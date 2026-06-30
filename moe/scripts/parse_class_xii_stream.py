"""
Extract Class XII stream-wise results (Arts / Commerce / Science / Vocational)
from MoE 'Results of Secondary and Higher Secondary Examinations' PDFs for
years 2020, 2021, 2022, 2024.

For each year the report has three Section B tables of interest:

  All-Categories stream table   2020/2021 = Table 13   2022/2024 = Table 31
  SC stream table                  "      = Table 15      "      = Table 33
  ST stream table                  "      = Table 17      "      = Table 35

Each table layout is identical:
  Sl.No | State | Name of Board | All-Streams Boys/Girls/Total
                                | Arts Boys/Girls/Total
                                | Commerce Boys/Girls/Total
                                | Science Boys/Girls/Total
                                | Vocational Boys/Girls/Total

Returns (via build_df): DataFrame [year, state, board, social_category, stream,
gender, students_passed] — merged into the single fact by clean_board_results.py.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import REPORTS

# (year, table_label_in_pdf -> social_category)
# Each entry: title regex (matches the table title text on each page) + category label.
TABLES = [
    # 2020/2021: Tables 13/15/17. 2022/2024: Tables 31/33/35.
    # Title text format: "Table N -Stream-wise Results Annual & Supplementary - ..."
    # We match the table number + "Stream" + the category indicator.
    {"year": 2020, "label": "Table 13", "category": "All Categories"},
    {"year": 2020, "label": "Table 15", "category": "Scheduled Caste"},
    {"year": 2020, "label": "Table 17", "category": "Scheduled Tribe"},
    {"year": 2021, "label": "Table 13", "category": "All Categories"},
    {"year": 2021, "label": "Table 15", "category": "Scheduled Caste"},
    {"year": 2021, "label": "Table 17", "category": "Scheduled Tribe"},
    {"year": 2022, "label": "Table 31", "category": "All Categories"},
    {"year": 2022, "label": "Table 33", "category": "Scheduled Caste"},
    {"year": 2022, "label": "Table 35", "category": "Scheduled Tribe"},
    {"year": 2024, "label": "Table 31", "category": "All Categories"},
    {"year": 2024, "label": "Table 33", "category": "Scheduled Caste"},
    {"year": 2024, "label": "Table 35", "category": "Scheduled Tribe"},
]

STREAMS = ["All Streams", "Arts", "Commerce", "Science", "Vocational"]
GENDERS = ["Boys", "Girls", "Total"]


def normalise_int(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "")
    if not s:
        return None
    # blacked-out cells often come through as empty or as a single dash
    if s in {"-", "--"}:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def find_table_pages(pdf, label_regex):
    """Return list of (page_idx, table) for pages whose text contains the label
    regex AND whose extracted tables look like the stream table.

    Two layouts are accepted:
      - 18 physical columns (2021/2022/2024): direct mapping
      - ~54 physical columns (2020): each logical column is split into 3 sub-cells
    """
    pages = []
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if not label_regex.search(text):
            continue
        tables = page.extract_tables()
        for tbl in tables:
            if not tbl:
                continue
            ncols = max(len(r) for r in tbl)
            # Accept 18-col layout OR 50+ -col layout (2020 quirky split).
            if ncols < 18 or (20 < ncols < 45):
                continue
            has_data = any(((r[0] or "").strip().isdigit()) for r in tbl if r)
            if has_data:
                pages.append((i, tbl))
                break  # one stream table per page
    return pages


def parse_stream_rows(table, year, category):
    """Yield (year, state, board, social_category, stream, gender, value).

    Auto-detects column layout: 18 physical cols (2021+) vs ~54 cols (2020).
    """
    if not table:
        return []
    ncols = max(len(r) for r in table)

    is_2020_style = ncols >= 45  # 2020 PDF — pdfplumber over-splits cells
    last_state = ""
    out = []

    for r in table:
        if not r:
            continue

        if not is_2020_style:
            # 18-col clean layout (2021/2022/2024) — column positions are stable.
            sno = (r[0] or "").strip() if len(r) > 0 else ""
            if not sno.isdigit():
                continue
            state = re.sub(r"\s+", " ", (r[1] or "").strip()) if len(r) > 1 else ""
            if state:
                last_state = state
            else:
                state = last_state
            board = re.sub(r"\s+", " ", (r[2] or "").strip()) if len(r) > 2 else ""
            if not board:
                continue
            for idx in range(15):
                dc = 3 + idx
                si, gi = divmod(idx, 3)
                val = normalise_int(r[dc]) if dc < len(r) else None
                out.append((year, state, board, category, STREAMS[si], GENDERS[gi], val))

        else:
            # 2020 layout: 54 physical cols, but column positions drift between
            # pages and rows because pdfplumber's grid detection isn't stable
            # for this PDF. Strategy: compress the row to its non-empty cells,
            # then take ID + the numeric tail. Streams are assumed left-to-right
            # in the conventional order (All / Arts / Commerce / Science /
            # Vocational); blacked-out streams are assumed to be from the end
            # (predominantly Vocational). Document this caveat in the notes.
            sno_raw = (r[0] or "").strip() if r else ""
            if not sno_raw.isdigit():
                continue
            non_empty = [(j, str(c).strip()) for j, c in enumerate(r) if c not in (None, "") and str(c).strip()]
            if not non_empty:
                continue
            # Drop leading S.No.
            cells = [c for _, c in non_empty]
            # cells[0] = sno
            assert cells[0] == sno_raw
            cells = cells[1:]
            # Next 1-2 cells are State (sometimes empty/forward-filled) + Board
            # Heuristic: state is short (<=30 chars no digits), board is long.
            state = ""
            board = ""
            i = 0
            while i < len(cells) and not cells[i].replace(",", "").replace(".", "").replace("-", "").isdigit():
                token = cells[i]
                if not state and len(token) <= 30:
                    state = token
                elif not board:
                    board = token
                else:
                    # Multi-word continuation of board name
                    board += " " + token
                i += 1
            state = re.sub(r"\s+", " ", state)
            board = re.sub(r"\s+", " ", board)
            if state:
                last_state = state
            else:
                state = last_state
            if not board:
                continue
            # Remaining cells are numerics
            numerics = cells[i:]
            # Pad to 15 with None to make schema consistent
            for idx in range(15):
                si, gi = divmod(idx, 3)
                val = normalise_int(numerics[idx]) if idx < len(numerics) else None
                out.append((year, state, board, category, STREAMS[si], GENDERS[gi], val))

    return out


def build_df() -> pd.DataFrame:
    all_rows = []
    for cfg in TABLES:
        year = cfg["year"]
        pdf_path = REPORTS[year]
        # Build a regex that anchors on table label as a *whole token* — e.g.,
        # 'Table 13' must not match 'Table 130'. Allow optional period/dash.
        # Match 'Table 31' or 'Table31' (no space variant) — newer PDFs drop the space.
        # Use \D before the digit so we don't match e.g. 'Table 130' for 'Table 13'.
        m = re.match(r"Table\s*(\d+)", cfg["label"])
        tnum = m.group(1) if m else cfg["label"]
        label_pat = re.compile(rf"Table\s*{tnum}\b[\s\-:]*Stream", re.IGNORECASE)
        with pdfplumber.open(pdf_path) as pdf:
            pages = find_table_pages(pdf, label_pat)
            n_rows_for_table = 0
            for _, tbl in pages:
                rows = parse_stream_rows(tbl, year, cfg["category"])
                # Drop "Total" board rows (the totals row at the table's bottom)
                rows = [r for r in rows if r[2].lower() != "total"]
                all_rows.extend(rows)
                n_rows_for_table += len(rows) // (len(STREAMS) * len(GENDERS))
            print(f"  {year} {cfg['label']} ({cfg['category']:18s}): "
                  f"{len(pages)} pages -> {n_rows_for_table} board rows")

    cols = ["year", "state", "board", "social_category", "stream", "gender", "students_passed"]
    # Drop blacked-out cells (None values) — same as the CSV extractor.
    records = [dict(zip(cols, r)) for r in all_rows if r[6] is not None]
    df = pd.DataFrame(records, columns=cols)
    print(f"  stream: {len(df):,} non-null rows ({len(all_rows) - len(records):,} blacked-out cells dropped)")
    return df
