"""
Reshape the UDISE+ enrolment dashboard export (wide cross-tab) into one tidy
long-form fact, written to clean/enrolment.parquet.

The export (sheet "UDISE+") is a wide cross-tab:
  - rows 0-5: title / metadata
  - the class-label header row (Balvatika-1/2/3, Class-1 … Class-12), each label
    merged across a Girls/Boys pair
  - the sub-header row: "Location, School Management(Detailed),
    School Category(Detailed), Urban/Rural", then Girls/Boys repeating per class,
    then a final "Overall" total column
  - data rows below

Output (BQ: udise_fact_enrolment), one row per
  (academic_year, state, school_management, school_category, urban_rural,
   class_level, gender) → enrolment

Usage:
  python3 scripts/clean_udise.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import ACADEMIC_YEAR, CLEAN, SHEET, SOURCE_XLSX, TABLES

ID_COLS = ["state", "school_management", "school_category", "urban_rural"]


def build_df() -> pd.DataFrame:
    if not SOURCE_XLSX.exists():
        raise SystemExit(f"missing source xlsx: {SOURCE_XLSX}")
    raw = pd.read_excel(SOURCE_XLSX, sheet_name=SHEET, header=None, dtype=str)

    # Locate the sub-header row (its first cell is exactly "Location").
    hdr = None
    for i in range(min(15, len(raw))):
        if str(raw.iat[i, 0]).strip() == "Location":
            hdr = i
            break
    if hdr is None:
        raise SystemExit("could not find the 'Location' sub-header row")

    sub = raw.iloc[hdr]                       # Location / … / Girls / Boys / … / Overall
    classes = raw.iloc[hdr - 1].ffill()       # class labels (merged across Girls/Boys pairs)

    # Value columns = those whose sub-header is Girls or Boys (excludes "Overall").
    value_cols = [
        c for c in range(4, raw.shape[1])
        if str(sub.iat[c]).strip() in ("Girls", "Boys")
    ]

    # The export mixes leaf detail rows with subtotal/total rows at several
    # levels (urban_rural="Total" = Rural+Urban; blank-urban_rural = state
    # subtotals; a blank-Location all-India grand total). Keep only the LEAF
    # rows — state + management + category present and urban_rural in
    # {Rural, Urban} — so the fact has no double-counting. The aggregates are
    # all derivable by summing.
    records = []
    for r in range(hdr + 1, len(raw)):
        row = raw.iloc[r]
        ids = [str(row.iat[k]).strip() for k in range(4)]
        state, mgmt, cat, loc = ids
        if loc not in ("Rural", "Urban"):
            continue
        if any(v == "" or v.lower() == "nan" for v in (state, mgmt, cat)):
            continue
        for c in value_cols:
            records.append(ids + [
                str(classes.iat[c]).strip(),     # class_level
                str(sub.iat[c]).strip(),         # gender
                row.iat[c],                       # enrolment (raw)
            ])

    df = pd.DataFrame(records, columns=ID_COLS + ["class_level", "gender", "enrolment"])
    df.insert(0, "academic_year", ACADEMIC_YEAR)
    df["enrolment"] = pd.to_numeric(df["enrolment"], errors="coerce").astype("Int64")
    return df


def main() -> None:
    df = build_df()
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = TABLES[0].local_path
    df.to_parquet(out, index=False, engine="pyarrow")
    print(f"udise_fact_enrolment: {len(df):,} rows → {out.name}")
    print(f"  states={df.state.nunique()}  classes={df.class_level.nunique()}  "
          f"managements={df.school_management.nunique()}  categories={df.school_category.nunique()}")
    print(f"  total enrolment (sum) = {int(df.enrolment.sum()):,}")


if __name__ == "__main__":
    main()
