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
    "school_code",
    # location
    "student_state", "district_12", "place_of_school",
    "jnv_name", "jnv_region",
    # 12th board
    "year_of_passing_12", "board_12",
    "marks_12_obtained", "marks_12_total", "marks_12_pct",
    # 10th board
    "year_of_passing_10", "board_10",
    "marks_10_obtained", "marks_10_total", "marks_10_pct",
    # JEE Mains scores
    "roll_no_s1", "roll_no_s2",
    "mains_appeared_for_exam",
    "mains_physics_score", "mains_chemistry_score", "mains_maths_score",
    "mains_total_score", "mains_max_score",
    # JEE Mains session scores (S1 = January, S2 = April)
    "mains_physics_score_s1", "mains_chemistry_score_s1",
    "mains_maths_score_s1",   "mains_total_score_s1",
    "mains_physics_score_s2", "mains_chemistry_score_s2",
    "mains_maths_score_s2",   "mains_total_score_s2",
    # JEE Mains ranks
    "mains_all_india_rank", "mains_category_rank",
    "mains_all_india_pwd_rank", "mains_category_pwd_rank",
    # JEE Mains qualification
    "jee_mains_qualified_from_data", "jee_mains_qualified_calculated", "jee_mains_qualified",
    # JEE Advanced eligibility metadata
    "jee_adv_ineligible", "jee_adv_ineligibility_reason",
    # JEE Advanced ranks (populated after merging the advanced Excel files)
    "adv_all_india_rank", "adv_category_rank",
    "adv_all_india_pwd_rank", "adv_category_pwd_rank",
    "adv_prep_category_rank",
    # JEE Advanced qualification
    "jee_advanced_qualified_from_data", "jee_advanced_qualified_calculated", "jee_advanced_qualified",
    # Preparatory course qualification
    "jee_prep_qualified_from_data", "jee_prep_qualified_calculated", "jee_prep_qualified",
]

# ── Column types ──────────────────────────────────────────────────────────────
# constant     → value comes from codemap["constants"], never from raw columns
# str          → raw value passed through as-is
# float        → to_float()
# gender       → normalize_gender()
# category     → normalize_category() — also reads _pwd_raw from col_map
# appeared     → appeared() — True/False based on ABS detection
# boolean      → to_boolean()

COLUMN_TYPES = {
    "test_year":                    "constant",
    "test_name":                    "constant",
    "application_no":               "str",
    "student_full_name":            "str",
    "dob":                          "str",
    "student_gender":               "gender",
    "category":                     "category",
    "school_code":                  "str",
    "roll_no_s1":                   "str",
    "roll_no_s2":                   "str",
    "student_state":                "str",
    "district_12":                  "str",
    "place_of_school":              "str",
    "jnv_name":                     "str",
    "jnv_region":                   "str",
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
    "mains_appeared_for_exam":      "appeared",
    "mains_physics_score":          "float",
    "mains_chemistry_score":        "float",
    "mains_maths_score":            "float",
    "mains_total_score":            "float",
    "mains_max_score":              "constant",
    "mains_physics_score_s1":       "float",
    "mains_chemistry_score_s1":     "float",
    "mains_maths_score_s1":         "float",
    "mains_total_score_s1":         "float",
    "mains_physics_score_s2":       "float",
    "mains_chemistry_score_s2":     "float",
    "mains_maths_score_s2":         "float",
    "mains_total_score_s2":         "float",
    "mains_all_india_rank":         "int",
    "mains_category_rank":          "int",
    "mains_all_india_pwd_rank":     "int",
    "mains_category_pwd_rank":      "int",
    "jee_mains_qualified_from_data":   "boolean",
    "jee_mains_qualified_calculated":  "boolean",
    "jee_mains_qualified":             "boolean",
    "jee_adv_ineligible":               "boolean",
    "jee_adv_ineligibility_reason":     "str",
    # adv_* columns are populated post-merge; engine leaves them as NaN
    "adv_all_india_rank":           "int",
    "adv_category_rank":            "int",
    "adv_all_india_pwd_rank":       "int",
    "adv_category_pwd_rank":        "int",
    "adv_prep_category_rank":       "int",
    "jee_advanced_qualified_from_data":   "boolean",
    "jee_advanced_qualified_calculated":  "boolean",
    "jee_advanced_qualified":             "boolean",
    "jee_prep_qualified_from_data":       "boolean",
    "jee_prep_qualified_calculated":      "boolean",
    "jee_prep_qualified":                 "boolean",
}

