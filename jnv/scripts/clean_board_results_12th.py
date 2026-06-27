#!/usr/bin/env python3
"""
Clean and reshape CBSE 12th board results for JNV students (2022–2025).

Reads:   raw/board_results_12th/JNV12{YY}.xlsx  (one file per year)
Writes:  clean/board_results_12th_clean.csv

Transformations:
  - Column names normalized and renamed (see COLUMN_RENAMES)
  - Wide format → long format (one row per student per subject)
    - Up to 6 main subject slots (sub1..6): full marks + grade
    - Up to 3 internal subject slots (isub1..3): grade only, no marks
    - is_internal flag distinguishes the two types
    - Null slots dropped
  - gender:   M → Male, F → Female
  - category: C → SC, T → ST, O → OBC, G → Gen

Usage:
    python3 scripts/clean_board_results_12th.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BOARD_RESULTS_12TH_CLEAN, RAW_BOARD_RESULTS_12TH_FILES

# ── Year configs ───────────────────────────────────────────────────────────────

YEAR_CONFIGS = [
    {"exam_year": 2022, "raw": RAW_BOARD_RESULTS_12TH_FILES[0]},
    {"exam_year": 2023, "raw": RAW_BOARD_RESULTS_12TH_FILES[1]},
    {"exam_year": 2024, "raw": RAW_BOARD_RESULTS_12TH_FILES[2]},
    {"exam_year": 2025, "raw": RAW_BOARD_RESULTS_12TH_FILES[3]},
]

# Applied on raw column names before sanitization to fix year-specific quirks.
YEAR_COLUMN_FIXES = {
    2022: {
        # The 'stream' column in this year's file contains JNV region names,
        # not academic stream (Science/Commerce/Arts). Remap it to region.
        "stream": "region",
    },
    2023: {
        "REGION": "region",
        "STATE":  "state_full",
        "DISTT":  "district",
    },
    2025: {
        "Region":               "region",
        "State":                "state_full",
        "JNV Name":             "school_district",
        "DUMMY Column":         "_drop_1_",
        " ":                    "_drop_2_",
        "Dummy 10 Roll Number": "roll_number_10th",  # links student to 10th board data
        "Unnamed: 85":          "_drop_3_",
    },
}

# Maps sanitized raw column names → canonical output names.
# Subject-slot columns are handled separately in the unpivot step.
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
    "district":     "district",
    # Exam metadata
    "session":      "session",
    "month":        "exam_month",
    "dateofdecl":   "date_of_declaration",
    "date_rev":     "date_revised",
    "rank":         "school_rank",     # only present in 2022
    # Results (student-level)
    "tmrk":         "total_marks",
    "comptt":       "compartment",
    "rlrw":         "reappear",
    "skill":        "skill_subject",
    "nse":          "nse",
    "nchmct":       "nchmct",
    # 2025-specific
    "roll_number_10th": "roll_number_10th",
}

GENDER_MAP   = {"M": "Male", "F": "Female"}
CATEGORY_MAP = {"C": "SC", "T": "ST", "O": "OBC", "G": "Gen"}

# Slot columns excluded from the base row and handled in unpivot
_MAIN_SLOT_RE     = re.compile(r"^(sub|sname|mrk|pf|gr)\d")
_INTERNAL_SLOT_RE = re.compile(r"^(isub|isname|igr)\d")

# Excel formula error strings → NaN
_EXCEL_ERRORS = {"#REF!", "#VALUE!", "#N/A", "#NAME?", "#DIV/0!", "#NULL!", "#NUM!"}

# Final column order in the output CSV
OUTPUT_COLS = [
    "exam_year", "session",
    "roll_number", "school_code", "school_name", "centre_code",
    "student_name", "mother_name", "father_name", "date_of_birth",
    "gender", "category", "disability",
    "region", "state", "district", "school_type",
    "exam_month", "date_of_declaration", "date_revised",
    "is_internal",
    "subject_code", "subject_name",
    "theory_marks", "practical_marks", "final_marks",
    "grade", "subject_result",
    "total_marks", "result",
    "school_rank",
    "compartment", "reappear",
    "admission_id", "skill_subject", "nse", "nchmct",
    "roll_number_10th",
]


# ── Column normalization ───────────────────────────────────────────────────────

def _sanitize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase, strip whitespace, remove DBF-style ',C,N' suffixes, snake_case."""
    def clean(name: str) -> str:
        name = str(name).strip()
        name = re.sub(r",\s*[a-zA-Z],\s*\d+$", "", name)
        name = re.sub(r"[^\w\s]", "", name)
        name = re.sub(r"\s+", "_", name)
        return name.lower()

    df.columns = [clean(c) for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df


# ── Subject unpivot ────────────────────────────────────────────────────────────

def _unpivot_subjects(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert wide subject slots to long format.
    Main slots (sub1..6): full marks + grade, is_internal=False.
    Internal slots (isub1..3): grade only, is_internal=True.
    """
    slot_cols = [c for c in df.columns if _MAIN_SLOT_RE.match(c) or _INTERNAL_SLOT_RE.match(c)]
    base_cols = [c for c in df.columns if c not in slot_cols]
    frames = []

    # Main subject slots (1–6)
    for n in range(1, 7):
        if f"sub{n}" not in df.columns and f"sname{n}" not in df.columns:
            continue
        slot = df[base_cols].copy()
        slot["is_internal"]     = False
        slot["subject_code"]    = df.get(f"sub{n}")
        slot["subject_name"]    = df.get(f"sname{n}")
        slot["theory_marks"]    = df.get(f"mrk{n}1")
        slot["practical_marks"] = df.get(f"mrk{n}2")
        slot["final_marks"]     = df.get(f"mrk{n}3")
        slot["grade"]           = df.get(f"gr{n}")
        slot["subject_result"]  = df.get(f"pf{n}")
        has_subject = slot["subject_code"].notna() | slot["subject_name"].notna()
        frames.append(slot[has_subject])

    # Internal subject slots (1–3): grade only
    for n in range(1, 4):
        if f"isub{n}" not in df.columns and f"isname{n}" not in df.columns:
            continue
        slot = df[base_cols].copy()
        slot["is_internal"]     = True
        slot["subject_code"]    = df.get(f"isub{n}")
        slot["subject_name"]    = df.get(f"isname{n}")
        slot["theory_marks"]    = pd.NA
        slot["practical_marks"] = pd.NA
        slot["final_marks"]     = pd.NA
        slot["grade"]           = df.get(f"igr{n}")
        slot["subject_result"]  = pd.NA
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

    # 2. Drop placeholder columns
    drop_cols = [c for c in df.columns if str(c).startswith("_drop_")]
    df = df.drop(columns=drop_cols, errors="ignore")

    # 3. Sanitize column names
    df = _sanitize_columns(df)

    # 4. Replace Excel formula error strings with NaN
    df = df.replace(_EXCEL_ERRORS, pd.NA)

    # 5. Derive result — 2022 has both res and res2; prefer res (full word)
    if "res" in df.columns:
        df["result"] = df["res"]
    elif "res2" in df.columns:
        df["result"] = df["res2"]
    else:
        df["result"] = pd.NA
    df = df.drop(columns=["res", "res2"], errors="ignore")

    # 6. Rename to canonical names; dedup in case a year has both a raw column
    #    matching the canonical name and another that renames to it
    df = df.rename(columns=COLUMN_RENAMES)
    df = df.loc[:, ~df.columns.duplicated(keep="first")]

    # 7. Unpivot subject slots → long format
    df = _unpivot_subjects(df)

    # 8. Value mappings
    if "gender" in df.columns:
        df["gender"] = df["gender"].map(GENDER_MAP).fillna(df["gender"])
    if "category" in df.columns:
        df["category"] = df["category"].map(CATEGORY_MAP).fillna(df["category"])

    # 9. Prepend exam_year
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

    print(f"\nTotal: {len(out_df):,} rows × {len(out_df.columns)} columns")

    out = BOARD_RESULTS_12TH_CLEAN.local_path
    out.parent.mkdir(exist_ok=True)
    out_df.to_csv(out, index=False)
    print(f"Written to {out}")
    print("\nDone.")


if __name__ == "__main__":
    main()
