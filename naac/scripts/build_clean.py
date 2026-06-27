"""
Build clean NAAC parquets from the raw xlsx.

Reads each sheet listed in sources.py, applies column renames, strips
embedded newlines from text fields, repairs dirty date values, parses date
columns, and stamps a data_as_of constant (the date the file was published
on naac.gov.in). Writes one parquet per table to naac/clean/.

This is the auditable raw → clean recipe. The parquets it produces are the
exact files that upload_to_gcs.py stages and load_bq.py loads — nothing is
transformed downstream.

Known data quality issues handled here:
  - Embedded \\n in address / HEI name fields → collapsed to a single space.
  - Two malformed dates in Transition Autonomous Colleges:
      "3112/2025"  → 2025-12-31
      "31/122025"  → 2025-12-31
  - Date Of Declaration stored as DD-MM-YYYY string → parsed to DATE.
  - Extended validity upto stored as Excel datetime or string → parsed to DATE.

Usage:
  python3 scripts/build_clean.py                 # build all three tables
  python3 scripts/build_clean.py --table naac_fact_colleges   # one only
  python3 scripts/build_clean.py --dry-run       # build in-mem, print summary, write nothing
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, DATA_AS_OF, TABLES, Table


# ─── Cleaning helpers ────────────────────────────────────────────────────────

def _clean_text(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse embedded newlines and extra whitespace in string cells.

    Uses per-value apply rather than .str accessor so non-string values
    (e.g. datetime objects in mixed-type columns) are passed through unchanged.
    """
    for col in df.select_dtypes(include=["object", "string"]).columns:
        df[col] = df[col].apply(
            lambda v: re.sub(r"\s*\n\s*", " ", v).strip() if isinstance(v, str) else v
        )
    return df


def _fix_dirty_dates(series: pd.Series) -> pd.Series:
    """
    Repair the two malformed date strings in Transition Autonomous Colleges:
      "3112/2025"  → "2025-12-31"
      "31/122025"  → "2025-12-31"
    All other values are passed through unchanged.
    """
    def _fix(val):
        if not isinstance(val, str):
            return val
        digits_only = re.sub(r"[^\d/]", "", val)
        if re.match(r"^3112/\d{4}$", digits_only) or re.match(r"^31/12\d{4}$", digits_only):
            year = re.search(r"\d{4}", digits_only).group()
            return f"{year}-12-31"
        return val

    return series.map(_fix)


def _parse_dates(df: pd.DataFrame, date_columns: list[str]) -> pd.DataFrame:
    """
    Parse date columns to Python date objects.

    Universities / Colleges: Date Of Declaration arrives as a DD-MM-YYYY string.
    Transition Autonomous Colleges: Extended validity upto is a mix — Excel
    already parsed most rows as datetime.datetime; 2 rows are dirty strings
    (handled by _fix_dirty_dates). We dispatch per-value to handle both cleanly.
    """
    import datetime as dt

    def _to_date(val):
        if isinstance(val, dt.datetime):
            return val.date()
        if isinstance(val, dt.date):
            return val
        if isinstance(val, str):
            cleaned = _fix_dirty_dates(pd.Series([val.strip()])).iloc[0]
            # Try DD-MM-YYYY first (Universities/Colleges format), then ISO fallback.
            parsed = pd.to_datetime(cleaned, format="%d-%m-%Y", errors="coerce")
            if pd.isnull(parsed):
                parsed = pd.to_datetime(cleaned, errors="coerce")
            return None if pd.isnull(parsed) else parsed.date()
        return None

    for col in date_columns:
        if col not in df.columns:
            continue
        df[col] = df[col].apply(_to_date)
    return df


# ─── Per-table build ─────────────────────────────────────────────────────────

def build(table: Table) -> pd.DataFrame:
    df = pd.read_excel(table.raw_xlsx, sheet_name=table.sheet)

    unknown = set(table.column_renames) - set(df.columns)
    if unknown:
        raise SystemExit(
            f"Sheet '{table.sheet}': rename map references missing columns: {sorted(unknown)}"
        )

    df = df.rename(columns=table.column_renames)
    df = _clean_text(df)
    df = _parse_dates(df, table.date_columns)
    df["data_as_of"] = DATA_AS_OF
    return df


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--table", default=None,
        help="Build only this BQ table name (e.g. naac_fact_colleges)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Build in-mem and print summary; write nothing to disk",
    )
    args = ap.parse_args()

    chosen = TABLES
    if args.table:
        chosen = [t for t in TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")

    if not args.dry_run:
        CLEAN.mkdir(parents=True, exist_ok=True)

    print(f"NAAC build_clean   ({'dry-run' if args.dry_run else f'writing to {CLEAN}'})")
    for t in chosen:
        df = build(t)
        print(f"  {t.sheet!r}: {len(df):,} rows × {len(df.columns)} cols → {t.local_path.name}")
        if args.dry_run:
            print(df.head(2).to_string())
            print()
        else:
            df.to_parquet(t.local_path, index=False)
            print(f"    wrote {t.local_path}")

    print("✓ done.")


if __name__ == "__main__":
    main()
