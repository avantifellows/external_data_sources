#!/usr/bin/env python3
"""
Prepare pb_scert SOE & RSMS Admission Test merit list for BQ load.

Reads:
    raw/SOE & RSMS Admission Test Merit List_ 2024-26 (3 years).xlsx
        (sheet: Student List)

Writes:
    clean/merit_list_clean.csv

Transformations:
  - Column renames to snake_case canonical names
  - MIS ID / E-Punjab ID dropped (all zeros — no usable data)
  - Gender normalised: FEMALE → Female, MALE → Male, TRANSGENDER* → Others
  - Category normalised: GENERAL → General, BC → OBC, EWS → EWS, SC/ST unchanged
  - Qualification status title-cased
  - Applied For title-cased
  - G10 board roll number: sentinel value "\\N" replaced with null

Usage:
    python3 scripts/clean_merit_list.py
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import MERIT_LIST_CLEAN, RAW_MERIT_LIST_FILES


COLUMN_RENAMES = {
    "Academic Year":                            "academic_year",
    "Exam Application number":                  "exam_application_no",
    "G10 board roll number":                    "g10_board_roll_no",
    "Student Name":                             "student_name",
    "Date of Birth":                            "date_of_birth",
    "Gender":                                   "gender",
    "Category":                                 "category",
    "G10 School\nUDISE Code":                   "g10_school_udise_code",
    "G10 School Name":                          "g10_school_name",
    "G10 School\nBoard":                        "g10_school_board",
    "Reasoning Marks":                          "reasoning_marks",
    "Subject Marks":                            "subject_marks",
    "Total Marks- 150":                         "total_marks_150",
    "Qualifiication for Meritorious / SOE ":    "qualification_status",   # sic: double-i, trailing space
    "Applied For":                              "applied_for",
    "Class":                                    "class",
}

# MIS ID / E-Punjab ID — all zeros, no usable information
COLUMNS_TO_DROP = ["MIS ID / E-Punjab ID\n(If Available)"]

_GENDER_MAP = {
    "female":      "Female",
    "male":        "Male",
    "transgender": "Others",
    "trans":       "Others",
}

_CATEGORY_MAP = {
    "general":  "General",
    "sc":       "SC",
    "st":       "ST",
    "obc":      "OBC",
    "bc":       "OBC",       # Punjab uses BC; maps to standard OBC
    "obc/bc":   "OBC",       # combined value used in source
    "ews":      "EWS",
}

_QUALIFICATION_MAP = {
    "qualified":               "Qualified",
    "not qualified":           "Not Qualified",
    "provisionally qualified": "Provisionally Qualified",
    "absent":                  "Absent",
    "cancelled":               "Cancelled",
}

_APPLIED_FOR_MAP = {
    "both":                "Both",
    "school of eminence":  "School of Eminence",
    "meritorious":         "Meritorious",
}


def _normalize_gender(val: str | None) -> str | None:
    if val is None or (isinstance(val, float)):
        return None
    key = val.strip().lower()
    # match prefix for TRANSGENDER (MALE) / TRANSGENDER (FEMALE) variants
    for raw_key, mapped in _GENDER_MAP.items():
        if key.startswith(raw_key):
            return mapped
    return val.strip()


def _normalize_category(val: str | None) -> str | None:
    if val is None or (isinstance(val, float)):
        return None
    key = "".join(val.lower().split())
    for raw_key, mapped in _CATEGORY_MAP.items():
        if "".join(raw_key.split()) == key:
            return mapped
    return val.strip()


def _normalize_lookup(val: str | None, mapping: dict) -> str | None:
    if val is None or (isinstance(val, float)):
        return None
    key = val.strip().lower()
    return mapping.get(key, val.strip())


def main() -> None:
    raw = RAW_MERIT_LIST_FILES[0]

    if not raw.local_path.exists():
        print(f"ERROR: raw file not found: {raw.local_path}")
        sys.exit(1)

    print(f"Reading {raw.file!r} sheet {raw.sheet!r} ...")
    df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
    print(f"  {len(df):,} rows × {len(df.columns)} columns")

    # Drop columns with no usable data
    df = df.drop(columns=[c for c in COLUMNS_TO_DROP if c in df.columns])

    # Rename to canonical snake_case names
    df = df.rename(columns=COLUMN_RENAMES)

    # Null sentinel in G10 board roll number
    df["g10_board_roll_no"] = df["g10_board_roll_no"].replace(r"\\N", None).replace("\\N", None)
    df.loc[df["g10_board_roll_no"].isna(), "g10_board_roll_no"] = None

    # Normalise categorical columns
    df["gender"]               = df["gender"].apply(_normalize_gender)
    df["category"]             = df["category"].apply(_normalize_category)
    df["qualification_status"] = df["qualification_status"].apply(
        lambda v: _normalize_lookup(v, _QUALIFICATION_MAP)
    )
    df["applied_for"]          = df["applied_for"].apply(
        lambda v: _normalize_lookup(v, _APPLIED_FOR_MAP)
    )

    print("\nValue distributions after normalisation:")
    for col in ("academic_year", "gender", "category", "qualification_status", "applied_for", "class"):
        if col in df.columns:
            print(f"\n  {col}:")
            for val, cnt in df[col].value_counts(dropna=False).items():
                print(f"    {repr(val):45s} {cnt:>8,}")

    out = MERIT_LIST_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nWritten {len(df):,} rows to {out}")
    print("\nDone.")


if __name__ == "__main__":
    main()
