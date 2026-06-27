"""
Column types and dtype coercion for the JNVST 2018 clean table.
Mirrors the pattern in codemaps/mains/shared.py and codemaps/neet/shared.py.
"""

from __future__ import annotations

import pandas as pd

# ── Column type registry ──────────────────────────────────────────────────────
# Types:
#   "str"      — kept as string
#   "int"      — nullable integer (Int64)
#   "float"    — nullable float (float64)
#   "constant" — written as-is (str), no coercion needed

COLUMN_TYPES: dict[str, str] = {
    "test_year":                        "constant",
    "area":                             "str",
    "block":                            "int",
    "centre_no":                        "int",
    "roll_no":                          "str",
    "district_rank":                    "int",
    "gender":                           "str",
    "category":                         "str",
    "language":                         "str",
    "sel":                              "str",
    "total_marks":                      "int",
    "mental_ability_marks":             "int",
    "arithmetic_marks":                 "int",
    "language_marks":                   "int",
    "qualified":                        "float",
    "name":                             "str",
    "medium_of_education":              "str",
    "absent_flag":                      "float",
    "win":                              "str",
    "osel":                             "str",
    "handicapped":                      "str",
    "selqt":                            "str",
    "open_code":                        "float",
    "serial":                           "int",
    "waitlist":                         "int",
    "state_district_code":              "int",
    "state":                            "str",
    "district":                         "str",
    "standardized_scores":              "float",
    "total_marks_bucket_10":            "int",
    "mental_ability_marks_bucket_10":   "int",
    "arithmetic_marks_bucket_10":       "int",
    "language_marks_bucket_10":         "int",
}


def apply_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast a clean JNVST DataFrame to canonical types.
    Call this before writing to parquet so BigQuery sees the correct schema.
    """
    for col in df.columns:
        col_type = COLUMN_TYPES.get(col)

        if col_type == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce")

        elif col_type == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        elif col_type in ("str", "constant"):
            df[col] = df[col].where(df[col].notna(), other=None).astype(str)
            df[col] = df[col].replace({"nan": None, "None": None, "<NA>": None})

    return df
