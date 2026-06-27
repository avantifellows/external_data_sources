#!/usr/bin/env python3
"""
Clean and reshape UBSE Grade 10 board results (2026+).

Reads:   raw/G10th _ UBSE Board data 2026.xlsx  (sheet: HS_NET)
Writes:  clean/grade10_clean.csv

Transformations:
  - Wide format (6 subject slots per row) → long format
    (one row per student per subject; empty slots dropped)
  - SEX:   1 → Male, 2 → Female, 3 → Others
  - CASTE: 1 → SC, 2 → ST, 3 → OBC, 4 → General
  - RESULT normalised to consistent capitalisation across years
    (FAIL/FAILED → Fail, PASS → Pass, etc.)

Grain: (exam_year, roll_no, subject_slot)

Usage:
    python3 scripts/clean_grade10.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import GRADE10_CLEAN, RAW_GRADE10_FILES

# ── Column renames: raw → canonical ───────────────────────────────────────────

COLUMN_RENAMES = {
    "DISTT":     "district_code",
    "SCHOOL":    "school_code",
    "ROLL":      "roll_no",
    "REGCD":     "registration_no",
    "CNAME":     "student_name",
    "FNAME":     "father_name",
    "MNAME":     "mother_name",
    "DOB":       "date_of_birth",
    "CASTE":     "caste",
    "SEX":       "gender",
    "SCHTYPE":   "school_type",
    "TOTMKSOBT": "total_marks_obtained",
    "TOTMAXMKS": "total_max_marks",
    "RESULT":    "result",
    "DIVISION":  "division",
    "GRACE":     "grace_marks",
}

SEX_MAP = {"1": "Male", "2": "Female", "3": "Others"}

CASTE_MAP = {"1": "SC", "2": "ST", "3": "OBC", "4": "General"}

RESULT_MAP = {
    "PASS":       "Pass",
    "PASSED IN":  "Pass (Compartment)",
    "FAIL":       "Fail",
    "FAILED":     "Fail",
    "ABSENT":     "Absent",
    "CANCELLED":  "Cancelled",
    "W-INCOMPLE": "Withheld",
    "U-INCOMPLE": "Withheld",
    "INCOMPLETE": "Incomplete",
    "WE/WK":      "WE/WK",
}

# Subject-slot column prefixes present in Grade 10
# Each slot n has: SUBnNAME, SUBnTHMKS, SUBnPRAMKS, SUBnINTMKS, SUBnTOT, SUBnRES, SUBnGRADE
_N_SLOTS = 6

OUTPUT_COLS = [
    "exam_year",
    "district_code", "school_code", "roll_no", "registration_no",
    "student_name", "father_name", "mother_name", "date_of_birth",
    "gender", "caste", "school_type",
    "subject_slot", "subject_name",
    "theory_marks", "practical_marks", "internal_marks",
    "subject_total", "subject_result", "subject_grade",
    "total_marks_obtained", "total_max_marks",
    "result", "division", "grace_marks",
]

# Columns that belong to subject slots — excluded from the base row
_SLOT_PREFIXES = tuple(f"SUB{n}" for n in range(1, _N_SLOTS + 1))


def _unpivot_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """Convert wide subject slots into one row per student per subject."""
    base_cols = [c for c in df.columns if not c.startswith(_SLOT_PREFIXES)]
    frames = []

    for n in range(1, _N_SLOTS + 1):
        name_col = f"SUB{n}NAME"
        if name_col not in df.columns:
            continue

        slot = df[base_cols].copy()
        slot["subject_slot"]    = n
        slot["subject_name"]    = df[name_col]
        slot["theory_marks"]    = df.get(f"SUB{n}THMKS")
        slot["practical_marks"] = df.get(f"SUB{n}PRAMKS")
        slot["internal_marks"]  = df.get(f"SUB{n}INTMKS")
        slot["subject_total"]   = df.get(f"SUB{n}TOT")
        slot["subject_result"]  = df.get(f"SUB{n}RES")
        slot["subject_grade"]   = df.get(f"SUB{n}GRADE")

        frames.append(slot[slot["subject_name"].notna()])

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=base_cols)


def _load_year(raw) -> pd.DataFrame:
    print(f"  Reading {raw.file!r} sheet {raw.sheet!r} ...")
    df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)

    df = df.rename(columns=COLUMN_RENAMES)
    df["gender"] = df["gender"].map(SEX_MAP).fillna(df["gender"])
    df["caste"]  = df["caste"].map(CASTE_MAP).fillna(df["caste"])
    df["result"] = df["result"].map(RESULT_MAP).fillna(df["result"])

    df = _unpivot_subjects(df)
    df.insert(0, "exam_year", str(raw.exam_year))

    print(f"    → {len(df):,} subject rows")
    return df


def main() -> None:
    frames = []
    for raw in RAW_GRADE10_FILES:
        if not raw.local_path.exists():
            print(f"WARN: file not found, skipping: {raw.local_path}")
            continue
        frames.append(_load_year(raw))

    if not frames:
        print("ERROR: no input files found.")
        sys.exit(1)

    out_df = pd.concat(frames, ignore_index=True)

    for col in OUTPUT_COLS:
        if col not in out_df.columns:
            out_df[col] = pd.NA
    out_df = out_df[OUTPUT_COLS]

    print(f"\nTotal: {len(out_df):,} rows × {len(out_df.columns)} columns")

    out = GRADE10_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"Written to {out}")
    print("\nDone.")


if __name__ == "__main__":
    main()
