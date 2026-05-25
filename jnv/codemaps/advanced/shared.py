"""
Canonical columns and helpers for JEE Advanced data.

These are merged onto the mains DataFrame by (test_year, application_no)
inside clean_jee.py. The advanced Excel files carry ranks only — no scores —
so jee_advanced_qualified_calculated is always null (see clean_jee.py).
"""

import numpy as np
import pandas as pd

# Columns produced by the advanced codemap engine.
# Join keys first, then all rank columns.
ADV_CANONICAL_COLS = [
    "test_year",
    "application_no",
    # Presence marker — True for every row in the advanced file; used to
    # distinguish "student appeared for JEE Advanced" from "no advanced data".
    # Dropped from the final output after post-processing.
    "adv_appeared",
    # All-India
    "adv_all_india_rank",
    "adv_all_india_pwd_rank",
]

ADV_COLUMN_TYPES = {col: "int" for col in ADV_CANONICAL_COLS}
ADV_COLUMN_TYPES["test_year"]          = "constant"
ADV_COLUMN_TYPES["application_no"]     = "str"
ADV_COLUMN_TYPES["adv_appeared"]       = "constant"  # always True; dropped post-merge
ADV_COLUMN_TYPES["adv_all_india_rank"] = "int"
ADV_COLUMN_TYPES["adv_all_india_pwd_rank"] = "int"

# Intermediate rank columns — read from raw files, used to derive adv_category_rank,
# adv_category_pwd_rank, adv_prep_category_rank, and jee_prep_qualified, then dropped.
ADV_RANK_SOURCE_COLS = {
    # Per-category general ranks
    "adv_obc_rank":         "int",
    "adv_sc_rank":          "int",
    "adv_st_rank":          "int",
    "adv_ews_rank":         "int",
    # Per-category PWD ranks
    "adv_obc_pwd_rank":     "int",
    "adv_sc_pwd_rank":      "int",
    "adv_st_pwd_rank":      "int",
    "adv_ews_pwd_rank":     "int",
    # Preparatory course ranks
    "adv_prep_sc_rank":     "int",
    "adv_prep_st_rank":     "int",
    "adv_prep_sc_pwd_rank": "int",
    "adv_prep_st_pwd_rank": "int",
    "adv_prep_obc_pwd_rank":"int",
    "adv_prep_ews_pwd_rank":"int",
    "adv_prep_crl_pwd_rank":"int",
}


def to_adv_rank(val, zero_is_null=False):
    """
    Parse a rank value from the raw Excel.
    Returns NaN if missing, non-numeric, or (when zero_is_null=True) zero.
    The 2025 advanced file uses 0 for 'no rank'; the 2024 file uses NaN.
    """
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if s in ("", "---", "-", "N/A", "NA", "NONE", "NAN"):
        return np.nan
    try:
        f = float(s)
        return np.nan if (zero_is_null and f == 0.0) else f
    except ValueError:
        return np.nan
