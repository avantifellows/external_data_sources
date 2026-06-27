"""
Canonical column list, column types, normalisation helpers, and apply_dtypes
for the NCST (Navodaya CoE Selection Test) clean table.
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
    "nvs_region",
    "state",
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
    # scores — effective (after marking-scheme penalty)
    "physics_effective_score",
    "chemistry_effective_score",
    "math_bio_effective_score",
    "reasoning_effective_score",
    "total_effective_score",
    # 2025 only: per-session totals used to pick the canonical score
    "march_total_effective_score",
    "dec_total_effective_score",
]

# ── Column type registry ──────────────────────────────────────────────────────

COLUMN_TYPES: dict[str, str] = {
    "test_year":                    "constant",
    "roll_no":                      "str",
    "student_full_name":            "str",
    "student_gender":               "str",
    "category":                     "str",
    "physically_disabled":          "bool",
    "stream":                       "str",
    "dob":                          "str",
    "school_name":                  "str",
    "school_code":                  "int",
    "nvs_region":                   "str",
    "state":                        "str",
    "annual_family_income":         "float",
    "father_annual_income":         "str",
    "mother_annual_income":         "str",
    "staff_ward":                   "str",
    "is_father_late":               "bool",
    "coaching_preference_1":        "str",
    "coaching_preference_2":        "str",
    "coaching_preference_3":        "str",
    "physics_effective_score":      "float",
    "chemistry_effective_score":    "float",
    "math_bio_effective_score":     "float",
    "reasoning_effective_score":    "float",
    "total_effective_score":        "float",
    "march_total_effective_score":  "float",
    "dec_total_effective_score":    "float",
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
    "dakshana":                 "Dakshana Foundation",
    "dakshana foundation":      "Dakshana Foundation",
    "enf":                      "Ex-Navodaya Foundation",
    "ex-navodaya foundation":   "Ex-Navodaya Foundation",
    "avanti":                   "Avanti Foundation",
    "avanti foundation":        "Avanti Foundation",
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
    # strip internal spaces before lookup (handles "Gen- EWS", "OBC -NCL", etc.)
    key = "".join(s.lower().split())
    # rebuild the dash-variants the map expects
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
    """Cast clean NCST DataFrame to canonical types before writing to parquet."""
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
