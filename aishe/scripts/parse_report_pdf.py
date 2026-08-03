"""
Parse the AISHE Final Report **PDFs** in raw/ into the same higher-ed fact rows
that clean_aishe.py builds from the Excel workbooks.

Why a second parser: AISHE only publishes an Excel edition of the Final Report
from 2019-20 onward. Every earlier year (2012-13 … 2018-19) exists as a PDF and
nothing else, so the historical backfill cannot go through openpyxl. This module
reads the same three published cross-tabs out of the PDF and emits rows in the
identical grain, so both parsers feed one table.

  cut='state_level'      Table 33   graduates by state × level
  cut='programme_social' Table 34   graduates by programme (see the caveat below)
  cut='ug_discipline'    Table 12   UG enrolment by discipline

**Caveat on the programme cut.** The Excel-era `programme_social` cut comes from
Table 34a, which breaks programme out by social category. The historical PDFs
have no Table 34a — their Table 34 is programme × Male/Female/Total only. Those
rows therefore carry social_category='All Categories', the same sentinel the
Excel parser uses for that band. They are the "All Categories" slice of the cut
and nothing more: a historical year answers "how many B.A. graduates", never
"how many SC B.A. graduates".

Geometry is detected, never assumed — the same discipline the Excel parser
follows, for the same reason. AISHE renumbers and re-lays-out tables between
editions, so every reader locates its own columns from the Male/Female/Total
header row and verifies the group-label row above it before reading positionally.
Value cells fail loudly: a text label landing in a value column is an error, not
a silent 0.

Which (year, table) pairs are parsed is declared in sources.PDF_TABLES, not here.

Usage:
  python3 scripts/parse_report_pdf.py                  # all registered years
  python3 scripts/parse_report_pdf.py --year 2018-19   # one year
  python3 scripts/parse_report_pdf.py --year 2018-19 --debug
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import PDF_REPORTS, PDF_TABLES, SENTINEL

GENDERS = ["Male", "Female", "Total"]

# Table 33's published level groups, in the order they appear across its pages.
# "Grand Total" is a published roll-up, not a level — it is read for validation
# and never emitted as a fact row.
PDF_LEVELS = [
    "Ph.D.", "M.Phil.", "Post Graduate", "Under Graduate",
    "PG Diploma", "Diploma", "Certificate", "Integrated",
]
GRAND_TOTAL = "Grand Total"

# Cells that legitimately mean "no value" in these tables (mirrors clean_aishe).
NULLISH = {"", "-", "--", "na", "n.a.", "n/a", "nil", "*", ".", "…"}

# Rows whose label is a published roll-up rather than a member of the dimension.
ALL_INDIA = {"allindia", "india", "total", "grandtotal"}

# Page furniture that sits inside the table's column band and so reads as a data
# row: the running footer ("AISHE 2015-16 T-44") and the bare table-page marker
# ("T-12"). Present from 2015-16 to 2017-18; 2018-19 prints only the marker.
FURNITURE_RE = re.compile(
    r"^(AISHE\s*\d{4}-\d{2}\s*)?T-\d+\s*\(?[a-z]?\)?$|^AISHE\s*\d{4}-\d{2}$",
    re.I,
)

# A label word this far left is the row's serial number, not part of the label.
SERIAL_X = 75.0


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _num(text: str, ctx: str) -> int:
    """Coerce a value cell to int, failing loudly on anything unexpected."""
    s = str(text).strip()
    if s.lower() in NULLISH:
        return 0
    try:
        return int(float(s.replace(",", "")))
    except ValueError:
        raise SystemExit(
            f"non-numeric value {text!r} in a value column ({ctx}).\n"
            f"The column layout has probably shifted. Re-run with --debug to see "
            f"the detected geometry."
        )


# ─── Line assembly ───────────────────────────────────────────────────────────
def _lines(page) -> list[list[dict]]:
    """Group a page's words into visual lines, ordered top-to-bottom.

    Line bands come from pdfplumber's own `extract_text_lines`, and each word is
    placed in the band containing its vertical midpoint. Clustering words on
    `top` with a fixed tolerance instead does not survive these reports: the row
    pitch tightens between editions, and at 2016-17's spacing any tolerance loose
    enough to hold a row's label together with its digits also merges the
    "Engineering & Technology Total" row into the subject row beneath it —
    concatenating two rows' value cells into one impossible number.
    """
    bands = page.extract_text_lines()
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
    if not bands or not words:
        return []
    rows: list[list[dict]] = [[] for _ in bands]
    for w in words:
        mid = (w["top"] + w["bottom"]) / 2
        for i, b in enumerate(bands):
            if b["top"] <= mid <= b["bottom"]:
                rows[i].append(w)
                break
    return [sorted(r, key=lambda w: w["x0"]) for r in rows if r]


def _centers(words: list[dict]) -> list[float]:
    return [(w["x0"] + w["x1"]) / 2 for w in words]


def _bounds(centers: list[float]) -> list[float]:
    """Column split points: the midpoint between consecutive column centers.

    Values in these tables are right-aligned, so a value's centre sits to the
    right of its column's header centre. Midpoint boundaries absorb that offset,
    which matters most on sparse rows — a state reporting only Ph.D. totals must
    not have its lone number read into the Male column.
    """
    return [(a + b) / 2 for a, b in zip(centers, centers[1:])]


def _assign(words: list[dict], bounds: list[float], n: int) -> list[str]:
    """Bucket value words into `n` columns using the split points."""
    cols: list[list[str]] = [[] for _ in range(n)]
    for w in words:
        c = (w["x0"] + w["x1"]) / 2
        idx = 0
        while idx < len(bounds) and c >= bounds[idx]:
            idx += 1
        cols[min(idx, n - 1)].append(w["text"])
    return ["".join(c) for c in cols]


# ─── Geometry detection ──────────────────────────────────────────────────────
def _gender_header(lines: list[list[dict]]) -> tuple[int, list[dict]]:
    """Find the Male/Female/Total header line. Returns (line index, words)."""
    for i, line in enumerate(lines[:12]):
        hits = [w for w in line if _key(w["text"]) in {"male", "female", "total"}]
        if len(hits) >= 3 and len(hits) % 3 == 0:
            return i, hits
    raise SystemExit(
        "could not find a Male/Female/Total header row on this page — "
        "re-run with --debug to see the extracted lines."
    )


def _assert_single_gender_block(page, ctx: str, extra: str = "") -> None:
    """Fail unless the page carries exactly one Male/Female/Total block.

    The line-level readers assume three value columns. A page with six or more
    gender headers is a cross-tab (some dimension broken out) and would be read
    as if only its first three columns existed — plausible numbers, wrong ones.
    """
    _i, hits = _gender_header(_lines(page))
    if len(hits) != 3:
        raise SystemExit(
            f"{ctx}: expected one Male/Female/Total block (3 value columns) but "
            f"found {len(hits)} gender headers, i.e. {len(hits)//3} groups.\n"
            + (extra or "This edition breaks the table out by a further "
                        "dimension — it needs a cross-tab reader.")
        )


def _verify_groups(lines: list[list[dict]], header_i: int,
                   first_x: float, expected: list[str], ctx: str) -> None:
    """Check the group-label row above the gender header against `expected`.

    The read within a value block is positional, so the group order is load
    bearing. This is the tripwire for an edition that reorders or drops a level.
    """
    for i in range(header_i - 1, max(-1, header_i - 4), -1):
        labels = [w for w in lines[i] if w["x1"] > first_x - 30]
        if len(labels) < 2:
            continue
        # Group labels can wrap ("Post" / "Graduate") — merge words that sit
        # within a hair of each other before comparing.
        merged: list[str] = []
        for w in labels:
            if merged and w["x0"] - prev_x1 < 8:
                merged[-1] += " " + w["text"]
            else:
                merged.append(w["text"])
            prev_x1 = w["x1"]
        if [_key(m) for m in merged] != [_key(e) for e in expected]:
            raise SystemExit(
                f"{ctx}: group labels don't match the expected order.\n"
                f"  found:    {merged}\n  expected: {expected}\n"
                f"AISHE re-laid-out this table — fix the group list before "
                f"trusting the numbers (the read is positional)."
            )
        return
    raise SystemExit(f"{ctx}: no group-label row found above the gender header.")


def _label_and_values(line: list[dict], label_x: float):
    """Split a data line into its label words and its value words.

    A leading pure-integer token is the row's serial number, not part of the
    label, and is dropped. It is identified by value rather than by x position:
    the label column starts further left on pages whose value block is wider, so
    a fixed x cutoff silently truncates state names ("Andhra Pradesh" →
    "Pradesh") on exactly the pages carrying the largest numbers.
    """
    label = [w for w in line if w["x1"] <= label_x]
    values = [w for w in line if w["x0"] > label_x]
    serial = False
    if label:
        head = label[0]["text"]
        if re.fullmatch(r"\d{1,3}", head):
            serial, label = True, label[1:]
        else:
            # 2016-17 sets the serial hard against the label with no gap, so it
            # extracts as one word ("1Ph.D.-Doctor"). Split the digits off rather
            # than failing to recognise the row at all.
            m = re.fullmatch(r"(\d{1,3})(\D.*)", head)
            if m:
                serial = True
                label = [{**label[0], "text": m.group(2)}] + label[1:]
    return label, values, serial


def _text(words: list[dict]) -> str:
    return " ".join(w["text"] for w in words).strip()


def _column_number_row(lines: list[list[dict]], header_i: int) -> int | None:
    """Index of the column-number row ("1 2 3 … 11") printed under the header.

    AISHE prints one beneath every table header. It must be excluded from the
    body outright: it looks exactly like a data row (a serial-column entry plus a
    full set of numbers), so left in place it adopts the first row's wrapped
    label and contributes its column indices as if they were counts.
    """
    for i in range(header_i + 1, min(header_i + 4, len(lines))):
        line = lines[i]
        if len(line) < 4 or not all(re.fullmatch(r"\d{1,2}", w["text"]) for w in line):
            continue
        seq = [int(w["text"]) for w in line]
        if seq[:2] == [1, 2] and seq == sorted(seq):
            return i
    return None


def _has_serial_column(lines: list[list[dict]], numrow_i: int | None,
                       n_values: int) -> bool:
    """Whether this table has a Sl. No. column.

    Not every table does, and the difference must be *proven* rather than guessed
    from x positions. The column-number row numbers every column, so its length
    settles it: `n_values + 2` means serial + label + values (Table 33), while
    `n_values + 1` means label + values only (Table 12). Reading Table 12's
    leading "1" as a serial column silently drops every row.

    Only presence is returned, not a position. The column-number row's own "1" is
    typeset ~9pt left of where the data rows' serials sit, so matching a row's
    serial against that x centre rejects most of the table — the rows are found by
    "the line starts with an integer token" instead.
    """
    if numrow_i is None:
        return False
    return len(lines[numrow_i]) == n_values + 2


def _table_rows(lines: list[list[dict]], header_i: int, label_x: float,
                n_values: int, attach_orphans: bool = True):
    """Yield (label, label_words, value_words) per data row, re-joining wrapped
    labels.

    Rows are anchored on the serial number, not on the presence of values. Both
    alternatives are wrong on real pages:

    - "a line with values starts a row" loses a state whose every cell is blank
      (Daman and Diu reports nothing at some levels), because its label line then
      looks like a continuation and gets welded onto a neighbour.
    - "a continuation belongs to the row above" breaks where the label wraps
      *around* its values: on Table 33's third page the Andaman and Nicobar
      Islands row is three lines, with the digits in the middle one.

    The serial number always shares a line with that row's values, so lines
    carrying one are rows and every other line is a label fragment, attached to
    whichever row sits closest vertically.
    """
    numrow_i = _column_number_row(lines, header_i)
    has_serial = _has_serial_column(lines, numrow_i, n_values)
    body = lines[(numrow_i if numrow_i is not None else header_i) + 1:]

    rows: list[dict] = []
    orphans: list[tuple[float, list[dict]]] = []
    for line in body:
        if FURNITURE_RE.match(_text(line)):
            continue
        label, values, serial = _label_and_values(line, label_x)
        if has_serial:
            is_row = serial
            # The published roll-up row carries no serial number, so the serial
            # anchor alone would orphan it onto the last state.
            if not is_row and values and _key(_text(label)) in ALL_INDIA:
                is_row = True
        else:
            is_row = bool(values)
        if is_row:
            rows.append({"top": line[0]["top"], "label": label, "values": values})
        elif label:
            orphans.append((line[0]["top"], label))

    if attach_orphans:
        for top, frag in orphans:
            if not rows:
                continue
            nearest = min(rows, key=lambda r: abs(r["top"] - top))
            nearest.setdefault("frags", []).append((top, frag))

    for r in rows:
        parts = [(r["top"], r["label"])] + r.get("frags", [])
        words = [w for _t, frag in sorted(parts, key=lambda p: p[0]) for w in frag]
        text = _text(words)
        # Skip the column-number row printed under the header ("1 2 3 4 …").
        if text and not re.fullmatch(r"[\d\s]+", text):
            yield text, words, r["values"]


# ─── Table 33: graduates by state × level ────────────────────────────────────
def state_level_rows(pdf, year: str, pages: list[int], debug=False) -> list[dict]:
    """Table 33 spans several pages, three level-groups per page.

    Each page is read independently and contributes its own groups, so a year
    that splits the table differently still parses — the page's own gender header
    says how many groups are on it.
    """
    out: list[dict] = []
    seen_groups: list[str] = []
    grand: dict[str, dict[str, int]] = {}

    for pno in pages:
        page = pdf.pages[pno]
        lines = _lines(page)
        header_i, hits = _gender_header(lines)
        centers = _centers(hits)
        bounds = _bounds(centers)
        n = len(hits)
        n_groups = n // 3
        label_x = centers[0] - (centers[1] - centers[0]) / 2

        # Which groups this page carries: the next n_groups still unseen.
        remaining = [g for g in PDF_LEVELS + [GRAND_TOTAL] if g not in seen_groups]
        groups = remaining[:n_groups]
        if len(groups) < n_groups:
            raise SystemExit(
                f"{year} Table 33 page {pno+1}: page has {n_groups} value groups "
                f"but only {len(groups)} published levels remain unread "
                f"({seen_groups} already seen). The table's layout changed."
            )
        _verify_groups(lines, header_i, centers[0], groups,
                       f"{year} Table 33 p{pno+1}")
        seen_groups += groups
        if debug:
            print(f"    p{pno+1}: groups={groups} centers="
                  f"{[round(c,1) for c in centers]}")

        for state, _label, values in _table_rows(lines, header_i, label_x, n):
            cells = _assign(values, bounds, n)
            if _key(state) in ALL_INDIA:
                for gi, group in enumerate(groups):
                    grand.setdefault(group, {})
                    for j, gender in enumerate(GENDERS):
                        grand[group][gender] = _num(
                            cells[gi * 3 + j], f"{year} T33 All India/{group}/{gender}")
                continue
            for gi, group in enumerate(groups):
                if group == GRAND_TOTAL:
                    continue
                for j, gender in enumerate(GENDERS):
                    out.append({
                        "cut": "state_level", "aishe_year": year,
                        "metric": "graduates", "level": group, "state": state,
                        "discipline": SENTINEL, "programme": SENTINEL,
                        "social_category": SENTINEL, "gender": gender,
                        "value": _num(cells[gi * 3 + j],
                                      f"{year} T33 {state}/{group}/{gender}"),
                    })

    missing = [g for g in PDF_LEVELS if g not in seen_groups]
    if missing:
        raise SystemExit(
            f"{year} Table 33: never found the level group(s) {missing} across "
            f"pages {[p+1 for p in pages]}. The table spans more pages than were "
            f"located, or a level was dropped this edition."
        )
    _check_grand_total(out, grand, year, debug)
    return out


def _check_grand_total(rows, grand, year, debug=False) -> None:
    """The published Grand Total column must equal the sum of the levels.

    This is the strongest available self-check on a Table 33 parse: it catches a
    column misassignment that leaves every individual number looking plausible.
    """
    if not grand:
        print(f"    ⚠ {year} T33: no All India row found — grand-total check skipped")
        return
    if GRAND_TOTAL not in grand:
        return
    for gender in GENDERS:
        got = sum(r["value"] for r in rows if r["gender"] == gender)
        want = grand[GRAND_TOTAL][gender]
        # Levels sum across states; the published grand total is the same
        # population, so these must agree exactly.
        if got != want:
            raise SystemExit(
                f"{year} Table 33: levels sum to {got:,} for gender={gender} but "
                f"the published Grand Total is {want:,} (off by "
                f"{got - want:+,}).\nThe parse is wrong — a column was very "
                f"likely misassigned. Re-run with --debug."
            )
    if debug:
        print(f"    grand-total check OK ({grand[GRAND_TOTAL]})")


# ─── Three-column tables (12 / 34 / 35): <label> Male Female Total ───────────
# Read line-by-line off the text rather than by column geometry. These tables are
# a label plus exactly three integers, and the geometric read is actively worse
# here: their rows sit as little as 7pt apart with differing indents, so
# assigning words to column bands interleaves two adjacent rows into one
# ("Gandhian Grand Total Studies") and concatenates their digits into an
# impossible value. Anchoring on "three integers at end of line" cannot do that.
THREE_COL_RE = re.compile(
    r"^(?P<label>.*?)\s+(?P<m>-|[\d,]+)\s+(?P<f>-|[\d,]+)\s+(?P<t>-|[\d,]+)$"
)


def _three_col_rows(page, ctx: str):
    """Yield (label, x0, [male, female, total]) for each data line on the page.

    Lines that are not data — captions, headers, page furniture, a merged label
    cell, a wrapped label fragment — simply don't match and are returned as
    skipped so the caller can report them rather than lose them silently.
    """
    rows, skipped, totals = [], [], []
    for band in page.extract_text_lines():
        text = " ".join(band["text"].split())
        if not text or FURNITURE_RE.match(text):
            continue
        m = THREE_COL_RE.match(text)
        if not m:
            skipped.append(text)
            continue
        label = m.group("label").strip()
        # 2016-17 sets the serial hard against the label ("1Ph.D.-Doctor").
        label = re.sub(r"^\d{1,3}(?=\D)", "", label).strip()
        # A wholly numeric label is the column-number row ("1 2 3 4"), whose
        # trailing entries otherwise read as this row's Male/Female/Total.
        if not label or label.isdigit():
            continue
        cells = [_num(m.group(k), f"{ctx} {label}") for k in ("m", "f", "t")]
        if _key(label) in ALL_INDIA:
            totals.append(cells)
            continue
        rows.append((label, band["x0"], cells))
    return rows, skipped, totals


def _check_total(kept, published, ctx: str, debug=False) -> None:
    """The kept rows must sum to the table's published Grand Total.

    Without this the discipline read fails quietly. Picking discipline rows out of
    a discipline/subject hierarchy is a heuristic on indentation, and when it
    misfires the result is a slightly-too-large total that still looks like a
    credible national figure — 2017-18's Table 12 summed to 28,492,661 against a
    published 28,441,310, and nothing downstream would have noticed.
    """
    if not published:
        raise SystemExit(
            f"{ctx}: no Grand Total row found, so the row selection cannot be "
            f"verified. Refusing to emit unvalidated rows — inspect the table "
            f"with --debug."
        )
    # Several pages may each print a Grand Total; the table's is the largest.
    want = max(published, key=lambda c: c[2])
    for j, gender in enumerate(GENDERS):
        got = sum(c[j] for _l, c in kept)
        if got != want[j]:
            raise SystemExit(
                f"{ctx}: rows sum to {got:,} for gender={gender} but the "
                f"published Grand Total is {want[j]:,} (off by "
                f"{got - want[j]:+,}).\nThe row selection was read wrong — "
                f"re-run with --debug."
            )
    if debug:
        print(f"    grand-total check OK ({want})")


# ─── Table 34: graduates by programme ────────────────────────────────────────
def programme_rows(pdf, year: str, pages: list[int], debug=False) -> list[dict]:
    """Table 34 — programme × Male/Female/Total, no social-category breakdown.

    Emitted with social_category='All Categories' (see the module docstring).
    """
    out: list[dict] = []
    collected: list[tuple[str, float, list[int]]] = []
    published: list[list[int]] = []
    for pno in pages:
        page = pdf.pages[pno]
        _assert_single_gender_block(page, f"{year} Table 34 p{pno+1}", extra=(
            "If this edition breaks programme out by social category it is a "
            "Table 34a and needs the cross-tab reader instead."))
        rows, skipped, totals = _three_col_rows(page, f"{year} T34")
        if debug:
            print(f"    p{pno+1}: {len(rows)} rows, {len(skipped)} non-data lines")
        collected += rows
        published += totals

    # Same gate as the discipline tables: programmes must sum to the published
    # Grand Total, or a dropped/duplicated programme row goes unnoticed.
    _check_total([(l, c) for l, _x, c in collected], published,
                 f"{year} T34 programme", debug)

    for prog, _x0, cells in collected:
        for j, gender in enumerate(GENDERS):
            out.append({
                "cut": "programme_social", "aishe_year": year,
                "metric": "graduates", "level": SENTINEL,
                "state": SENTINEL, "discipline": SENTINEL,
                "programme": prog, "social_category": "All Categories",
                "gender": gender, "value": cells[j],
            })
    return out


# ─── Tables 12 / 35: UG by discipline ────────────────────────────────────────
def discipline_rows(pdf, year: str, pages: list[int], metric: str,
                    debug=False) -> list[dict]:
    """UG by discipline — Table 12 (enrolment) and Table 35 (graduates).

    Only discipline-level rows are kept, matching the Excel parser. Sub-subject
    rows are indented under a merged discipline label, so the discipline rows are
    the ones starting at the page's left margin. The margin is measured per page
    rather than fixed: the indent depth moves between editions.
    """
    out: list[dict] = []
    collected: list[tuple[str, float, list[int]]] = []
    published: list[list[int]] = []
    for pno in pages:
        page = pdf.pages[pno]
        _assert_single_gender_block(page, f"{year} Table {metric} p{pno+1}")
        rows, skipped, totals = _three_col_rows(page, f"{year} UG-discipline")
        if debug:
            print(f"    p{pno+1}: {len(rows)} data rows, "
                  f"{len(skipped)} non-data lines, {len(totals)} total rows")
        collected += rows
        published += totals
    if not collected:
        return out

    # The margin is taken across every page of the table, not per page. In
    # 2016-17 and 2017-18 this table is a ranked list whose subject rows and
    # discipline rows land on *different pages* — so a per-page margin makes the
    # subject column look like the left margin on the page that has only
    # subjects, and returns subjects instead of disciplines.
    margin = min(x0 for _l, x0, _c in collected)
    kept = [(l, c) for l, x0, c in collected if x0 <= margin + 6]
    if debug:
        print(f"    margin={margin:.1f} → {len(kept)}/{len(collected)} "
              f"discipline rows")
    _check_total(kept, published, f"{year} UG-discipline ({metric})", debug)
    for disc, cells in kept:
        if disc.lower().endswith(" total"):
            disc = disc[:-len(" total")].strip()
        if not disc or _key(disc) in ALL_INDIA:
            continue
        for j, gender in enumerate(GENDERS):
            out.append({
                "cut": "ug_discipline", "aishe_year": year,
                "metric": metric, "level": "Under Graduate",
                "state": SENTINEL, "discipline": disc,
                "programme": SENTINEL, "social_category": SENTINEL,
                "gender": gender, "value": cells[j],
            })
    return out


# ─── Page location ───────────────────────────────────────────────────────────
def _find_pages(pdf, title_re: str, year: str) -> list[int]:
    """Pages whose text contains the table's title.

    Matched on the printed title rather than a page number: AISHE's pagination
    moves between editions but the table captions are stable.
    """
    pat = re.compile(title_re, re.I)
    pages = [i for i, p in enumerate(pdf.pages) if pat.search(p.extract_text() or "")]
    if not pages:
        raise SystemExit(
            f"{year}: no page matches /{title_re}/ — the table is numbered "
            f"differently in this edition. Check the report's table list and fix "
            f"the title pattern in sources.PDF_TABLES."
        )
    return pages


READERS = {
    "state_level": lambda pdf, y, pages, metric, debug:
        state_level_rows(pdf, y, pages, debug),
    "programme_social": lambda pdf, y, pages, metric, debug:
        programme_rows(pdf, y, pages, debug),
    "ug_discipline": lambda pdf, y, pages, metric, debug:
        discipline_rows(pdf, y, pages, metric, debug),
}


def build_rows(years: list[str] | None = None, debug=False) -> list[dict]:
    """Parse every (year, table) pair declared in sources.PDF_TABLES."""
    wanted = [t for t in PDF_TABLES if years is None or t.year in years]
    if not wanted:
        raise SystemExit(
            f"no PDF tables registered for {years}. Registered years: "
            f"{sorted({t.year for t in PDF_TABLES})}"
        )
    rows: list[dict] = []
    for year in sorted({t.year for t in wanted}):
        path = PDF_REPORTS[year]
        if not path.exists():
            raise SystemExit(
                f"missing raw PDF: {path}\nRun: python3 scripts/fetch.py "
                f"--year {year}"
            )
        print(f"  {year}  {path.name}")
        with pdfplumber.open(path) as pdf:
            for t in [t for t in wanted if t.year == year]:
                pages = _find_pages(pdf, t.title_re, year)
                got = READERS[t.cut](pdf, year, pages, t.metric, debug)
                print(f"    {t.label:<10} pages={[p+1 for p in pages]} "
                      f"cut={t.cut:<17} metric={t.metric:<10} {len(got):>6,} rows")
                rows += got
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--year", action="append",
                    help="only this year (repeatable); default all registered")
    ap.add_argument("--debug", action="store_true",
                    help="print the detected geometry per page")
    args = ap.parse_args()

    rows = build_rows(args.year, args.debug)
    print(f"\n{len(rows):,} rows parsed from PDF reports")


if __name__ == "__main__":
    main()
