CODEMAP = {
    "source": {
        "file": "JEE 2026 - Passing Candidates graduating before 2025.xlsx",
        "sheet": 0,
        # Header detection is handled by the engine: if the first row yields
        # mostly Unnamed columns, it retries with header=1.
        "header": 0,
        "header_fallback": 1,
    },
    "constants": {
        "test_year": "2026",
        "test_name": "JEE Mains Overall",
        "max_score": 300,
        "eligible": False,
        # All candidates in this file are ineligible — override qualified flag.
        "jee_mains_qualified": False,
    },
    # 2026 ineligible notes:
    # - Candidates passed Class 12 before 2025; not eligible for 2026 JEE.
    # - Has session-level scores (P1A = Session 1, P1B = Session 2).
    # - No rank columns available.
    # - adv_ineligibility_reason populated from REMARK col (long ineligibility message).
    "columns": {
        "application_no":           ["APPNO"],
        "student_full_name":        ["CNAME"],
        "dob":                      ["DOB"],
        "student_gender":           ["GENDER", "Gender"],
        "_pwd_raw":                 ["PWD"],
        "category":                 ["CAT"],
        "school_code":              ["SCODE_E"],
        "student_state":            ["STATE_12P"],
        # 10th board — first (no-suffix) qualification record
        "year_of_passing_10":       ["yearOfPassing"],
        "marks_10_obtained":        ["obtainedMark"],
        "marks_10_total":           ["totalMark"],
        # 12th board — second (.1 suffix) qualification record
        "year_of_passing_12":       ["yearOfPassing.1"],
        "marks_12_obtained":        ["obtainedMark.1"],
        "marks_12_total":           ["totalMark.1"],
        "appeared_for_exam":        ["PS_TOT_P1F"],
        "physics_score":            ["PS_PHY_P1F"],
        "chemistry_score":          ["PS_CHE_P1F"],
        "maths_score":              ["PS_MAT_P1F"],
        "total_score":              ["PS_TOT_P1F"],
        "physics_score_s1":         ["PS_PHY_P1A"],
        "chemistry_score_s1":       ["PS_CHE_P1A"],
        "maths_score_s1":           ["PS_MAT_P1A"],
        "total_score_s1":           ["PS_TOT_P1A"],
        "physics_score_s2":         ["PS_PHY_P1B"],
        "chemistry_score_s2":       ["PS_CHE_P1B"],
        "maths_score_s2":           ["PS_MAT_P1B"],
        "total_score_s2":           ["PS_TOT_P1B"],
        "adv_ineligibility_reason": ["REMARK"],
    },
}
