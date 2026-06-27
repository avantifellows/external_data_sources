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
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BOARD_RESULTS_10TH_CLEAN, BQ_PROJECT, BQ_LOCATION, RAW_BOARD_RESULTS_10TH_FILES

_DIM_STUDENT      = f"`{BQ_PROJECT}.production_dbt_final.dim_student`"
_DIM_STUDENT_HIST = f"`{BQ_PROJECT}.production_dbt_final.dim_student_historical`"

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
    "fk_avanti_student_id", "fk_match_confidence", "fk_match_count",
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


# ── FK student ID matching ─────────────────────────────────────────────────────

def _add_fk_student_id(df: pd.DataFrame) -> pd.DataFrame:
    """
    Query BigQuery to match each (exam_year, roll_number) to an Avanti pk_student_id
    using four passes:
      1. name_dob / name_dob_parent  — exact name + DOB (parent names escalate confidence)
      2. name_dob_swapped            — DD/MM transposition in dim_student
      3. name_dob_year_off           — exam_year ± 1
      4. name_fuzzy_dob              — exact DOB + edit distance ≤ 2 on name
    Adds fk_avanti_student_id, fk_match_confidence, fk_match_count to df.
    """
    from google.cloud import bigquery

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    # Upload unique student rows to a temp table so BQ can join against them
    students = (
        df[["exam_year", "roll_number", "student_name", "date_of_birth", "father_name", "mother_name"]]
        .drop_duplicates(subset=["exam_year", "roll_number"])
        .copy()
    )
    tmp = f"{BQ_PROJECT}.external_data_sources._tmp_b10_{int(time.time())}"
    print(f"  Uploading {len(students):,} student rows to temp table ...")
    load_job = client.load_table_from_dataframe(students, tmp)
    load_job.result()

    try:
        sql = f"""
        WITH src AS (
            SELECT
                exam_year,
                roll_number,
                UPPER(TRIM(REGEXP_REPLACE(student_name,   r'\\s+', ' '))) AS norm_name,
                SAFE.PARSE_DATE('%d%m%Y', LPAD(date_of_birth, 8, '0'))      AS parsed_dob,
                UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))) AS norm_father,
                UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))) AS norm_mother
            FROM `{tmp}`
            WHERE student_name IS NOT NULL
        ),
        avanti AS (
            SELECT DISTINCT pk_student_id, date_of_birth, academic_year,
                UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\\s+', ' ')))         AS norm_name,
                UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))) AS norm_father,
                UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))) AS norm_mother,
                CAST(CAST(RIGHT(academic_year,4) AS INT64) - 2 AS STRING)            AS expected_exam_year,
                SAFE.DATE(
                    EXTRACT(YEAR  FROM date_of_birth),
                    EXTRACT(DAY   FROM date_of_birth),
                    EXTRACT(MONTH FROM date_of_birth)
                ) AS dob_swapped
            FROM {_DIM_STUDENT}
            WHERE (LOWER(COALESCE(student_school,'')) LIKE '%jnv%'
                OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')
              AND student_grade = 12
              AND academic_year IN ('2023-2024','2024-2025','2025-2026','2026-2027')
              AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL
            UNION ALL
            SELECT DISTINCT pk_student_id, date_of_birth, academic_year,
                UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\\s+', ' ')))         AS norm_name,
                UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))) AS norm_father,
                UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))) AS norm_mother,
                CAST(CAST(RIGHT(academic_year,4) AS INT64) - 2 AS STRING)            AS expected_exam_year,
                SAFE.DATE(
                    EXTRACT(YEAR  FROM date_of_birth),
                    EXTRACT(DAY   FROM date_of_birth),
                    EXTRACT(MONTH FROM date_of_birth)
                ) AS dob_swapped
            FROM {_DIM_STUDENT_HIST}
            WHERE (LOWER(COALESCE(student_school,'')) LIKE '%jnv%'
                OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')
              AND student_grade = 12
              AND academic_year IN ('2023-2024','2024-2025','2025-2026','2026-2027')
              AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL
        ),
        p1 AS (
            SELECT b.exam_year, b.roll_number,
                COUNT(DISTINCT a.pk_student_id) AS match_count,
                ANY_VALUE(a.pk_student_id)      AS fk_avanti_student_id,
                CASE WHEN LOGICAL_OR(
                    (b.norm_father!='' AND b.norm_father=a.norm_father)
                    OR (b.norm_mother!='' AND b.norm_mother=a.norm_mother)
                ) THEN 'name_dob_parent' ELSE 'name_dob' END AS match_confidence
            FROM src b JOIN avanti a
                ON a.norm_name=b.norm_name AND a.date_of_birth=b.parsed_dob AND a.expected_exam_year=b.exam_year
            GROUP BY 1,2
        ),
        p2 AS (
            SELECT b.exam_year, b.roll_number,
                COUNT(DISTINCT a.pk_student_id) AS match_count,
                ANY_VALUE(a.pk_student_id)      AS fk_avanti_student_id,
                'name_dob_swapped'              AS match_confidence
            FROM src b
            LEFT JOIN p1 USING (exam_year, roll_number)
            JOIN avanti a ON a.norm_name=b.norm_name AND a.dob_swapped=b.parsed_dob AND a.expected_exam_year=b.exam_year
            WHERE p1.roll_number IS NULL
            GROUP BY 1,2
        ),
        p3 AS (
            SELECT b.exam_year, b.roll_number,
                COUNT(DISTINCT a.pk_student_id) AS match_count,
                ANY_VALUE(a.pk_student_id)      AS fk_avanti_student_id,
                'name_dob_year_off'             AS match_confidence
            FROM src b
            LEFT JOIN p1 USING (exam_year, roll_number)
            LEFT JOIN p2 USING (exam_year, roll_number)
            JOIN avanti a ON a.norm_name=b.norm_name AND a.date_of_birth=b.parsed_dob
                AND CAST(a.expected_exam_year AS INT64) IN (CAST(b.exam_year AS INT64)-1, CAST(b.exam_year AS INT64)+1)
            WHERE p1.roll_number IS NULL AND p2.roll_number IS NULL
            GROUP BY 1,2
        ),
        p4 AS (
            SELECT b.exam_year, b.roll_number,
                COUNT(DISTINCT a.pk_student_id) AS match_count,
                ANY_VALUE(a.pk_student_id)      AS fk_avanti_student_id,
                'name_fuzzy_dob'                AS match_confidence
            FROM src b
            LEFT JOIN p1 USING (exam_year, roll_number)
            LEFT JOIN p2 USING (exam_year, roll_number)
            LEFT JOIN p3 USING (exam_year, roll_number)
            JOIN avanti a ON a.date_of_birth=b.parsed_dob AND a.expected_exam_year=b.exam_year
                AND EDIT_DISTANCE(a.norm_name, b.norm_name) BETWEEN 1 AND 2
            WHERE p1.roll_number IS NULL AND p2.roll_number IS NULL AND p3.roll_number IS NULL
            GROUP BY 1,2
        ),
        mapping AS (
            SELECT exam_year, roll_number,
                CASE WHEN match_count=1 THEN fk_avanti_student_id ELSE NULL END AS fk_avanti_student_id,
                match_confidence AS fk_match_confidence,
                match_count      AS fk_match_count
            FROM (
                SELECT * FROM p1 UNION ALL SELECT * FROM p2
                UNION ALL SELECT * FROM p3 UNION ALL SELECT * FROM p4
            )
        )
        SELECT exam_year, roll_number, fk_avanti_student_id, fk_match_confidence, fk_match_count
        FROM mapping
        """
        print("  Running 4-pass FK matching ...")
        mapping_df = client.query(sql).to_dataframe()
        mapping_df["exam_year"] = mapping_df["exam_year"].astype(str)
        mapping_df["roll_number"] = mapping_df["roll_number"].astype(str)
        mapping_df["fk_match_count"] = mapping_df["fk_match_count"].astype("Int64")

        matched = mapping_df["fk_avanti_student_id"].notna().sum()
        print(f"  Matched {matched:,} / {len(mapping_df):,} students ({matched/len(mapping_df)*100:.1f}%)")

        df = df.merge(
            mapping_df,
            on=["exam_year", "roll_number"],
            how="left",
        )
    finally:
        client.delete_table(tmp, not_found_ok=True)

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

    print("\nFetching FK student IDs from BigQuery ...")
    out_df = _add_fk_student_id(out_df)

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
