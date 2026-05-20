"""
Shared constants, column definitions, and normalization helpers
for all JEE Mains codemaps.
"""

import numpy as np
import pandas as pd

# ── Canonical output columns (ordered) ───────────────────────────────────────

CANONICAL_COLS = [
    # core
    "test_year", "test_name", "application_no", "student_full_name",
    "dob", "student_gender", "category",
    "school_code", "roll_no_s1", "roll_no_s2",
    # location
    "student_state", "district_12", "place_of_school",
    "jnv_name", "jnv_region",
    # 12th board
    "year_of_passing_12", "board_12",
    "marks_12_obtained", "marks_12_total", "marks_12_pct",
    # 10th board
    "year_of_passing_10", "board_10",
    "marks_10_obtained", "marks_10_total", "marks_10_pct",
    # scores
    "appeared_for_exam",
    "physics_score", "chemistry_score", "maths_score", "total_score", "max_score",
    # session scores (S1 = January, S2 = April)
    "physics_score_s1", "chemistry_score_s1", "maths_score_s1", "total_score_s1",
    "physics_score_s2", "chemistry_score_s2", "maths_score_s2", "total_score_s2",
    # ranks
    "all_india_rank", "category_rank",
    "all_india_pwd_rank", "category_pwd_rank",
    "obc_rank", "sc_rank", "st_rank", "ews_rank",
    # qualification
    "jee_mains_qualified", "jee_advanced_qualified", "jee_prep_qualified",
    "adv_prep_category_rank", "adv_ineligibility_reason",
    "eligible",
]

# ── Column types ──────────────────────────────────────────────────────────────
# constant     → value comes from codemap["constants"], never from raw columns
# str          → raw value passed through as-is
# float        → to_float()
# gender       → normalize_gender()
# category     → normalize_category() — also reads _pwd_raw from col_map
# appeared     → appeared() — True/False based on ABS detection
# bool_qualified → to_bool_qualified()

COLUMN_TYPES = {
    "test_year":                "constant",
    "test_name":                "constant",
    "application_no":           "str",
    "student_full_name":        "str",
    "dob":                      "str",
    "student_gender":           "gender",
    "category":                 "category",
    "school_code":              "str",
    "roll_no_s1":               "str",
    "roll_no_s2":               "str",
    "student_state":            "str",
    "district_12":              "str",
    "place_of_school":          "str",
    "jnv_name":                 "str",
    "jnv_region":               "str",
    "year_of_passing_12":       "float",
    "board_12":                 "str",
    "marks_12_obtained":        "float",
    "marks_12_total":           "float",
    "marks_12_pct":             "float",
    "year_of_passing_10":       "float",
    "board_10":                 "str",
    "marks_10_obtained":        "float",
    "marks_10_total":           "float",
    "marks_10_pct":             "float",
    "appeared_for_exam":        "appeared",
    "physics_score":            "float",
    "chemistry_score":          "float",
    "maths_score":              "float",
    "total_score":              "float",
    "max_score":                "constant",
    "physics_score_s1":         "float",
    "chemistry_score_s1":       "float",
    "maths_score_s1":           "float",
    "total_score_s1":           "float",
    "physics_score_s2":         "float",
    "chemistry_score_s2":       "float",
    "maths_score_s2":           "float",
    "total_score_s2":           "float",
    "all_india_rank":           "float",
    "category_rank":            "float",
    "all_india_pwd_rank":       "float",
    "category_pwd_rank":        "float",
    "obc_rank":                 "float",
    "sc_rank":                  "float",
    "st_rank":                  "float",
    "ews_rank":                 "float",
    "jee_mains_qualified":      "bool_qualified",
    "jee_advanced_qualified":   "bool_qualified",
    "jee_prep_qualified":       "bool_qualified",
    "adv_prep_category_rank":   "float",
    "adv_ineligibility_reason": "str",
    "eligible":                 "constant",
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
    c = str(cat_val).strip().upper().replace("-NCL", "").replace(" ", "")
    base_map = {
        "GENERAL": "Gen", "GEN": "Gen", "UR": "Gen",
        "EWS": "Gen-EWS", "GENEWS": "Gen-EWS",
        "OBC": "OBC",
        "SC": "SC",
        "ST": "ST",
    }
    base = base_map.get(c, "Gen")
    pwd = (
        not pd.isna(pwd_val)
        and str(pwd_val).strip().lower() not in ("", "0", "no", "false", "nan", "none", "n")
    )
    return f"PWD-{base}" if pwd else base


def to_float(val):
    if pd.isna(val):
        return np.nan
    s = str(val).strip().upper()
    if s in ("", "---", "- -", "-", "ABS", "N/A", "NA", "NONE", "NAN"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        return np.nan


def appeared(val):
    """False if candidate was absent (null or ABS string), True otherwise."""
    if pd.isna(val):
        return False
    return str(val).strip().upper() != "ABS"


def to_bool_qualified(val):
    if pd.isna(val):
        return False
    return str(val).strip().lower() in ("yes", "1", "true", "y", "eligible")


def safe_pct(obtained, total):
    try:
        o, t = float(obtained), float(total)
        return round(o / t * 100, 2) if t > 0 else np.nan
    except (TypeError, ValueError):
        return np.nan
