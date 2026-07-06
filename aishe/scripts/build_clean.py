"""
Build clean parquet files from the raw AISHE HE Directory Excel exports.

Reads each Excel file from aishe/raw/, skips the title/date header rows,
normalises column names to canonical snake_case, strips whitespace, and
writes a clean parquet to aishe/clean/.

This is a raw passthrough: every column in the output comes verbatim from
the source export (only renamed to snake_case and whitespace-trimmed). No
derived/computed columns are added — downstream analysis owns any
classification or enrichment.

The clean parquets are the inputs to upload_to_gcs.py and load_bq.py.
Raw Excel files are gitignored — they must be downloaded manually from
https://dashboard.aishe.gov.in/hedirectory/#/hedirectory and placed in
aishe/raw/ before running this script.

Requires: pandas, openpyxl, pyarrow

Usage:
  python3 scripts/build_clean.py                              # all five tables
  python3 scripts/build_clean.py --table aishe_fact_colleges  # one only
  python3 scripts/build_clean.py --dry-run                    # print stats, no write
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, TABLE_BY_NAME, TABLES, Table



# ─── Core pipeline ───────────────────────────────────────────────────────────

def _read_and_clean(table: Table) -> pd.DataFrame:
    """Read raw Excel → clean DataFrame with canonical column names."""
    if not table.raw_path.exists():
        raise SystemExit(
            f"Missing raw file: {table.raw_path}\n"
            f"Download from https://dashboard.aishe.gov.in/hedirectory/#/hedirectory "
            f"and place in aishe/raw/ as '{table.raw_file}'."
        )

    # Extract source snapshot date from the dashboard-generated header row
    _hdr = pd.read_excel(table.raw_path, header=None, nrows=2, dtype=str)
    _match = re.search(r"(\d{1,2}-\d{1,2}-\d{4})", _hdr.iloc[1, 0] or "")
    _as_on_date = pd.to_datetime(_match.group(1), dayfirst=True) if _match else pd.NaT

    df = pd.read_excel(
        table.raw_path,
        header=table.header_row,  # skip title + date rows; actual headers at row 2
        dtype=str,                 # keep everything as string; avoids float coercion on codes
    )

    # Drop fully-empty rows/columns (Excel exports often have trailing empties)
    df = df.dropna(how="all").reset_index(drop=True)
    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns.str.strip() != ""]

    # Strip whitespace from all headers and string values
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes("object").columns:
        df[col] = df[col].str.strip()

    # Validate expected source columns before renaming
    missing = set(table.column_renames) - set(df.columns)
    if missing:
        raise SystemExit(
            f"{table.raw_file}: expected columns not found: {sorted(missing)}\n"
            f"Actual columns: {list(df.columns)}"
        )

    df = df.rename(columns=table.column_renames)

    # Cast serial-number columns from float string to nullable Int64
    if "sno" in df.columns:
        df["sno"] = pd.to_numeric(df["sno"], errors="coerce").astype("Int64")

    # Normalise unknown year values ('-') to None
    if "year_of_establishment" in df.columns:
        df["year_of_establishment"] = df["year_of_establishment"].replace("-", None)

    # Normalise management '-' to None
    if "management" in df.columns:
        df["management"] = df["management"].replace("-", None)

    # Provenance columns
    df["aishe_as_on_date"] = _as_on_date   # when the AISHE dashboard snapshot was taken
    df["ingested_at"] = pd.Timestamp.utcnow()  # when this pipeline run processed it

    return df


def _build(table: Table, dry_run: bool) -> None:
    df = _read_and_clean(table)
    n_rows, n_cols = df.shape

    if dry_run:
        print(f"  [dry-run] {table.bq_name}: {n_rows:,} rows × {n_cols} cols")
        print(f"    columns: {list(df.columns)}")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(table.clean_path, index=False)
    print(f"  {table.bq_name}: {n_rows:,} rows × {n_cols} cols → {table.clean_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--table",
        default=None,
        help="Build only this BQ table (e.g. aishe_fact_colleges).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Read + validate locally; print stats but don't write parquet.",
    )
    args = ap.parse_args()

    if args.table:
        if args.table not in TABLE_BY_NAME:
            raise SystemExit(
                f"Unknown table {args.table!r}. Known: {list(TABLE_BY_NAME)}"
            )
        chosen = [TABLE_BY_NAME[args.table]]
    else:
        chosen = TABLES

    print(
        f"AISHE HE Directory → aishe/clean/   "
        f"({'dry-run' if args.dry_run else 'writing parquet'})"
    )
    for t in chosen:
        _build(t, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
