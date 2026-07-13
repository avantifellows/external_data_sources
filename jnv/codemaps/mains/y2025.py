from pathlib import Path

import numpy as np
import pandas as pd

# JEE Mains 2025.xlsx is a 4,037-row subset of All JNV Candidates that carries
# CNAME, DOB, FNAME, MNAME — columns absent from the main file.
_MAINS_2025 = Path(__file__).resolve().parent.parent.parent / "raw" / "jee_mains" / "JEE Mains 2025.xlsx"


def post_transform(raw_df, out_df):
    """
    1. Merge name/DOB/parent names from JEE Mains 2025.xlsx (4,037-row subset
       that has CNAME/DOB/FNAME/MNAME, absent from All JNV Candidates).
    2. Derive mains_category_pwd_rank from per-category PWD rank columns.
    3. Capture jee_adv_qualified / jee_prep_qualified from the mains file
       into the _from_data columns as a fallback.  clean_jee.py will
       override these with rank-derived values for students who appear in
       the advanced Excel file.
    """
    # ── Step 1: merge identity fields from JEE Mains 2025.xlsx ──────────────────
    if _MAINS_2025.exists():
        mains = pd.read_excel(_MAINS_2025, dtype=str)[["APPNO", "CNAME", "DOB", "FNAME", "MNAME"]]
        mains = mains.rename(columns={
            "APPNO": "application_no",
            "CNAME": "_m_name",
            "DOB":   "_m_dob",
            "FNAME": "_m_father",
            "MNAME": "_m_mother",
        })
        mains["application_no"] = mains["application_no"].str.strip()
        out_df["application_no"] = out_df["application_no"].astype(str).str.strip()
        out_df = out_df.merge(mains, on="application_no", how="left")
        # Fill nulls in the canonical columns from the Mains file
        for src, dst in [("_m_name", "student_full_name"), ("_m_dob", "dob"),
                         ("_m_father", "father_name"), ("_m_mother", "mother_name")]:
            if dst in out_df.columns:
                out_df[dst] = out_df[dst].where(out_df[dst].notna(), out_df[src])
            else:
                out_df[dst] = out_df[src]
            out_df = out_df.drop(columns=[src])
        filled = out_df["student_full_name"].notna().sum()
        print(f"    [2025] merged JEE Mains 2025.xlsx: {filled:,} / {len(out_df):,} rows now have a name")
    else:
        print(f"    [2025] WARN: {_MAINS_2025} not found — name/DOB will be null for all 2025 rows")

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
    # - SOURCE MUST BE THE appno-MERGE of three 2025 files (all keyed on the JEE
    #   application number, 12,103 rows each, perfect 1:1 overlap):
    #     1. "JEE 2025 - All JNV Candidates" (Avanti enrichment): avanti_studentid,
    #        `final program`, jeeTotal (percentile), YEAROFPASSING12.
    #     2. NTA "Appeared Candidates Data": CNAME, DOB, GENDER, CAT, ranks.  <- names/DOB
    #     3. NTA "Registered Candidates Data": rollno (12th board roll), QualDistrict,
    #        QualState, 12th marks (obtainedMark/totalMark/percentageOfMarks).
    #   The current pipeline points at file (1) ALONE, so student_full_name / dob /
    #   12th roll / district / state come out NULL. The candidates below resolve
    #   correctly once the merged file is the source.
    # - NO 10th board roll exists in ANY 2025 NTA file (registration captures only the
    #   12th marksheet). So jnv_fact_board_results_10th can only be linked by name+DOB
    #   (district-scoped via QualDistrict) — ~50-64% per program, not the 92-99%
    #   id-join that 2024's "10th Roll Number" allows. roll_no_10 stays NULL for 2025.
    # - `final program` tags only the 813 Avanti-touched students; the ~11,290 untagged
    #   rows are the JNV PMU control pool (program NULL by design).
    "columns": {
        "application_no":           ["JEEApplicationNumber", "APPNO"],
        "program":                  ["final program", "12th Program", "Program Model"],
        "student_full_name":        ["CNAME", "Student Name"],
        "dob":                      ["DOB", "DoB"],
        "student_gender":           ["Gender", "GENDER"],
        "_pwd_raw":                 ["PWD"],
        "category":                 ["Category", "CAT"],
        "student_state":            ["State12", "QualState"],
        "district_12":              ["District", "QualDistrict", "District12"],
        "place_of_school":          ["PlaceofSchool", "PlaceofSchooling", "School_or_CollegeName_Address"],
        "jnv_name":                 ["jnvname", "JNV Name"],
        "roll_no_12":               ["rollno", "12th Roll Number"],
        "year_of_passing_12":       ["YEAROFPASSING12", "yearOfPassing"],
        "board_12":                 ["boardName", "Board", "School_Board"],
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
