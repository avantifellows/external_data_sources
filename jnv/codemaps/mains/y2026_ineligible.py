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
        "test_name": "JEE",
        "mains_max_score": 300,
        "jee_adv_ineligible": True,
        # All candidates in this file are ineligible — override qualified flag.
        "jee_mains_qualified": False,
    },
    # 2026 ineligible notes:
    # - 2+ year droppers: passed Class 12 before 2024, so ineligible for JEE Advanced.
    # - They can sit JEE Mains but NTA excludes them from Advanced qualification.
    # - jee_advanced_ineligibility_reason (REMARK col) carries the NTA ineligibility message.
    # - Has session-level scores (P1A = Session 1, P1B = Session 2).
    # - No rank columns available.
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
        "mains_appeared_for_exam":        ["PS_TOT_P1F"],
        "mains_physics_score":            ["PS_PHY_P1F"],
        "mains_chemistry_score":          ["PS_CHE_P1F"],
        "mains_maths_score":              ["PS_MAT_P1F"],
        "mains_total_score":              ["PS_TOT_P1F"],
        "mains_physics_score_s1":         ["PS_PHY_P1A"],
        "mains_chemistry_score_s1":       ["PS_CHE_P1A"],
        "mains_maths_score_s1":           ["PS_MAT_P1A"],
        "mains_total_score_s1":           ["PS_TOT_P1A"],
        "mains_physics_score_s2":         ["PS_PHY_P1B"],
        "mains_chemistry_score_s2":       ["PS_CHE_P1B"],
        "mains_maths_score_s2":           ["PS_MAT_P1B"],
        "mains_total_score_s2":           ["PS_TOT_P1B"],
        "jee_adv_ineligibility_reason": ["REMARK"],
    },
}
