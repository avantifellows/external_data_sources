"""
Shared constants, column definitions, and normalization helpers
for all NEET codemaps.
"""

import re

import numpy as np
import pandas as pd

# ── Canonical output columns (ordered) ───────────────────────────────────────

CANONICAL_COLS = [
    # core
    "test_year", "test_name", "application_no", "roll_no",
    "student_full_name", "dob", "student_gender", "category",
    # identifiers
    "student_id", "school_code",
    # location
    "student_state", "place_of_school", "jnv_name",
    # 12th board
    "year_of_passing_12", "board_12",
    "marks_12_obtained", "marks_12_total", "marks_12_pct",
    # 10th board
    "year_of_passing_10", "board_10",
    "marks_10_obtained", "marks_10_total", "marks_10_pct",
    # NEET scores — per-subject are percentiles; neet_total_score is raw marks
    "neet_appeared_for_exam",
    "neet_physics_percentile", "neet_chemistry_percentile", "neet_biology_percentile",
    "neet_total_percentile",
    "neet_total_score", "neet_max_score",
    # NEET ranks
    "neet_all_india_rank", "neet_category_rank", "neet_all_india_pwd_rank",
    # NEET qualification
    "neet_qualified_from_data", "neet_qualified_calculated", "neet_qualified",
]

# ── Column types ──────────────────────────────────────────────────────────────
# constant  → value comes from codemap["constants"], never from raw columns
# str       → raw value passed through as-is
# float     → to_float()
# int       → to_int()
# gender    → normalize_gender()
# category  → normalize_category() — also reads _pwd_raw from col_map
# appeared  → appeared() — True if P/present or null; False if A/absent
# boolean   → to_boolean()

COLUMN_TYPES = {
    "test_year":                    "constant",
    "test_name":                    "constant",
    "application_no":               "str",
    "roll_no":                      "str",
    "student_full_name":            "str",
    "dob":                          "str",
    "student_gender":               "gender",
    "category":                     "category",
    "student_id":                   "str",
    "school_code":                  "str",
    "student_state":                "str",
    "place_of_school":              "str",
    "jnv_name":                     "str",
    "year_of_passing_12":           "float",
    "board_12":                     "str",
    "marks_12_obtained":            "float",
    "marks_12_total":               "float",
    "marks_12_pct":                 "float",
    "year_of_passing_10":           "float",
    "board_10":                     "str",
    "marks_10_obtained":            "float",
    "marks_10_total":               "float",
    "marks_10_pct":                 "float",
    "neet_appeared_for_exam":       "appeared",
    "neet_physics_percentile":      "float",
    "neet_chemistry_percentile":    "float",
    "neet_biology_percentile":      "float",
    "neet_total_percentile":        "float",
    "neet_total_score":             "float",
    "neet_max_score":               "constant",
    "neet_all_india_rank":          "int",
    "neet_category_rank":           "int",
    "neet_all_india_pwd_rank":      "int",
    "neet_qualified_from_data":     "boolean",
    "neet_qualified_calculated":    "boolean",
    "neet_qualified":               "boolean",
}


# ── Normalization helpers ─────────────────────────────────────────────────────

def normalize_gender(val):
    if pd.isna(val):
        return None
    v = str(val).strip().lower()
    if v in ("male", "m"):
        return "Male"
    if v in ("female", "f"):
        return "Female"
    return "Others"


def normalize_category(cat_val, pwd_val):
    if pd.isna(cat_val):
        return None
    c = str(cat_val).strip().upper().replace("-NCL", "").replace("(CENTRAL LIST)", "").replace(" ", "")

    cat_pwd = "PWD" in c or "PH" in c
    if cat_pwd:
        c = c.replace("PWD", "").replace("PH", "").strip("-")

    base_map = {
        "EWS": "Gen-EWS", "GENEWS": "Gen-EWS", "GEN-EWS": "Gen-EWS",
        "GENERAL": "Gen", "GEN": "Gen", "UR": "Gen",
        "OBC": "OBC",
        "SC": "SC",
        "ST": "ST",
    }
    pwd_name_map = {
        "Gen": "PWD-Gen", "Gen-EWS": "PWD-EWS",
        "OBC": "PWD-OBC", "SC": "PWD-SC", "ST": "PWD-ST",
    }
    base = base_map.get(c, "Gen")
    pwd = cat_pwd or (
        not pd.isna(pwd_val)
        and str(pwd_val).strip().lower() not in ("", "0", "no", "false", "nan", "none", "n", "----", "---")
    )
    return pwd_name_map[base] if pwd else base


