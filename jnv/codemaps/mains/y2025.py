import numpy as np
import pandas as pd


def post_transform(raw_df, out_df):
    """
    1. Derive mains_category_pwd_rank from per-category PWD rank columns.
    2. Capture jee_adv_qualified / jee_prep_qualified from the mains file
       into the _from_data columns as a fallback.  clean_jee.py will
       override these with rank-derived values for students who appear in
       the advanced Excel file.
    """
    cols_lower = {c.lower().strip(): c for c in raw_df.columns}

    # ── mains_category_pwd_rank ───────────────────────────────────────────────
    pwd_col_map = {
        "PWD-OBC": "OBC_PH_rank",
        "PWD-SC":  "SC_PH_rank",
        "PWD-ST":  "ST_PH_rank",
        "PWD-EWS": "EWS_PH_rank",
        "PWD-Gen": "AIR_PH_Rank",
    }

    def _resolve(cat):
        raw_name = pwd_col_map.get(str(cat), "")
        actual = cols_lower.get(raw_name.lower(), "")
        return actual if actual and actual in raw_df.columns else None

    pwd_ranks = []
    for cat, idx in zip(out_df["category"], out_df.index):
        col = _resolve(cat)
        val = raw_df.at[idx, col] if col else np.nan
        try:
            pwd_ranks.append(float(val) if not pd.isna(val) else np.nan)
        except (TypeError, ValueError):
            pwd_ranks.append(np.nan)
    out_df["mains_category_pwd_rank"] = pwd_ranks

    # ── mains-file qualification flags (fallback for students not in adv file) ─
    def _to_bool(val):
        if pd.isna(val):
            return None
        return str(val).strip().lower() in ("true", "1", "yes", "y", "eligible")

    for src_col, dst_col in [
        ("jee_adv_qualified",  "jee_advanced_qualified_from_data"),
        ("jee_prep_qualified", "jee_prep_qualified_from_data"),
    ]:
        actual = cols_lower.get(src_col.lower())
        if actual and actual in raw_df.columns:
            out_df[dst_col] = raw_df[actual].apply(_to_bool)
        else:
            out_df[dst_col] = None

    # ── adv_prep_category_rank from mains file ────────────────────────────────
    actual = cols_lower.get("adv_prep_category_rank")
    if actual and actual in raw_df.columns:
        out_df["adv_prep_category_rank"] = raw_df[actual].apply(
            lambda v: float(v) if not pd.isna(v) else np.nan
        )

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
        "test_name": "JEE",
        "mains_max_score": 300,
        "jee_adv_ineligible": None,
    },
    # 2025 notes:
    # - Final scores only in this file (no session-level P1A/P1B columns).
    # - mains_category_pwd_rank derived via post_transform.
    # - jee_advanced_qualified_from_data / jee_prep_qualified_from_data written
    #   by post_transform as fallback; overridden for students in the advanced
    #   Excel file during the merge step in clean_jee.py.
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
        "mains_appeared_for_exam":  ["jeeTotal", "PS_TOT_P1F"],
        "mains_physics_score":      ["jeePhysics", "PS_PHY_P1F"],
        "mains_chemistry_score":    ["jeeChemistry", "PS_CHE_P1F"],
        "mains_maths_score":        ["jeeMathematics", "PS_MAT_P1F"],
        "mains_total_score":        ["jeeTotal", "PS_TOT_P1F"],
        "mains_all_india_rank":     ["AIR_Rank"],
        "mains_all_india_pwd_rank": ["AIR_PH_Rank"],
        "mains_obc_rank":           ["OBC_rank"],
        "mains_sc_rank":            ["SC_rank"],
        "mains_st_rank":            ["ST_rank"],
        "mains_ews_rank":           ["EWS_rank"],
        "jee_mains_qualified":      ["JeeQualified"],
    },
    "post_transform": post_transform,
}
