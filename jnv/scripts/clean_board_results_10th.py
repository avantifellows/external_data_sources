#!/usr/bin/env python3
"""
Clean and reshape CBSE 10th board results for JNV students (2022–2025).

Reads:   raw/board_results_10th/JNV10{YY}.xlsx  (one file per year)
Writes:  clean/board_results_10th_clean.csv

Transformations:
  - Column names normalized and renamed (see COLUMN_RENAMES)
  - Wide format (up to 7 subject slots per row) → long format
    (one row per student per subject; null slots dropped)
  - gender:   M → Male, F → Female
  - category: C → SC, T → ST, O → OBC, G → Gen

Usage:
    python3 scripts/clean_board_results_10th.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BOARD_RESULTS_10TH_CLEAN, RAW_BOARD_RESULTS_10TH_FILES

# ── Year configs ───────────────────────────────────────────────────────────────

YEAR_CONFIGS = [
    {"exam_year": 2022, "raw": RAW_BOARD_RESULTS_10TH_FILES[0]},
    {"exam_year": 2023, "raw": RAW_BOARD_RESULTS_10TH_FILES[1]},
    {"exam_year": 2024, "raw": RAW_BOARD_RESULTS_10TH_FILES[2]},
    {"exam_year": 2025, "raw": RAW_BOARD_RESULTS_10TH_FILES[3]},
]

# Applied on raw column names before sanitization to fix year-specific quirks.
# 2024 renamed student/location cols; 2025 has unnamed region/state columns.
YEAR_COLUMN_FIXES = {
    2024: {
        "JNV Region":   "region",
        "JNV State":    "state",
        "JNV Name":     "school_district",
        "Student Name": "cname",
        # Slots 3–5 have non-standard subject name columns in this year's file
        "Subject Code": "sub3",
        "Matheamtics":  "sname3",   # typo in source — Mathematics
        "Science.1":    "sname4",
        "Social Science": "sname5",
    },
    2025: {
        "s":     "region",       # JNV region (e.g. "Jaipur")
        " ":     "state_full",   # full state name (e.g. "Delhi (UT)")
        " .1":   "school_district",
        " .2":   "_drop_1_",
        "State": "_drop_2_",     # duplicate of STATE,C,2 after sanitization
    },
}

# Excel formula error strings — replaced with NaN after loading
_EXCEL_ERRORS = {"#REF!", "#VALUE!", "#N/A", "#NAME?", "#DIV/0!", "#NULL!", "#NUM!"}

# Maps sanitized raw column names → canonical output names.
# Subject-slot columns (sub1..7, sname1..7, mrk*) are handled separately.
COLUMN_RENAMES = {
    # Student identity
    "rroll":        "roll_number",
    "cname":        "student_name",
    "mname":        "mother_name",
    "fname":        "father_name",
    "dob":          "date_of_birth",
    "sex":          "gender",
    "scst":         "category",
    "hand":         "disability",
    "admid":        "admission_id",
    # School
    "sch":          "school_code",
    "abbr_name":    "school_name",
    "schtype":      "school_type",
    "cent":         "centre_code",
    # Location
    "region":       "region",
    "state":        "state",
    # Exam metadata
    "session":      "session",
    "month":        "exam_month",
    "dateofdecl":   "date_of_declaration",
    "date_rev":     "date_revised",
    # Results (student-level)
    "tmrk":         "total_marks",
    "comptt":       "compartment",
    "rlrw":         "reappear",
    "skill":        "skill_subject",
    "nse":          "nse",
    "nchmct":       "nchmct",
}

GENDER_MAP   = {"M": "Male", "F": "Female"}
CATEGORY_MAP = {"C": "SC", "T": "ST", "O": "OBC", "G": "Gen"}

# Columns that are part of subject slots — excluded from the base row
# and handled in the unpivot step.
_SLOT_RE = re.compile(r"^(sub|sname|mrk|pf|gr)\d")

# Final column order in the output CSV
OUTPUT_COLS = [
    "exam_year", "session",
    "roll_number", "school_code", "school_name", "centre_code",
    "student_name", "mother_name", "father_name", "date_of_birth",
    "gender", "category", "disability",
    "region", "state", "school_type",
    "exam_month", "date_of_declaration", "date_revised",
    "subject_code", "subject_name",
    "theory_marks", "practical_marks", "final_marks",
    "grade", "subject_result",
    "total_marks", "result",
    "compartment", "reappear",
    "admission_id", "skill_subject", "nse", "nchmct",
]


# ── Column normalization ───────────────────────────────────────────────────────

def _sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, strip whitespace, remove DBF-style ',C,N' suffixes, snake_case."""
    def clean(name: str) -> str:
        name = str(name).strip()
        # 2025 files have columns like 'SUB1,C,3' — strip the DBF type annotation
        name = re.sub(r",\s*[a-zA-Z],\s*\d+$", "", name)
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", "_", name)
        return name.lower()

    df.columns = [clean(c) for c in df.columns]
    # Drop duplicate column names (can appear after lowercasing), keep first
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df


