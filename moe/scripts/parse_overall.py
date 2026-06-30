"""
Extract Class X (Secondary) and Class XII (Higher Secondary) overall results
from MoE 'Results of Secondary and Higher Secondary Examinations' PDFs for
years 2020, 2021, 2022, 2024.

For each year and level (Class X / Class XII) we pull the
'Annual & Supplementary - Regular & Private - All Categories' table:

  2020/2021 -> Section A/B "Table 3"
  2022/2024 -> Section A/B "Table 1"  (Mgmt-wise-All)

Section A holds Class X (Secondary), Section B holds Class XII (Higher Secondary).
We disambiguate which section a page belongs to via the running page header
text ("RESULTS OF SECONDARY EXAMINATION" vs "RESULTS OF HIGHER SECONDARY EXAMINATION").

Schema after extraction (15 cols, 1-3 ID + 12 numeric):
  Sl.No | State | Board | Reg-B | Reg-G | Reg-T | App-B | App-G | App-T
                       | Pass-B | Pass-G | Pass-T | Pct-B | Pct-G | Pct-T

Returns (via build_df): DataFrame [year, level, state, board, gender, registered,
appeared, passed_annual_and_supp, pass_percentage] — merged into the single fact
by clean_board_results.py.
"""
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import REPORTS

# Per year, the "all categories Reg+Private" table number for each section.
# (Same number applies to Section A and Section B — page header disambiguates.)
TABLE_NUMBER = {2020: 3, 2021: 3, 2022: 1, 2024: 1}


