#!/usr/bin/env python3
"""
Turn the NEET-2026 matrix CSV into the clean parquet loaded to BigQuery.

Input : the matrix CSV produced by futures-v2/neet/matrix_2026/builders/neet_matrix_merge_all.py
Output: clean/neet_marks_matrix_2026.parquet  (370 rows, grain = state x category)

TWO SHAPE CHANGES vs the CSV, both for queryability:

1. data_status is SPLIT. In the CSV it is one prose field carrying both a verdict and
   its justification, e.g.
     "INDICATIVE / PARTIAL — OCR of rotated DTE scan; only ~12 of 66+ rows recovered,
      so the TRUE FLOOR IS LOWER than shown"
   Up to 605 characters, which is unusable in a WHERE clause. Split into:
     data_status       short enum: VERIFIED / INDICATIVE / INDICATIVE_PARTIAL /
                       N_A_NO_QUOTA / NO_DATA / BLANKED_THIN_POOL
     data_status_note  the full original prose, kept verbatim — it is the provenance
                       and must not be lost
2. Marks/rank columns become nullable INT64 rather than strings. A blank cell means
   "we have no number", which is NOT the same as zero, so blanks stay NULL.

Usage: python3 scripts/build_parquet.py --csv <path to neet_2026_matrix_all.csv>
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, SNAPSHOT, TABLES

# Prose prefix -> short enum. Order matters: the two-word INDICATIVE / PARTIAL must be
# tested before the bare INDICATIVE.
_STATUS_RULES: list[tuple[str, str]] = [
    (r"^INDICATIVE\s*/\s*PARTIAL", "INDICATIVE_PARTIAL"),
    (r"^INDICATIVE", "INDICATIVE"),
    (r"^VERIFIED", "VERIFIED"),
    (r"^N/A", "N_A_NO_QUOTA"),      # the state does not operate this category at all
    (r"^NO DATA", "NO_DATA"),        # no usable source for this state/UT
    (r"^BLANKED", "BLANKED_THIN_POOL"),  # a pool too thin to publish (n=1)
]

INT_COLS = [
    "B2b_qualifying_marks_2026",
    "B1a_MBBS_marks_2025", "B1a_MBBS_AIR_2025",
    "B1a_MBBS_marks_2026est", "B1a_MBBS_AIR_2026est",
    "B1b_BDS_marks_2025", "B1b_BDS_AIR_2025",
    "B1b_BDS_marks_2026est", "B1b_BDS_AIR_2026est",
]


def classify(note: str) -> str:
    text = str(note or "").strip()
    for pattern, label in _STATUS_RULES:
        if re.match(pattern, text, re.I):
            return label
    return "UNKNOWN"


def build(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype=str).fillna("")
    df["snapshot"] = SNAPSHOT
    df["data_status_note"] = df["data_status"].str.strip()
    df["data_status"] = df["data_status_note"].map(classify)

    for col in INT_COLS:
        # blank -> NULL, never 0: "no number" and "zero marks" are different facts
        df[col] = pd.to_numeric(df[col].replace("", pd.NA), errors="coerce").astype("Int64")

    df["source_round"] = df["source_round"].str.strip()
    return df[[
        "snapshot", "state", "category",
        "B2b_qualifying_marks_2026",
        "B1a_MBBS_marks_2025", "B1a_MBBS_AIR_2025",
        "B1a_MBBS_marks_2026est", "B1a_MBBS_AIR_2026est",
        "B1b_BDS_marks_2025", "B1b_BDS_AIR_2025",
        "B1b_BDS_marks_2026est", "B1b_BDS_AIR_2026est",
        "source_round", "data_status", "data_status_note",
    ]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, type=Path)
    args = ap.parse_args()

    df = build(args.csv)
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = TABLES[0].local_path
    df.to_parquet(out, index=False)

    print(f"neet_matrix → {out.name}: {len(df):,} rows")
    print(f"  tracks (state/UT + All India) : {df['state'].nunique()}")
    print(f"  categories per track          : {df['category'].nunique()}")
    print(f"  with an MBBS 2026 estimate    : {int(df['B1a_MBBS_marks_2026est'].notna().sum())}")
    print("  data_status:")
    for label, n in df["data_status"].value_counts().items():
        print(f"    {label:<22} {n:>4}")
    assert (df.groupby(["state", "category"]).size() == 1).all(), "grain violated"
    assert "UNKNOWN" not in set(df["data_status"]), "unclassified data_status"


if __name__ == "__main__":
    main()
