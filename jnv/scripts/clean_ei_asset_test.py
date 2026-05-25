#!/usr/bin/env python3
"""
Prepare EI Asset Test data for BQ load.

Reads:
    raw/ei_asset_test/EI_Asset_Test.xlsx  (sheet: "student_scores")

Writes:
    clean/ei_asset_test_clean.csv

Transformations applied:
  - Column names lowercased (e.g. Caste → caste, assetD_assessment_id → assetd_assessment_id)

Usage:
    python3 scripts/clean_ei_asset_test.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import EI_ASSET_TEST_CLEAN, RAW_EI_ASSET_TEST_FILES


COLUMN_RENAMES = {
    "firstname":  "first_name",
    "lastname":   "last_name",
    "subjectno":  "subject_no",
}


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
    raw = RAW_EI_ASSET_TEST_FILES[0]

    if not raw.local_path.exists():
        print(f"ERROR: raw file not found: {raw.local_path}")
        sys.exit(1)

    print(f"Reading {raw.file!r} sheet {raw.sheet!r} ...")
    df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
    df = _sanitize_columns(df)
    df = df.rename(columns=COLUMN_RENAMES)
    print(f"  {len(df):,} rows × {len(df.columns)} columns")

    out = EI_ASSET_TEST_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"  Written to {out}")

    print("\nDone.")


if __name__ == "__main__":
    main()
