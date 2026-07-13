import numpy as np
import pandas as pd

from codemaps.mains.shared import derive_category_pwd_rank


def post_transform(raw_df, out_df):
    pwd_col_map = {
        "PWD-OBC": "AI_OBC1PH",
        "PWD-SC":  "AI_SC1PH",
        "PWD-ST":  "AI_ST1PH",
        "PWD-EWS": "AI_EWS1PH",
        "PWD-Gen": "AI_CRL1PH",
    }
    out_df["mains_category_pwd_rank"] = derive_category_pwd_rank(out_df, raw_df, pwd_col_map)
    return out_df


CODEMAP = {
    "source": {
        "file": "JEE Mains 2021.xlsx",
        "sheet": "FullData",
        "header": 0,
    },
    "constants": {
        "test_year": "2021",
        "test_name": "JEE",
        "mains_max_score": 300,
    },
    # _pwd_raw  → used internally by category normalization
    # appeared_for_exam → points to total score col to detect ABS
    "columns": {
        "application_no":           ["APPNO"],
        "student_full_name":        ["CNAME", "Student Name"],
        "father_name":              ["FNAME"],
        "mother_name":              ["MNAME"],
        "dob":                      ["DOB"],
        "student_gender":           ["GENDER"],
        "_pwd_raw":                 ["PWD"],
        "category":                 ["CAT"],
        "school_code":              ["SCODE_E"],
        "roll_no_s1":               ["rollno", "ROLLNO"],
        "student_state":            ["StateName", "State"],
        "district_12":              ["districtName", "District"],
        "place_of_school":          ["PlaceofSchooling", "PlaceofSchool"],
        "jnv_name":                 ["DB JNV Name", "JNV Name"],
        "jnv_region":               ["DB JNV Region"],
        "year_of_passing_12":       ["yearOfPassing"],
        "board_12":                 ["boardName", "Board"],
        "marks_12_obtained":        ["obtainedMark"],
        "marks_12_total":           ["totalMark"],
        "marks_12_pct":             ["percentageOfMarks"],
        "mains_appeared_for_exam":        ["PS_TOT_F"],
        "mains_physics_score":            ["PS_PHY_F"],
        "mains_chemistry_score":          ["PS_CHE_F"],
        "mains_maths_score":              ["PS_MAT_F"],
        "mains_total_score":              ["PS_TOT_F"],
        "mains_all_india_rank":           ["All India Rank"],
        "mains_all_india_pwd_rank":       ["AI_CRL1PH"],
        "mains_obc_rank":                 ["AI_OBC1"],
        "mains_sc_rank":                  ["AI_SC1"],
        "mains_st_rank":                  ["AI_ST1"],
        "mains_ews_rank":                 ["AI_EWS1"],
        "jee_mains_qualified":      ["Qualified"],
        # NELIG_ADV: True = ineligible for JEE Advanced
        "jee_adv_ineligible":       ["NELIG_ADV"],
        "jee_adv_ineligibility_reason": ["NELIG_ADV", "NELIG_REM"],
    },
    "post_transform": post_transform,
}
