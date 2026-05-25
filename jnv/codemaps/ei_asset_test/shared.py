"""
Column types and dtype coercion for the EI Asset Test clean table.
Mirrors the pattern in codemaps/mains/shared.py and codemaps/neet/shared.py.
"""

from __future__ import annotations

import pandas as pd

# ── Column type registry ──────────────────────────────────────────────────────
# Types:
#   "str"   — kept as string
#   "int"   — nullable integer (Int64)
#   "float" — nullable float (float64)

COLUMN_TYPES: dict[str, str] = {
    "id":                       "int",
    "school_identifier":        "int",
    "assetd_assessment_id":     "int",
    "first_name":                "str",
    "last_name":                 "str",
    "gender":                   "str",
    "school":                   "str",
    "city":                     "str",
    "state":                    "str",
    "caste":                    "str",
    "class":                    "int",
    "subject_no":                "int",
    "subject":                  "str",
    "raw_score":                "int",
    "scale_score":              "int",
    "percentile":               "int",
}


def apply_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cast a clean EI Asset Test DataFrame to canonical types.
    Call this before writing to parquet so BigQuery sees the correct schema.
    """
    for col in df.columns:
        col_type = COLUMN_TYPES.get(col)

        if col_type == "float":
            df[col] = pd.to_numeric(df[col], errors="coerce")

        elif col_type == "int":
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        elif col_type == "str":
            df[col] = df[col].where(df[col].notna(), other=None).astype(str)
            df[col] = df[col].replace({"nan": None, "None": None, "<NA>": None})

    return df
