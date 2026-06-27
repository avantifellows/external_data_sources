"""
Canonical column list, column types, normalisation helpers, and apply_dtypes
for the NVS NCST clean table.

Column names match dakshana_fact_ncst_results wherever the concept is the same
(roll_no, student_gender, category, coaching_preference_*, etc.). Where the
2026 data differs — normalized scores rather than penalty-adjusted effective
scores, separate bio/maths columns rather than a combined math_bio column —
the names reflect the actual data.
"""

from __future__ import annotations

import pandas as pd

# ── Canonical columns (output schema) ────────────────────────────────────────

CANONICAL_COLS: list[str] = [
    # identity
    "test_year",
    "roll_no",
    "student_full_name",
    # demographics
    "student_gender",
    "category",
    "physically_disabled",
    "stream",
    "dob",
    # school / geography
    "school_name",
    "school_code",
    "school_district",
    "state",
    # exam metadata
    "attendance",
    "qp_set",
    "exam_date",
    # socioeconomic
    "annual_family_income",
    "father_annual_income",
    "mother_annual_income",
    "staff_ward",
    "is_father_late",
    # coaching preference
    "coaching_preference_1",
    "coaching_preference_2",
    "coaching_preference_3",
    # aggregate scores
    "total_positive_ques",
    "total_negative_ques",
    "total_unattempted_ques",
    "total_raw_score",
    "total_normalized_score",
    # physics
    "physics_positive_ques",
    "physics_negative_ques",
    "physics_unattempted_ques",
    "physics_raw_score",
    "physics_normalized_score",
    # chemistry
    "chemistry_positive_ques",
    "chemistry_negative_ques",
    "chemistry_unattempted_ques",
    "chemistry_raw_score",
    "chemistry_normalized_score",
    # biology (NEET stream)
    "bio_positive_ques",
    "bio_negative_ques",
    "bio_unattempted_ques",
    "bio_raw_score",
    "bio_normalized_score",
    # maths (JEE stream)
    "maths_positive_ques",
    "maths_negative_ques",
    "maths_unattempted_ques",
    "maths_raw_score",
    "maths_normalized_score",
    # logical reasoning
    "reasoning_positive_ques",
    "reasoning_negative_ques",
    "reasoning_unattempted_ques",
    "reasoning_raw_score",
    "reasoning_normalized_score",
    # self-reported academic history
    "grade_9_math_marks",
    "grade_9_science_marks",
    "grade_10_math_marks",
    "grade_10_science_marks",
    "grade_9_aggregate_pct",
    "grade_10_aggregate_pct",
    "willing_for_coaching",
    # extended family
    "is_mother_alive",
    "father_education",
    "father_occupation",
    "mother_education",
    "mother_occupation",
    "guardian",
    # home address (separate from school location)
    "home_village",
    "home_post_office",
    "home_district",
    "home_state",
    "domicile_state",
    "pin_code",
    # household wealth
    "household_assets_value",
    "household_earning_members",
    "household_annual_income",
    "father_mother_combined_income",
    "max_household_income",
    "household_cash_savings",
    "house_ownership",
    "house_area_sqft",
    "house_bedrooms",
    "locality_type",
    "is_bpl",
    "has_ration_card",
    "ration_card_color",
    # misc
    "submission_type",
]

# ── Column type registry ──────────────────────────────────────────────────────

