"""
build_jee_main_candidate_details.py — NTA JEE-Main candidate-details export -> clean table.

NTA's JEE-Main candidate-details file lists, per applicant, the JNV school they sit from and their
Class-12 qualification (board, marks/CGPA, passing year). This is the appno -> JNV-school mapping that
the downstream JEE-results export dropped for some years (Issue #26), kept here as its own clean table.

Grain: one row per (test_year, application_no). Currently 2025 only (12,655 candidates); add years by
extending FILES. Note: this is registration/qualification data, NOT JEE scores — join to
jnv_fact_jee_results / the production JEE fact on application_no for results.

Run:  python3 scripts/build_jee_main_candidate_details.py [--raw DIR]
Output: clean/jnv_fact_jee_main_candidate_details.parquet
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = Path(os.environ.get("JNV_RAW", ROOT / "raw" / "jee_mains"))
CLEAN = ROOT / "clean"

FILES = {"2025": "2025 NTA JNV - JEE Main.csv"}

COLMAP = {
    "applicationNo": "application_no", "rollno": "roll_no",
    "School_or_CollegeName_Address": "school_name", "QualState": "qual_state",
    "QualDistrict": "qual_district", "School_Board": "school_board",
    "Type_of_SchoolorCollege": "school_type", "yearOfPassing": "year_of_passing_12",
    "obtainedMark": "twelfth_obtained_marks", "totalMark": "twelfth_total_marks",
    "percentageOfMarks": "twelfth_percentage", "CGPAValue": "cgpa_value",
    "CGPAMaxPointScale": "cgpa_max_scale", "CGPAPercentage": "cgpa_percentage",
    "passingStatus": "passing_status", "PlaceofSchool": "place_of_school", "FeeStatus": "fee_status",
}
NUMERIC = ["twelfth_obtained_marks", "twelfth_total_marks", "twelfth_percentage",
           "cgpa_value", "cgpa_max_scale", "cgpa_percentage"]


def load_year(year: str, fname: str, raw: Path) -> pd.DataFrame:
    df = pd.read_csv(raw / fname, dtype=str, keep_default_na=False)
    df.columns = df.columns.str.replace("﻿", "", regex=False).str.strip()    # drop BOM / whitespace
    df = df.rename(columns=COLMAP)
    df = df[[c for c in df.columns if c in COLMAP.values()]].copy()
    df["test_year"] = year
    for c in NUMERIC:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    a = ap.parse_args()
    raw = Path(a.raw)
    out = pd.concat([load_year(y, f, raw) for y, f in FILES.items()], ignore_index=True)
    cols = ["test_year", "application_no", "roll_no", "school_name", "qual_state", "qual_district",
            "school_board", "school_type", "year_of_passing_12"] + NUMERIC + ["passing_status",
            "place_of_school", "fee_status"]
    out = out[[c for c in cols if c in out.columns]]
    CLEAN.mkdir(exist_ok=True)
    dest = CLEAN / "jnv_fact_jee_main_candidate_details.parquet"
    out.to_parquet(dest, index=False)
    print(f"wrote {dest}  ({len(out):,} rows)")
    print(f"  distinct application_no: {out.application_no.nunique():,}")
    print(f"  with school_name: {(out.school_name.astype(str).str.strip() != '').sum():,}")
    print(f"  boards: {out.school_board.value_counts().head(4).to_dict()}")
    print(f"  passing_status: {out.passing_status.value_counts().head(4).to_dict()}")


if __name__ == "__main__":
    main()