def normalise_int(s):
    if s is None:
        return None
    s = str(s).strip().replace(",", "").replace("\n", " ")
    if not s or s in {"-", "--"}:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def normalise_pct(s):
    if s is None:
        return None
    s = str(s).strip().replace("%", "").replace("\n", " ")
    if not s or s in {"-", "--"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def build_section_map(pdf) -> list[str | None]:
    """Walk pages and forward-fill section based on:
      - Section divider pages ("Section A - Examination Result YYYY (Secondary)" /
        "Section B - Examination Result YYYY (Higher Secondary)") — present in
        2020 / 2021 / 2022 / 2024.
      - Running page headers ("RESULTS OF SECONDARY EXAMINATION" / "RESULTS OF
        HIGHER SECONDARY EXAMINATION") — present in 2022 / 2024 layouts.

    Returns a list of length len(pdf.pages); each entry is 'A', 'B', or None
    for cover/TOC/data-highlights pages outside both sections.
    """
    out = [None] * len(pdf.pages)
    current = None
    for i, page in enumerate(pdf.pages):
        txt = (page.extract_text() or "").strip()
        # Check for explicit section divider pages first
        upper = txt.upper()
        # Match divider page (short text, has "SECTION A" / "SECTION B" + "EXAMINATION RESULT")
        if len(txt) < 200 and "SECTION A" in upper and "EXAMINATION RESULT" in upper:
            current = "A"
        elif len(txt) < 200 and "SECTION B" in upper and "EXAMINATION RESULT" in upper:
            current = "B"
        else:
            # Use running header — but ONLY look at the first line to avoid
            # being fooled by board names that contain "Higher Secondary".
            head = " ".join(txt.split("\n")[:1]).upper()
            if "RESULTS OF HIGHER SECONDARY" in head:
                current = "B"
            elif "RESULTS OF SECONDARY" in head:
                current = "A"
            # else: keep current (forward-fill)
        out[i] = current
    return out


def parse_overall_rows(table, year, level):
    """Parse the year-specific overall table layout.

    2020 / 2021 layout (18 cols):
      0: S.No.        1: State     2: Board
      3-5:  Appeared (Reg+Private) Boys/Girls/Total
      6-8:  Passed Annual Boys/Girls/Total
      9-11: Passed Supplementary Boys/Girls/Total
      12-14: Passed Annual & Supplementary Boys/Girls/Total
      15-17: Pass Percentage Boys/Girls/Total
      (NO 'Registered' column)

    2022 / 2024 layout (15 cols):
      0: S.No.        1: State     2: Board
      3-5:  Registered (Reg+Private) Boys/Girls/Total
      6-8:  Appeared (Reg+Private) Boys/Girls/Total
      9-11: Passed Annual (incl Supplementary) Boys/Girls/Total
      12-14: Pass Percentage Boys/Girls/Total

    For both layouts we emit unified schema:
      registered, appeared, passed_annual_and_supp, pass_percentage
      (registered is None for 2020/2021 — not published).
    """
    if not table:
        return []
    ncols = max(len(r) for r in table)
    last_state = ""
    out = []
    layout_2020 = year in (2020, 2021)

    for r in table:
        if not r:
            continue
        sno = (r[0] or "").strip() if len(r) > 0 else ""
        if not sno.isdigit():
            continue
        state = (r[1] or "").strip().replace("\n", " ") if len(r) > 1 else ""
        if state:
            last_state = state
        else:
            state = last_state
        board = (r[2] or "").strip().replace("\n", " ") if len(r) > 2 else ""
        if not board:
            continue

        # Pad row for safety
        def get(idx):
            return r[idx] if idx < len(r) else None

        for gi, gender in enumerate(["Boys", "Girls", "Total"]):
            if layout_2020:
                # 18 cols
                reg = None  # not in this layout
                app = normalise_int(get(3 + gi))
                passed = normalise_int(get(12 + gi))  # Annual+Supplementary col
                pct = normalise_pct(get(15 + gi))
            else:
                # 15 cols
                reg = normalise_int(get(3 + gi))
                app = normalise_int(get(6 + gi))
                passed = normalise_int(get(9 + gi))
                pct = normalise_pct(get(12 + gi))
            out.append({
                "year": year,
                "level": level,
                "state": state,
                "board": board,
                "gender": gender,
                "registered": reg,
                "appeared": app,
                "passed_annual_and_supp": passed,
                "pass_percentage": pct,
            })
    return out


def find_tables(pdf, year):
    """Find Section A and Section B 'overall all-categories' tables."""
    tnum = TABLE_NUMBER[year]
    label_pat = re.compile(rf"Table\s*{tnum}\b[\s\-:–—]", re.IGNORECASE)
    section_map = build_section_map(pdf)

    found = {"A": [], "B": []}
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        sect = section_map[i]
        if not sect:
            continue
        # Title check: must contain "Table N -" + a Reg+Private + All Categories context
        if not label_pat.search(text):
            continue
        # Avoid Tables 31/33/35 (stream tables) being matched: ensure the title text
        # explicitly mentions "Regular" or "Annual and Supplementary"
        if "Regular" not in text and "Reg+Private" not in text and "Examination Results" not in text:
            continue
        # 2022/2024 must additionally NOT be a SC/ST table (Table 11/21).
        # Since we filter for tnum=1 specifically, that's already constrained.
        # We also want to skip the percentage variant (Table 2 / Table 4).
        # Filter: title contains "All Categories" AND "Number of Students" (not pct table)
        if "All Categories" not in text and "All-Categories" not in text:
            # 2020 tables don't have the "-All Categories" suffix in title; allow if pure Table 3
            pass
        for tbl in page.extract_tables():
            if not tbl:
                continue
            ncols = max(len(r) for r in tbl)
            if ncols < 12:
                continue
            has_data = any((r[0] or "").strip().isdigit() for r in tbl if r)
            if has_data:
                found[sect].append((i, tbl))
                break
    return found


def build_df() -> pd.DataFrame:
    all_rows = []
    for year in [2020, 2021, 2022, 2024]:
        pdf_path = REPORTS[year]
        with pdfplumber.open(pdf_path) as pdf:
            tables = find_tables(pdf, year)
            for sect_letter, level in [("A", "Class X"), ("B", "Class XII")]:
                pages = tables[sect_letter]
                rows_for_table = []
                for _, tbl in pages:
                    rows_for_table.extend(parse_overall_rows(tbl, year, level))
                # Drop the 'Total' aggregate row at table bottom
                rows_for_table = [r for r in rows_for_table if r["board"].lower() != "total"]
                all_rows.extend(rows_for_table)
                # Dedupe by (board, gender) — pdfplumber may pick up the same table
                # multiple times if title appears across pages. Keep first occurrence.
                seen = set()
                deduped = []
                for r in rows_for_table:
                    key = (r["year"], r["level"], r["board"], r["gender"])
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(r)
                n_boards = len({(r["board"]) for r in deduped})
                print(f"  {year} {level} (Section {sect_letter} Table {TABLE_NUMBER[year]}): "
                      f"{len(pages)} pages -> {n_boards} boards x 3 gender = {len(deduped)} rows")

    # Final dedupe across all years
    seen = set()
    final_rows = []
    for r in all_rows:
        key = (r["year"], r["level"], r["board"], r["gender"])
        if key in seen:
            continue
        seen.add(key)
        final_rows.append(r)

    df = pd.DataFrame(final_rows, columns=[
        "year", "level", "state", "board", "gender",
        "registered", "appeared", "passed_annual_and_supp", "pass_percentage",
    ])
    print(f"  overall: {len(df):,} rows")
    return df