# ── Intermediate rank columns ─────────────────────────────────────────────────
# Needed during processing to derive category_rank columns, but not in final output.
MAINS_RANK_SOURCE_COLS = {
    "mains_obc_rank": "int",
    "mains_sc_rank":  "int",
    "mains_st_rank":  "int",
    "mains_ews_rank": "int",
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

    # Detect PWD encoded in the category string itself (e.g. "Gen-EWS-PwD", "PWD-OBC", "OBC-PWD")
    cat_pwd = "PWD" in c
    if cat_pwd:
        c = c.replace("PWD", "").strip("-")

    base_map = {
        "EWS": "Gen-EWS", "GENEWS": "Gen-EWS", "GEN-EWS": "Gen-EWS",
        "GENERAL": "Gen", "GEN": "Gen", "UR": "Gen",
        "OBC": "OBC",
        "SC": "SC",
        "ST": "ST",
    }
    # PWD name differs from base name for EWS (PWD-EWS, not PWD-Gen-EWS)
    pwd_name_map = {
        "Gen": "PWD-Gen", "Gen-EWS": "PWD-EWS",
        "OBC": "PWD-OBC", "SC": "PWD-SC", "ST": "PWD-ST",
    }
    base = base_map.get(c, "Gen")
    pwd = cat_pwd or (
        not pd.isna(pwd_val)
        and str(pwd_val).strip().lower() not in ("", "0", "no", "false", "nan", "none", "n")
    )
    return pwd_name_map[base] if pwd else base


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


def to_int(val):
    """Parse a rank/integer value. Returns pd.NA (nullable) if missing or non-numeric."""
    f = to_float(val)
    return pd.NA if pd.isna(f) else int(f)


def appeared(val):
    """False if candidate was absent (null or ABS string), True otherwise."""
    if pd.isna(val):
        return False
    return str(val).strip().upper() != "ABS"


def to_boolean(val):
    """Parse True/False/1/0/yes/no/eligible strings into Python bool. None if missing."""
    if pd.isna(val):
        return None
    return str(val).strip().lower() in ("true", "1", "yes", "y", "eligible")


def safe_pct(obtained, total):
    try:
        o, t = float(obtained), float(total)
        return round(o / t * 100, 2) if t > 0 else np.nan
    except (TypeError, ValueError):
        return np.nan


def apply_dtypes(df: "pd.DataFrame") -> "pd.DataFrame":
    """
    Cast a clean JEE DataFrame to canonical types.
    Call this before writing to parquet so BigQuery sees the correct schema.
    """
    for col in df.columns:
        col_type = COLUMN_TYPES.get(col)

        if col_type == "float" or col == "mains_max_score":
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
            df[col] = df[col].where(df[col].notna(), other=None).astype(str)
            df[col] = df[col].replace({"nan": None, "None": None, "<NA>": None})

    # ID columns: strip trailing .0 from numeric reads (e.g. "4411109202.0" → "4411109202")
    for col in ("application_no", "roll_no_s1", "roll_no_s2", "school_code"):
        if col not in df.columns:
            continue
        def _clean_id(v):
            if pd.isna(v) or str(v).strip() in ("", "nan", "None", "<NA>"):
                return None
            s = str(v).strip()
            if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
                return s[:-2]
            return s
        df[col] = df[col].apply(_clean_id)

    return df
