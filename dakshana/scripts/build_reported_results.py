"""
build_reported_results.py — Dakshana's self-reported JEE/NEET result sheets -> one clean table.

Dakshana shares, per cycle, a result sheet naming every Dakshana student, their Dakshana CoE (the JNV
they were coached at), and their JEE-Main / NEET outcome. This is the AUTHORITATIVE record of who was a
Dakshana student and at which centre — the `student_program='Dakshana CoE'` tag in the warehouse is
patchy, so this sheet is the source of truth for Dakshana attribution (incl. which JNVs were Dakshana in
a given year, before any hand-over to Avanti).

Harmonises the JEE-Main and NEET sheets into one long table with an `exam` + `score_type` discriminator
(JEE score is a PERCENTILE, NEET score is RAW MARKS — never mix). Grain: (test_year, exam, student).
No student_id / application_no in the source — link to Avanti students by name (+ the identity crosswalk).

Run:  python3 scripts/build_reported_results.py [--raw DIR]
Output: clean/dakshana_fact_reported_results.parquet
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = Path(os.environ.get("DAKSHANA_RAW", ROOT / "raw" / "reported"))
CLEAN = ROOT / "clean"

# (filename, exam label, score_type, header colmap). Sheets carry a title in row 1, header in row 2.
JEE = ("Dakshana - JEE-NEET 2025_Result_NVS_16.06.2025.xlsx - JEE Main.csv", "JEE Main", "percentile", {
    "DRN": "drn", "NAME": "student_name", "Gender": "gender", "Cat": "category", "PwD": "pwd",
    "CoE": "coe", "Total %ile": "score_value", "All India Rank": "all_india_rank",
    "Category Rank": "category_rank", "AIR_PwD": "air_pwd", "Cat._PwD": "category_pwd_rank",
    "Qualifying status for JEE Advanced": "qualifying_status"})
NEET = ("Dakshana - 2025- NEET.csv", "NEET", "marks", {
    "Student Name": "student_name", "Gender": "gender", "Category": "category", "PwD": "pwd",
    "CoE": "coe", "Total Marks": "score_value", "All India Rank": "all_india_rank",
    "Category Rank": "category_rank", "Cat. PwD Rank": "category_pwd_rank",
    "Qualifying Status (Q/DNQ)": "qualifying_status"})

OUT_COLS = ["test_year", "exam", "drn", "student_name", "gender", "category", "pwd", "coe",
            "score_type", "score_value", "all_india_rank", "category_rank", "air_pwd",
            "category_pwd_rank", "qualifying_status"]
NUMERIC = ["score_value", "all_india_rank", "category_rank", "air_pwd", "category_pwd_rank"]


def load_sheet(spec, raw: Path, year: str) -> pd.DataFrame:
    fname, exam, score_type, colmap = spec
    df = pd.read_csv(raw / fname, dtype=str, keep_default_na=False, skiprows=1)   # row 1 = title
    df.columns = df.columns.str.replace("﻿", "", regex=False).str.strip()
    df = df.rename(columns=colmap)
    df = df[[c for c in df.columns if c in colmap.values()]].copy()
    df["test_year"], df["exam"], df["score_type"] = year, exam, score_type
    df = df[df.get("student_name", "").astype(str).str.strip() != ""]             # drop blank/footer rows
    for c in OUT_COLS:
        if c not in df.columns:
            df[c] = ""
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[OUT_COLS]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    a = ap.parse_args()
    raw = Path(a.raw)
    out = pd.concat([load_sheet(JEE, raw, "2025"), load_sheet(NEET, raw, "2025")], ignore_index=True)
    CLEAN.mkdir(exist_ok=True)
    dest = CLEAN / "dakshana_fact_reported_results.parquet"
    out.to_parquet(dest, index=False)
    print(f"wrote {dest}  ({len(out):,} rows)")
    print(out.groupby(["exam", "score_type"]).size().to_string())
    print("\nby CoE (the Dakshana-centre attribution):")
    print(out.groupby(["coe", "exam"]).size().unstack(fill_value=0).to_string())
    print(f"\nqualifying_status: {out.qualifying_status.value_counts().to_dict()}")


if __name__ == "__main__":
    main()
