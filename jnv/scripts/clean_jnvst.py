#!/usr/bin/env python3
"""
Prepare JNVST 2018 data for BQ load.

Reads:
    raw/jnvst/JNVST 2018 11-09-2025.xlsx  (sheet: "JNVST 2018")

Writes:
    clean/jnvst_clean.csv

Transformations applied:
  - Column names lowercased and renamed to descriptive names (see COLUMN_RENAMES)
  - area:     R → rural, U → urban
  - gender:   B → Male, G → Female
  - category: G → Gen, C → SC, O → OBC, T → ST
  - test_year column prepended (value: 2018)

Usage:
    python3 scripts/clean_jnvst.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import JNVST_CLEAN, RAW_JNVST_FILES

TEST_YEAR = "2018"

COLUMN_RENAMES = {
    "area":                 "area",           # R/U → rural/urban (mapped below)
    "blk":                  "block",
    "centre_no":            "centre_no",      # hierarchy: state → district → block → centre
    "rroll":                "roll_no",
    "rank":                 "district_rank",
    "sex":                  "gender",         # B → Male, G → Female (mapped below)
    "cat":                  "category",
    "language":             "language",
    "sel":                  "sel",
    "total":                "total_marks",
    "mat_mrk":              "mental_ability_marks",
    "arith_mrk":            "arithmetic_marks",
    "lng_mrk":              "language_marks",
    "qualified":            "qualified",
    "name":                 "name",
    "medium":               "medium_of_education",
    "absflg":               "absent_flag",
    "win":                  "win",
    "osel":                 "osel",
    "handi":                "handicapped",
    "selqt":                "selqt",
    "opencd":               "open_code",
    "serial":               "serial",
    "wait":                 "waitlist",
    "state_distt_code":     "state_district_code",
    "state":                "state",
    "district":             "district",
    "standardized_scores":  "standardized_scores",
    "total_bucket_10":      "total_marks_bucket_10",
    "mat_mrk_bucket_10":    "mental_ability_marks_bucket_10",
    "arith_mrk_bucket_10":  "arithmetic_marks_bucket_10",
    "lng_mrk_bucket_10":    "language_marks_bucket_10",
}

AREA_MAP     = {"R": "rural",   "U": "urban"}
GENDER_MAP   = {"B": "Male",   "G": "Female"}
CATEGORY_MAP = {"G": "Gen", "C": "SC", "O": "OBC", "T": "ST"}


def _sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, strip whitespace, spaces→underscores, drop non-word chars."""
    def clean(name: str) -> str:
        name = name.strip()
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", "_", name)
        return name.lower()

    df.columns = [clean(c) for c in df.columns]
    return df


def main() -> None:
    raw = RAW_JNVST_FILES[0]

    if not raw.local_path.exists():
        print(f"ERROR: raw file not found: {raw.local_path}")
        sys.exit(1)

    print(f"Reading {raw.file!r} sheet {raw.sheet!r} ...")
    df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
    df = _sanitize_columns(df)
    df = df.rename(columns=COLUMN_RENAMES)

    df["area"]     = df["area"].map(AREA_MAP).fillna(df["area"])
    df["gender"]   = df["gender"].map(GENDER_MAP).fillna(df["gender"])
    df["category"] = df["category"].map(CATEGORY_MAP).fillna(df["category"])

    df.insert(0, "test_year", TEST_YEAR)
    print(f"  {len(df):,} rows × {len(df.columns)} columns")

    out = JNVST_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"  Written to {out}")

    print("\nDone.")


if __name__ == "__main__":
    main()
