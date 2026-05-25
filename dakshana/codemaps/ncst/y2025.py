"""
NCST 2025 column mapping.

Source: NCST 2025.xlsx  sheet: "All"
The sheet has a merged-cell title row (row 0), a sub-header row (row 1), and
the actual column-name row at row 2 (0-indexed). header=2 tells pandas to use
row 2 as column names.

The file covers two exam sittings:
  - March 2025  → columns 11–25  (positional, after the 11 identity columns)
  - December 2024 → columns 26–40

Both sittings share the same +ve / -ve / Eff structure per subject:
  Physics (cols +3), Chemistry (+3), Logical Reasoning (+3), Maths/Bio (+3), Total (+3)

The canonical score columns are filled from whichever sitting produced the
higher total_effective_score (null counts as −∞). Both raw totals are also
kept as march_total_effective_score and dec_total_effective_score.

Columns 41–43 hold the three coaching preferences (1st / 2nd / 3rd).
school_code is available in this year only.
No contact columns in this file.
"""

import pandas as pd


# Positional indices for effective-score columns (0-indexed, post header=2 read)
_MARCH = {
    "physics":   13,
    "chemistry": 16,
    "reasoning": 19,
    "math_bio":  22,
    "total":     25,
}
_DEC = {
    "physics":   28,
    "chemistry": 31,
    "reasoning": 34,
    "math_bio":  37,
    "total":     40,
}
_PREF_COLS = (41, 42, 43)


def _post_transform(raw_df: pd.DataFrame, out_df: pd.DataFrame) -> pd.DataFrame:
    def _f(col_idx: int) -> pd.Series:
        return pd.to_numeric(raw_df.iloc[:, col_idx], errors="coerce")

    march = {k: _f(v) for k, v in _MARCH.items()}
    dec   = {k: _f(v) for k, v in _DEC.items()}

    # Use scores from whichever sitting has the higher total effective score.
    # When both are null the row stays null; when only one is present, use it.
    use_march = march["total"].fillna(float("-inf")) >= dec["total"].fillna(float("-inf"))

    out_df["physics_effective_score"]   = march["physics"].where(use_march,   dec["physics"])
    out_df["chemistry_effective_score"] = march["chemistry"].where(use_march, dec["chemistry"])
    out_df["reasoning_effective_score"] = march["reasoning"].where(use_march, dec["reasoning"])
    out_df["math_bio_effective_score"]  = march["math_bio"].where(use_march,  dec["math_bio"])
    out_df["total_effective_score"]     = march["total"].where(use_march,     dec["total"])

    out_df["march_total_effective_score"] = march["total"]
    out_df["dec_total_effective_score"]   = dec["total"]

    out_df["coaching_preference_1"] = raw_df.iloc[:, _PREF_COLS[0]].values
    out_df["coaching_preference_2"] = raw_df.iloc[:, _PREF_COLS[1]].values
    out_df["coaching_preference_3"] = raw_df.iloc[:, _PREF_COLS[2]].values

    return out_df


CODEMAP = {
    "source": {
        "file":   "NCST 2025.xlsx",
        "sheet":  "All",
        "header": 2,
    },
    "constants": {
        "test_year": "2025",
    },
    "columns": {
        "roll_no":              ["Unique Code"],
        "student_full_name":    ["Name of Student"],
        "student_gender":       ["Gender (Male / Female)"],
        "category":             ["Category (GEN/EWS/OBC/SC/ST)"],
        "physically_disabled":  ["Physically Disabled (Yes/No)"],
        "stream":               ["Applying For (Engineering / Medical)"],
        "school_name":          ["School Name"],
        "school_code":          ["School Code"],
        "annual_family_income": ["Annual Income"],
        # scores and preferences are extracted positionally in post_transform
    },
    "post_transform": _post_transform,
}