COLUMN_TYPES: dict[str, str] = {
    "test_year":                     "constant",
    "roll_no":                       "str",
    "student_full_name":             "str",
    "student_gender":                "str",
    "category":                      "str",
    "physically_disabled":           "bool",
    "stream":                        "str",
    "dob":                           "str",
    "school_name":                   "str",
    "school_code":                   "int",
    "school_district":               "str",
    "state":                         "str",
    "attendance":                    "str",
    "qp_set":                        "str",
    "exam_date":                     "str",
    "annual_family_income":          "float",
    "father_annual_income":          "float",
    "mother_annual_income":          "float",
    "staff_ward":                    "str",
    "is_father_late":                "bool",
    "coaching_preference_1":         "str",
    "coaching_preference_2":         "str",
    "coaching_preference_3":         "str",
    "total_positive_ques":           "int",
    "total_negative_ques":           "int",
    "total_unattempted_ques":        "int",
    "total_raw_score":               "float",
    "total_normalized_score":        "float",
    "physics_positive_ques":         "int",
    "physics_negative_ques":         "int",
    "physics_unattempted_ques":      "int",
    "physics_raw_score":             "float",
    "physics_normalized_score":      "float",
    "chemistry_positive_ques":       "int",
    "chemistry_negative_ques":       "int",
    "chemistry_unattempted_ques":    "int",
    "chemistry_raw_score":           "float",
    "chemistry_normalized_score":    "float",
    "bio_positive_ques":             "int",
    "bio_negative_ques":             "int",
    "bio_unattempted_ques":          "int",
    "bio_raw_score":                 "float",
    "bio_normalized_score":          "float",
    "maths_positive_ques":           "int",
    "maths_negative_ques":           "int",
    "maths_unattempted_ques":        "int",
    "maths_raw_score":               "float",
    "maths_normalized_score":        "float",
    "reasoning_positive_ques":       "int",
    "reasoning_negative_ques":       "int",
    "reasoning_unattempted_ques":    "int",
    "reasoning_raw_score":           "float",
    "reasoning_normalized_score":    "float",
    "grade_9_math_marks":            "float",
    "grade_9_science_marks":         "float",
    "grade_10_math_marks":           "float",
    "grade_10_science_marks":        "float",
    "grade_9_aggregate_pct":         "float",
    "grade_10_aggregate_pct":        "float",
    "willing_for_coaching":          "bool",
    "is_mother_alive":               "bool",
    "father_education":              "str",
    "father_occupation":             "str",
    "mother_education":              "str",
    "mother_occupation":             "str",
    "guardian":                      "str",
    "home_village":                  "str",
    "home_post_office":              "str",
    "home_district":                 "str",
    "home_state":                    "str",
    "domicile_state":                "str",
    "pin_code":                      "str",
    "household_assets_value":        "float",
    "household_earning_members":     "int",
    "household_annual_income":       "float",
    "father_mother_combined_income": "float",
    "max_household_income":          "float",
    "household_cash_savings":        "float",
    "house_ownership":               "str",
    "house_area_sqft":               "float",
    "house_bedrooms":                "int",
    "locality_type":                 "str",
    "is_bpl":                        "bool",
    "has_ration_card":               "bool",
    "ration_card_color":             "str",
    "submission_type":               "str",
}

# ── Normalisation helpers ─────────────────────────────────────────────────────

_GENDER_MAP: dict[str, str] = {
    "male":   "Male",
    "m":      "Male",
    "female": "Female",
    "f":      "Female",
}

_CATEGORY_MAP: dict[str, str] = {
    "gen":        "Gen",
    "general":    "Gen",
    "gen-ews":    "Gen-EWS",
    "ews":        "Gen-EWS",
    "gew":        "Gen-EWS",
    "obc":        "OBC",
    "obc-ncl":    "OBC",
    "sc":         "SC",
    "st":         "ST",
}

_STREAM_MAP: dict[str, str] = {
    "engineering": "Engineering",
    "jee":         "Engineering",
    "medical":     "Medical",
    "neet":        "Medical",
}

_COACHING_MAP: dict[str, str] = {
    "dakshana":               "Dakshana Foundation",
    "dakshana foundation":    "Dakshana Foundation",
    "enf":                    "Ex-Navodaya Foundation",
    "ex-navodaya foundation": "Ex-Navodaya Foundation",
    "avanti":                 "Avanti Foundation",
    "avanti foundation":      "Avanti Foundation",
}

_BOOL_TRUE  = {"yes", "y", "true", "1"}
_BOOL_FALSE = {"no",  "n", "false", "0"}


def _norm(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s and s.lower() not in ("nan", "none", "nat") else None


def normalize_gender(v) -> str | None:
    s = _norm(v)
    return _GENDER_MAP.get(s.lower(), s) if s else None


def normalize_category(v) -> str | None:
    s = _norm(v)
    if s is None:
        return None
    key = "".join(s.lower().split())
    for raw_key, mapped in _CATEGORY_MAP.items():
        if "".join(raw_key.split()) == key:
            return mapped
    return s


def normalize_stream(v) -> str | None:
    s = _norm(v)
    return _STREAM_MAP.get(s.lower(), s) if s else None


def normalize_coaching(v) -> str | None:
    s = _norm(v)
    return _COACHING_MAP.get(s.lower(), s) if s else None


def normalize_bool(v) -> bool | None:
    s = _norm(v)
    if s is None:
        return None
    key = s.lower()
    if key in _BOOL_TRUE:
        return True
    if key in _BOOL_FALSE:
        return False
    return None


# ── dtype coercion (CSV → parquet) ────────────────────────────────────────────

def apply_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Cast clean NVS NCST DataFrame to canonical types before writing to parquet."""
    for col in df.columns:
        col_type = COLUMN_TYPES.get(col)

        if col_type == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        elif col_type == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce")

        elif col_type == "bool":
            df[col] = df[col].map(
                lambda x: True if str(x).strip().lower() in ("true", "1")
                else (False if str(x).strip().lower() in ("false", "0") else None)
            )

        elif col_type in ("str", "constant"):
            df[col] = df[col].where(df[col].notna(), other=None).astype(str)
            df[col] = df[col].replace({"nan": None, "None": None, "<NA>": None, "NaT": None})

    return df
