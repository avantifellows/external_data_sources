CODEMAP = {
    "source": {
        "file": "JEE 2026 - All Passing Candidates passing 2025 or later.xlsx",
        "sheet": "Sheet1",
        "header": 0,
    },
    "constants": {
        "test_year": "2026",
        "test_name": "JEE Mains Overall",
        "max_score": 300,
        "jee_adv_ineligible": False,
    },
    # 2026 eligible notes:
    # - Final scores only (no session-level columns in this file).
    # - No rank columns available.
    # - qualificationName (no suffix) = 10th record;
    #   qualificationName.1 = 12th record (pandas duplicate-column suffix).
    # - jee_mains_qualified derived from REMARK col ("ELIGIBLE" string check).
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
        "jee_mains_qualified":      ["REMARK"],
    },
}
