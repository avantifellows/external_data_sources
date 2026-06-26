"""
Build clean parquet from the raw KCET cutoff CSV.

Reads kcet/raw/KA_engg_<year>_all_cutoffs_R<round>.csv (produced by
parse_KA_2025.py in the futures-v2 repo), joins college_type from a
supplementary govt-scope CSV, adds constant metadata columns, and writes
kcet/clean/kcet_fact_cutoffs.parquet.

college_type join logic:
  The main cutoff CSV covers all 243 colleges but has no college_type column.
  The govt-scope CSV covers only Govt/Govt-Aided colleges. We left-join on
  college_code and fill unmatched rows with 'Private'.

Raw files expected in kcet/raw/:
  KA_engg_<year>_all_cutoffs_R<round>.csv   — all colleges, all categories
  KA_engg_closing_ranks_govt_<year>.csv     — govt/aided scope, has college_type

Usage:
  python3 scripts/build_clean.py --dry-run   # validate + print stats, no write
  python3 scripts/build_clean.py             # write clean/kcet_fact_cutoffs.parquet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, RAW

# Expected raw filenames
CUTOFFS_GLOB = "KA_engg_*_all_cutoffs_R*.csv"
GOVT_GLOB    = "KA_engg_closing_ranks_govt_*.csv"

# Output columns in order
OUTPUT_COLS = [
    "state",
    "cet_name",
    "stream",
    "year",
    "round",
    "college_code",
    "college_name",
    "college_type",
    "course_name",
    "domicile_pool",
    "category_code",
    "closing_rank",
    "ingested_at",
]


def _find_raw(pattern: str) -> Path:
    matches = sorted(RAW.glob(pattern))
    if not matches:
        raise SystemExit(
            f"No file matching {pattern!r} in {RAW}.\n"
            f"Copy the raw CSV from futures-v2/state_cet/scrape/extracted_data/ "
            f"into kcet/raw/ before running."
        )
    if len(matches) > 1:
        raise SystemExit(
            f"Multiple files match {pattern!r} in {RAW}: {[m.name for m in matches]}\n"
            f"Remove all but the one you want to load."
        )
    return matches[0]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate + print stats; don't write parquet.")
    args = ap.parse_args()

    cutoffs_path = _find_raw(CUTOFFS_GLOB)
    govt_path    = _find_raw(GOVT_GLOB)

    print(f"Reading: {cutoffs_path.name}")
    df = pd.read_csv(cutoffs_path, dtype={"college_code": str})

    print(f"Reading: {govt_path.name}")
    govt = pd.read_csv(govt_path, dtype={"college_code": str})

    # Build college_type lookup from govt file (one row per college_code)
    college_type_map = (
        govt[["college_code", "college_type"]]
        .drop_duplicates("college_code")
        .set_index("college_code")["college_type"]
    )

    # Join college_type; fill unmatched (private) colleges with 'Private'
    df["college_type"] = df["college_code"].map(college_type_map).fillna("Private")

    # Add constant metadata
    df["state"]      = "KARNATAKA"
    df["cet_name"]   = "KCET"
    df["stream"]     = "engineering"
    df["ingested_at"] = pd.Timestamp.utcnow()

    # Ensure correct types
    df["closing_rank"] = pd.to_numeric(df["closing_rank"], errors="coerce")
    df["year"]  = df["year"].astype("Int64")
    df["round"] = df["round"].astype("Int64")

    df = df[OUTPUT_COLS]

    # Sanity checks
    n_rows     = len(df)
    n_colleges = df["college_code"].nunique()
    n_courses  = df["course_name"].nunique()
    n_cats     = df["category_code"].nunique()
    ct_counts  = df.drop_duplicates("college_code")["college_type"].value_counts()

    print(f"\nRows          : {n_rows:,}")
    print(f"Colleges      : {n_colleges}")
    print(f"Courses       : {n_courses}")
    print(f"Category codes: {n_cats}")
    print(f"college_type  :\n{ct_counts.to_string()}")
    print(f"\nYear / round  : {df['year'].unique()} / {df['round'].unique()}")
    print(f"Domicile pools: {sorted(df['domicile_pool'].unique())}")
    print(f"\nSample rows (UVCE CSE):")
    sample = df[(df["college_code"] == "E001") & df["course_name"].str.contains("COMPUTER SCIENCE AND ENGINEERING$", na=False)].head(6)
    print(sample.to_string(index=False))

    if args.dry_run:
        print("\n[dry-run] No file written.")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN / "kcet_fact_cutoffs.parquet"
    df.to_parquet(out_path, index=False)
    print(f"\nWritten: {out_path}  ({n_rows:,} rows)")


if __name__ == "__main__":
    main()
