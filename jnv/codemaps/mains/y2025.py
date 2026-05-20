import numpy as np
import pandas as pd


def post_transform(raw_df, out_df):
    """
    Derive category_pwd_rank from individual per-category PWD rank columns.
    Called by the engine after the standard column mapping pass.
    """
    col_map = {
        "PWD-OBC": "OBC_PH_rank",
        "PWD-SC":  "SC_PH_rank",
        "PWD-ST":  "ST_PH_rank",
        "PWD-EWS": "EWS_PH_rank",
        "PWD-Gen": "AIR_PH_Rank",
    }
    cols_lower = {c.lower().strip(): c for c in raw_df.columns}

    def _resolve(cat):
        raw_col_name = col_map.get(str(cat), "")
        actual = cols_lower.get(raw_col_name.lower(), "")
        if actual and actual in raw_df.columns:
            return actual
        return None

    pwd_ranks = []
    for cat, idx in zip(out_df["category"], out_df.index):
        col = _resolve(cat)
        val = raw_df.at[idx, col] if col else np.nan
        try:
            pwd_ranks.append(float(val) if not pd.isna(val) else np.nan)
        except (TypeError, ValueError):
            pwd_ranks.append(np.nan)

    out_df["category_pwd_rank"] = pwd_ranks
    return out_df


CODEMAP = {
    "source": {
        # Use the full JNV cohort file — it supersedes JEE Mains 2025.xlsx
        # (12,103 rows vs 4,037) and carries richer JNV metadata.
        "file": "JEE 2025 - All JNV Candidates.xlsx",
        "sheet": "JEE 2025 - All JNV Candidates",
        "header": 0,
    },
    "constants": {
        "test_year": "2025",
        "test_name": "JEE Mains Overall",
        "max_score": 300,
        "jee_adv_ineligible": None,
    },
    # 2025 notes:
    # - Final scores only in this file (no session-level P1A/P1B columns).
    # - category_pwd_rank is derived via post_transform from per-category
    #   PWD rank columns (OBC_PH_rank, SC_PH_rank, ST_PH_rank, EWS_PH_rank).
    "columns": {
        "application_no":           ["JEEApplicationNumber", "APPNO"],
        "student_full_name":        ["CNAME", "Student Name"],
        "dob":                      ["DOB", "DoB"],
        "student_gender":           ["Gender", "GENDER"],
        "_pwd_raw":                 ["PWD"],
        "category":                 ["Category", "CAT"],
        "student_state":            ["State12"],
        "district_12":              ["District"],
        "place_of_school":          ["PlaceofSchool", "PlaceofSchooling"],
        "jnv_name":                 ["jnvname", "JNV Name"],
        "year_of_passing_12":       ["YEAROFPASSING12", "yearOfPassing"],
        "board_12":                 ["boardName", "Board"],
        "marks_12_obtained":        ["obtainedMark"],
        "marks_12_total":           ["totalMark"],
        "marks_12_pct":             ["percentageOfMarks"],
        "appeared_for_exam":        ["jeeTotal", "PS_TOT_P1F"],
        "physics_score":            ["jeePhysics", "PS_PHY_P1F"],
        "chemistry_score":          ["jeeChemistry", "PS_CHE_P1F"],
        "maths_score":              ["jeeMathematics", "PS_MAT_P1F"],
        "total_score":              ["jeeTotal", "PS_TOT_P1F"],
        "all_india_rank":           ["AIR_Rank"],
        "all_india_pwd_rank":       ["AIR_PH_Rank"],
        "obc_rank":                 ["OBC_rank"],
        "sc_rank":                  ["SC_rank"],
        "st_rank":                  ["ST_rank"],
        "ews_rank":                 ["EWS_rank"],
        "jee_mains_qualified":      ["JeeQualified"],
        "jee_advanced_qualified":   ["jee_adv_qualified"],
        "jee_prep_qualified":       ["jee_prep_qualified"],
        "adv_prep_category_rank":   ["adv_prep_category_rank"],
    },
    "post_transform": post_transform,
}