def to_float(val):
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s.upper() in ("", "---", "----", "- -", "-", "ABS", "N/A", "NA", "NONE", "NAN"):
        return np.nan
    # Handle "X Y/Z" mixed-fraction strings (e.g. "55 2/5" → 55.4)
    frac_match = re.match(r"^(\d+)\s+(\d+)/(\d+)$", s)
    if frac_match:
        whole, num, den = int(frac_match.group(1)), int(frac_match.group(2)), int(frac_match.group(3))
        return whole + num / den if den != 0 else np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def to_int(val):
    """Parse a rank/integer value. Returns pd.NA (nullable) if missing or non-numeric."""
    f = to_float(val)
    return pd.NA if pd.isna(f) else int(f)


def appeared(val):
    """
    True if candidate appeared (P / present), False if absent (A / absent).
    Defaults to True when the column is missing or null — most NEET files only
    include rows for candidates who appeared.
    """
    if pd.isna(val):
        return True
    return str(val).strip().upper() not in ("A", "ABSENT", "ABS")


def to_boolean(val):
    """Parse True/False/Yes/No strings into Python bool. None if missing."""
    if pd.isna(val):
        return None
    return str(val).strip().lower() in ("true", "1", "yes", "y", "eligible", "qualified")


def apply_dtypes(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Cast a clean NEET DataFrame to canonical types.
    Call this before writing to parquet so BigQuery sees the correct schema.
    """
    for col in df.columns:
        col_type = COLUMN_TYPES.get(col)

        if col_type == "float" or col == "neet_max_score":
            df[col] = pd.to_numeric(df[col], errors="coerce")

        elif col_type == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        elif col_type in ("appeared", "boolean"):
            # Handles True/False objects, "True"/"False" strings, 0.0/1.0 floats, and NaN/None.
            # CSV round-trips store booleans as float64 (1.0/0.0), so we must try float() first.
            def _to_bool(v):
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return pd.NA
                sv = str(v).strip().lower()
                if sv in ("", "nan", "none", "<na>", "na"):
                    return pd.NA
                if sv in ("true", "yes", "y"):
                    return True
                if sv in ("false", "no", "n"):
                    return False
                try:
                    return bool(float(sv))
                except ValueError:
                    return pd.NA
            df[col] = pd.array([_to_bool(v) for v in df[col]], dtype=pd.BooleanDtype())

        elif col_type in ("str", "gender", "category") or col in ("test_year", "test_name"):
            # Keep as string; convert numeric artefacts (e.g. 2021 → "2021")
            df[col] = df[col].where(df[col].notna(), other=None).astype(str)
            df[col] = df[col].replace({"nan": None, "None": None, "<NA>": None})

        elif col_type == "constant" and col not in ("neet_max_score",):
            # Non-numeric constants (test_year, test_name) already handled above
            pass

    # ID columns: strip trailing .0 from numeric reads (e.g. "4411109202.0" → "4411109202")
    for col in ("application_no", "roll_no", "student_id", "school_code"):
        if col not in df.columns:
            continue
        def _clean_id(v):
            if pd.isna(v) or str(v).strip() in ("", "nan", "None", "<NA>"):
                return None
            s = str(v).strip()
            # strip trailing ".0" from float reads
            if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
                return s[:-2]
            return s
        df[col] = df[col].apply(_clean_id)

    return df


def safe_pct(obtained, total):
    try:
        o, t = float(obtained), float(total)
        return round(o / t * 100, 2) if t > 0 else np.nan
    except (TypeError, ValueError):
        return np.nan
