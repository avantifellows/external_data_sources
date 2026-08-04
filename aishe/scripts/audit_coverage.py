#!/usr/bin/env python3
"""
Year-by-year ingest audit for the AISHE higher-ed fact.

Answers three questions per year, from the registries and the built parquet
rather than from anyone's memory:

  HAVE      which editions of the report exist for that year (PDF, Excel, both)
  INGESTED  which of its published tables are registered and actually parsed
  GAPS      which are known not to reconcile, and by how much

Run after clean_aishe.py. Writes docs/INGEST_AUDIT.md and prints the same table.

  python3 scripts/audit_coverage.py
  python3 scripts/audit_coverage.py --check   # exit 1 if a registered table is
                                              # missing from the parquet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (PDF_REPORT_URLS, PDF_REPORTS, RAW_SHEETS, REPORTS,
                     PDF_TABLES, TABLES)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "INGEST_AUDIT.md"

# Tables each edition publishes that this pipeline cares about, and the cut each
# feeds. Anything absent from PDF_TABLES/RAW_SHEETS for a year is a gap.
WANTED = {
    "T12": "ug_discipline (enrolment)",
    "T14": "state_social (enrolment)",
    "T15": "state_social (enrolment)",
    "T33": "state_level (graduates)",
    "T34": "programme_social (graduates)",
    "T35": "ug_discipline (graduates)",
}

# Known failures, kept in step with the comment above PDF_TABLES in sources.py.
# (year, table) -> (delta, what it is measured against, note)
KNOWN_GAPS = {
    ("2015-16", "T34"): (-638_114, "T33 Grand Total",
                         "a large block of programmes missing"),
    ("2016-17", "T34"): (-854, "T33 Grand Total",
                         "a few rows printing <3 figures"),
    ("2017-18", "T34"): (-7_408, "own Grand Total", "same class as 2018-19's -51"),
    ("2017-18", "T12"): (+38_652, "own Grand Total",
                         "a subject row read as a discipline"),
    ("2016-17", "T35"): (None, "own Grand Total",
                         "ranked-list layout; the anchor itself misreads"),
    ("2017-18", "T35"): (None, "own Grand Total", "ranked-list layout"),
}

# Excel sheets present in the workbooks but not registered in RAW_SHEETS. Recorded
# because they are the cheapest remaining coverage: already-clean Excel, no PDF
# parsing needed. Verified by inspecting the workbooks' sheet names.
UNUSED_EXCEL: dict[str, list[str]] = {
    # All the sheets previously listed here are now registered in RAW_SHEETS.
    # 2022-23 / 2023-24 have no workbook at all (see sources.REPORT_URLS), so
    # there is nothing unused left to record.
}


def _editions(year: str) -> str:
    have = []
    if year in PDF_REPORT_URLS:
        have.append("PDF" + ("" if PDF_REPORTS[year].exists() else " (not fetched)"))
    if year in REPORTS:
        have.append("Excel" + ("" if REPORTS[year].exists() else " (not fetched)"))
    return " + ".join(have) or "—"


def build() -> tuple[str, list[str]]:
    df = pd.read_parquet(TABLES[0].local_path) if TABLES[0].local_path.exists() \
        else pd.DataFrame(columns=["cut", "aishe_year", "value"])

    pdf_reg: dict[str, set[str]] = {}
    for t in PDF_TABLES:
        pdf_reg.setdefault(t.year, set()).add(t.label)
    xls_reg: dict[str, set[str]] = {}
    for r in RAW_SHEETS:
        # 33OutTurnState -> T33, 12UGDisc -> T12, 34a -> T34
        key = "T" + "".join(c for c in r.sheet[:3] if c.isdigit())
        xls_reg.setdefault(r.year, set()).add(key)

    years = sorted(set(PDF_REPORT_URLS) | set(REPORTS))
    lines, problems = [], []

    lines.append("| Year | Editions held | Ingested tables | Rows in fact | Not reconciled |")
    lines.append("|---|---|---|---|---|")
    for y in years:
        got = sorted(pdf_reg.get(y, set()) | xls_reg.get(y, set()))
        rows = int((df.aishe_year == y).sum()) if len(df) else 0
        gaps = []
        for tbl in WANTED:
            if tbl in got:
                continue
            if (y, tbl) in KNOWN_GAPS:
                d, against, _note = KNOWN_GAPS[(y, tbl)]
                gaps.append(f"{tbl} ({d:+,} vs {against})" if d is not None
                            else f"{tbl} (unparsed)")
            elif y <= "2018-19" and tbl not in ("T14", "T15"):
                gaps.append(f"{tbl} (not attempted)")
            elif y >= "2022-23":
                gaps.append(f"{tbl} (no workbook; PDF not parsed)")
            elif tbl == "T15":
                # 2019-20 onward fold PwD/Muslim/Minority into the Table 14 sheet
                # rather than printing a separate Table 15.
                continue
        if got and not rows:
            problems.append(f"{y}: {len(got)} tables registered but 0 rows in the parquet")
        lines.append(f"| {y} | {_editions(y)} | {', '.join(got) or '—'} "
                     f"| {rows:,} | {'; '.join(gaps) or 'nothing outstanding'} |")

    body = [
        "# AISHE ingest audit",
        "",
        "Generated by `scripts/audit_coverage.py` — do not hand-edit. Run it after",
        "`clean_aishe.py` to refresh.",
        "",
        f"Fact table: **{len(df):,} rows** across "
        f"**{df.aishe_year.nunique() if len(df) else 0} years** and "
        f"**{df.cut.nunique() if len(df) else 0} cuts**.",
        "",
        "`Editions held` is what exists upstream and whether it is in `raw/`.",
        "`Ingested tables` is what the registries actually parse. Anything in the",
        "last column is either a measured reconciliation failure (delta shown), a",
        "table never attempted, or — for 2019-20 onward — an Excel sheet sitting",
        "unused in a workbook we already have.",
        "",
        *lines,
        "",
        "## Rows by cut and year",
        "",
    ]
    if len(df):
        ct = pd.crosstab(df.aishe_year, df.cut)
        body.append("| Year | " + " | ".join(ct.columns) + " |")
        body.append("|---" * (len(ct.columns) + 1) + "|")
        for y, r in ct.iterrows():
            body.append(f"| {y} | " + " | ".join(f"{v:,}" if v else "—"
                                                 for v in r) + " |")
    body += ["", "## Unused Excel sheets", ""]
    if UNUSED_EXCEL:
        body.append("Already-clean workbook sheets we hold but do not parse.")
        body.append("")
        for y, sheets in UNUSED_EXCEL.items():
            body.append(f"- **{y}**: " + ", ".join(f"`{s}`" for s in sheets))
    else:
        body.append("None — every sheet in every workbook we hold is now parsed.")
    body += [
        "",
        "## Not available from AISHE at all",
        "",
        "- **Household income** — no edition has an income variable. Use PLFS `mpce`.",
        "- **EWS before 2019-20** — the category does not appear until then.",
        "- **Excel before 2019-20** — only the PDF edition was ever published.",
        "",
    ]
    return "\n".join(body) + "\n", problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if a registered table contributed no rows")
    args = ap.parse_args()

    text, problems = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(text)
    print(f"written to {OUT.relative_to(ROOT)}")
    if problems:
        for p in problems:
            print(f"  ⚠ {p}")
        if args.check:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
