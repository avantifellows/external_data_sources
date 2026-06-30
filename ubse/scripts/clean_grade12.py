#!/usr/bin/env python3
"""
Clean and reshape UBSE Grade 12 board results (2026+).

Reads:   raw/G12th _UBSE Board data - 2026.xlsx  (sheet: int_net)
Writes:  clean/grade12_clean.csv

Transformations:
  - Wide format (6 subject slots per row) → long format
    (one row per student per subject; empty slots dropped)
  - SEX:    1 → Male, 2 → Female, 3 → Others
  - CASTE:  1 → SC, 2 → ST, 3 → OBC, 4 → General
  - GROUP (stream): A → Arts, B → Science, C → Commerce,
                    F1 → Vocational (Year 1), F2 → Vocational (Year 2)
  - RESULT normalised (FAILED → Fail, PASS → Pass, PADL → Pass (ADL), etc.)

Note: Grade 12 column order within each slot is THMKS, INTMKS, PRAMKS
      (different from Grade 10 which has THMKS, PRAMKS, INTMKS).
      Both are read by name so this makes no difference in processing.

Grain: (exam_year, roll_no, subject_slot)

Usage:
    python3 scripts/clean_grade12.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import GRADE12_CLEAN, RAW_GRADE12_FILES

# ── Column renames: raw → canonical ───────────────────────────────────────────

COLUMN_RENAMES = {
    "DISTT":     "district_code",
    "SCHOOL":    "school_code",
    "ROLL":      "roll_no",
    "REGCD":     "registration_no",
    "CNAME":     "student_name",
    "FNAME":     "father_name",
    "MNAME":     "mother_name",
    "GROUP":     "stream",
    "CASTE":     "caste",
    "SEX":       "gender",
    "SCHTYPE":   "school_type",
    "F1_TOTAL":  "f1_total",
    "F2_TOTAL":  "f2_total",
    "TOTMKSOBT": "total_marks_obtained",
    "TOTMAXMKS": "total_max_marks",
    "RESULT":    "result",
    "DIVISION":  "division",
    "GRACE":     "grace_marks",
}

SEX_MAP = {"1": "Male", "2": "Female", "3": "Others"}

CASTE_MAP = {"1": "SC", "2": "ST", "3": "OBC", "4": "General"}

STREAM_MAP = {
    "A":  "Arts",
    "B":  "Science",
    "C":  "Commerce",
    "F1": "Vocational (Year 1)",
    "F2": "Vocational (Year 2)",
}

RESULT_MAP = {
    "PASS":         "Pass",
    "PASSED IN":    "Pass (Compartment)",
    "FAIL":         "Fail",
    "FAILED":       "Fail",
    "ABSENT":       "Absent",
    "CANCELLED":    "Cancelled",
    "PADL":         "Pass (ADL)",
    "W-INCOMPLE":   "Withheld",
    "W-INCOMPLETE": "Withheld",
    "INCOMPLETE":   "Incomplete",
}

_N_SLOTS = 6

OUTPUT_COLS = [
    "exam_year",
    "district_code", "school_code", "roll_no", "registration_no",
    "student_name", "father_name", "mother_name",
    "gender", "caste", "stream", "school_type",
    "subject_slot", "subject_name",
    "theory_marks", "internal_marks", "practical_marks",
    "subject_total", "subject_result", "subject_grade",
    "f1_total", "f2_total",
    "total_marks_obtained", "total_max_marks",
    "result", "division", "grace_marks",
]

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
        slot["internal_marks"]  = df.get(f"SUB{n}INTMKS")
        slot["practical_marks"] = df.get(f"SUB{n}PRAMKS")
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
    df["stream"] = df["stream"].map(STREAM_MAP).fillna(df["stream"])
    df["result"] = df["result"].map(RESULT_MAP).fillna(df["result"])

    df = _unpivot_subjects(df)
    df.insert(0, "exam_year", str(raw.exam_year))

    print(f"    → {len(df):,} subject rows")
    return df


def main() -> None:
    frames = []
    for raw in RAW_GRADE12_FILES:
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

    out = GRADE12_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"Written to {out}")
    print("\nDone.")


if __name__ == "__main__":
    main()
