"""
Build the clean MCC AIQ fact from the R1 allotment CSV.

Reads mcc/raw/closing_ranks_aiq_r1_2025.csv (College DB output), splits the
combined `alloted_category` into a clean (category, is_pwd) pair, types the
rank/count columns, stamps the constant cycle year + round, and writes a
single clean parquet to mcc/clean/mcc_fact_closing_ranks.parquet.

`alloted_category` arrives as e.g. 'Open', 'OBC PwD' — a trailing ' PwD'
marks a Person-with-Disability sub-pool. We split it so analysts filter on a
boolean instead of string-matching, and so `category` is the clean 5-value
reservation space (Open/OBC/SC/ST/EWS — MCC's labels; note 'Open' = unreserved,
'OBC' here is OBC-NCL).

Usage:
  python3 scripts/build_clean.py                 # build from raw/, write clean/
  python3 scripts/build_clean.py --dry-run       # build in-mem, summary only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, CYCLE_ROUND, CYCLE_YEAR, RAW, RAW_FILE, TABLES


def build() -> pd.DataFrame:
    src = RAW / RAW_FILE
    if not src.exists():
        raise SystemExit(
            f"missing {src}. Land the College DB output there first "
            "(medical-national-ranks/extracted_data/closing_ranks_aiq_r1_2025.csv)."
        )

    raw = pd.read_csv(src, dtype=str)
    out = pd.DataFrame()
    out["institute"] = raw["institute"].astype("string").str.strip()
    out["course"] = raw["course"].astype("string").str.strip()
    out["quota"] = raw["quota"].astype("string").str.strip()

    cat = raw["alloted_category"].astype("string").str.strip()
    out["is_pwd"] = cat.str.endswith(" PwD").fillna(False).astype(bool)
    out["category"] = cat.str.replace(r"\s*PwD$", "", regex=True).str.strip()

    out["opening_rank"] = pd.to_numeric(raw["opening_rank"], errors="coerce").astype("Int64")
    out["closing_rank"] = pd.to_numeric(raw["closing_rank"], errors="coerce").astype("Int64")
    out["allotted_count"] = pd.to_numeric(raw["allotted_count"], errors="coerce").astype("Int64")

    out["year"] = pd.array([CYCLE_YEAR] * len(out), dtype="Int64")
    out["round"] = pd.array([CYCLE_ROUND] * len(out), dtype="Int64")

    ordered = [
        "institute", "course", "quota", "category", "is_pwd",
        "opening_rank", "closing_rank", "allotted_count", "year", "round",
    ]
    out = out[ordered].drop_duplicates().reset_index(drop=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Build in-mem; write nothing")
    args = ap.parse_args()

    df = build()
    print(
        f"built mcc_fact_closing_ranks: {len(df):,} rows, "
        f"courses {sorted(df['course'].dropna().unique().tolist())}, "
        f"pwd rows {int(df['is_pwd'].sum()):,}, cycle {CYCLE_YEAR} R{CYCLE_ROUND}"
    )

    if args.dry_run:
        print("  [dry-run] not writing")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    dest = TABLES[0].local_path
    df.to_parquet(dest, index=False)
    print(f"  wrote {dest}")


if __name__ == "__main__":
    main()
