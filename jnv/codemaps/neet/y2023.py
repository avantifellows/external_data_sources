CODEMAP = {
    "source": {
        "file": "NEET 2023.xlsx",
        "sheet": "Sheet1",
        "header": 0,
    },
    "constants": {
        "test_year": "2023",
        "test_name": "NEET",
        "neet_max_score": 720,
    },
    # 2023 notes:
    # - applicationNo (camelCase) is the primary key.
    # - Board columns identical to 2022 layout (qualifying-exam block at left of sheet,
    #   NTA score block at right). Treated as 12th board.
    # - percentageOfMarks may carry mixed-fraction strings like "55 2/5" → to_float()
    #   handles these via the fraction parser.
    "columns": {
        "application_no":           ["applicationNo"],
        "roll_no":                  ["ROLL"],
        "student_full_name":        ["CNAME"],
        "dob":                      ["DOB_N"],
        "student_gender":           ["SEX_N"],
        "category":                 ["CAT"],
        "_pwd_raw":                 ["PH"],
        "student_state":            ["APPSTATE_N"],
        "school_code":              ["rollno"],
        "place_of_school":          ["PlaceofSchooling"],
        "jnv_name":                 ["SchoolNameandAddress"],
        "year_of_passing_12":       ["yearOfPassing"],
        "board_12":                 ["SchoolBoard"],
        "marks_12_obtained":        ["obtainedMark"],
        "marks_12_total":           ["totalMark"],
        "marks_12_pct":             ["percentageOfMarks"],
        "neet_appeared_for_exam":   ["RLRW"],
        "neet_physics_percentile":  ["PTILE_PHY"],
        "neet_chemistry_percentile":["PTILE_CHE"],
        "neet_biology_percentile":  ["PTILE_BIO"],
        "neet_total_percentile":    ["PTILE"],
        "neet_total_score":         ["TOTAL"],
        "neet_all_india_rank":      ["AI_RANK", "NEET_R"],
        "neet_category_rank":       ["NEET_CAT_R"],
        "neet_all_india_pwd_rank":  ["NEET_PWD_R"],
    },
}