# ── Subject unpivot ────────────────────────────────────────────────────────────

def _unpivot_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """Convert 7 wide subject slots into one row per student per subject."""
    base_cols = [c for c in df.columns if not _SLOT_RE.match(c)]
    frames = []

    for n in range(1, 8):
        code_col  = f"sub{n}"
        name_col  = f"sname{n}"
        # Skip slot entirely if neither the code nor name column exists
        if code_col not in df.columns and name_col not in df.columns:
            continue

        slot = df[base_cols].copy()
        slot["subject_code"]    = df.get(code_col)
        slot["subject_name"]    = df.get(name_col)
        slot["theory_marks"]    = df.get(f"mrk{n}1")
        slot["practical_marks"] = df.get(f"mrk{n}2")
        slot["final_marks"]     = df.get(f"mrk{n}3")
        slot["grade"]           = df.get(f"gr{n}")
        slot["subject_result"]  = df.get(f"pf{n}")

        # Drop rows where the student has no subject in this slot
        has_subject = slot["subject_code"].notna() | slot["subject_name"].notna()
        frames.append(slot[has_subject])

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=base_cols)


# ── Per-year loader ────────────────────────────────────────────────────────────

def _load_year(exam_year: int, raw) -> pd.DataFrame:
    path = raw.local_path
    print(f"  Reading {path.name!r} sheet {raw.sheet!r} ...")
    df = pd.read_excel(path, sheet_name=raw.sheet, dtype=str)

    # 1. Fix year-specific column names before general sanitization
    fixes = YEAR_COLUMN_FIXES.get(exam_year, {})
    if fixes:
        df = df.rename(columns=fixes)

    # 2. Drop placeholder columns injected by YEAR_COLUMN_FIXES
    drop_cols = [c for c in df.columns if str(c).startswith("_drop_")]
    df = df.drop(columns=drop_cols, errors="ignore")

    # 3. Sanitize all remaining column names
    df = _sanitize_columns(df)

    # 3a. Replace Excel formula error strings with NaN
    df = df.replace(_EXCEL_ERRORS, pd.NA)

    # 4. Derive result from whichever column the year uses (res or rslt)
    if "res" in df.columns:
        df["result"] = df["res"]
    elif "rslt" in df.columns:
        df["result"] = df["rslt"]
    else:
        df["result"] = pd.NA
    df = df.drop(columns=["res", "rslt"], errors="ignore")

    # 5. Rename to canonical names; dedup in case a year has both a raw column
    #    that matches the canonical name and another that renames to the same name
    #    (e.g. 2023 has both 'school_name' and 'abbr_name', both → 'school_name')
    df = df.rename(columns=COLUMN_RENAMES)
    df = df.loc[:, ~df.columns.duplicated(keep="first")]

    # 6. Unpivot subject slots → long format
    df = _unpivot_subjects(df)

    # 7. Value mappings
    if "gender" in df.columns:
        df["gender"] = df["gender"].map(GENDER_MAP).fillna(df["gender"])
    if "category" in df.columns:
        df["category"] = df["category"].map(CATEGORY_MAP).fillna(df["category"])

    # 8. Prepend exam_year
    df.insert(0, "exam_year", str(exam_year))

    print(f"    → {len(df):,} subject rows")
    return df


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    frames = []
    for cfg in YEAR_CONFIGS:
        raw = cfg["raw"]
        if not raw.local_path.exists():
            print(f"WARN: raw file not found, skipping: {raw.local_path}")
            continue
        frames.append(_load_year(cfg["exam_year"], raw))

    if not frames:
        print("ERROR: no input files found.")
        sys.exit(1)

    out_df = pd.concat(frames, ignore_index=True)

    # Select and order output columns; fill missing ones with NA
    for col in OUTPUT_COLS:
        if col not in out_df.columns:
            out_df[col] = pd.NA
    out_df = out_df[OUTPUT_COLS]

    total_rows = len(out_df)
    print(f"\nTotal: {total_rows:,} rows × {len(out_df.columns)} columns")

    out = BOARD_RESULTS_10TH_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"Written to {out}")
    print("\nDone.")


if __name__ == "__main__":
    main()
