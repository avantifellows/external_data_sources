CODEMAP = {
    "source": {
        "file": "NEET 2022.xlsx",
        "sheet": "Full Data",
        "header": 0,
    },
    "constants": {
        "test_year": "2022",
        "test_name": "NEET",
        "neet_max_score": 720,
    },
    # 2022 notes:
    # - Has a "Qualified" column (Yes/No) → neet_qualified_from_data.
    # - Board columns (SchoolBoard, yearOfPassing, etc.) cover the qualifying exam
    #   (usually 12th for NEET candidates); treated as 12th board data.
    # - rollno = JNV roll number → school_code.
    # - PlaceofSchooling = Rural/Urban → place_of_school.
    # - SchoolNameandAddress contains JNV name → jnv_name.
    # - Column "400" (integer key) is a legacy NTA artifact; ignored.
    "columns": {
        "application_no":           ["appno"],
        "roll_no":                  ["roll"],
        "student_full_name":        ["cname"],
        "dob":                      ["dob_n"],
        "student_gender":           ["sex_n"],
        "category":                 ["cat"],
        "_pwd_raw":                 ["ph"],
        "student_state":            ["appstate_n"],
        "school_code":              ["rollno"],
        "place_of_school":          ["PlaceofSchooling"],
        "jnv_name":                 ["SchoolNameandAddress"],
        "year_of_passing_12":       ["yearOfPassing"],
        "board_12":                 ["SchoolBoard"],
        "marks_12_obtained":        ["obtainedMark"],
        "marks_12_total":           ["totalMark"],
        "marks_12_pct":             ["percentageOfMarks"],
        "neet_appeared_for_exam":   ["rlrw"],
        "neet_physics_percentile":  ["ptile_phy"],
        "neet_chemistry_percentile":["ptile_che"],
        "neet_biology_percentile":  ["ptile_bio"],
        "neet_total_percentile":    ["ptile"],
        "neet_total_score":         ["total"],
        "neet_all_india_rank":      ["neet_r"],
        "neet_category_rank":       ["neet_cat_r"],
        "neet_all_india_pwd_rank":  ["neet_pwd_r"],
        "neet_qualified_from_data": ["Qualified"],
    },
}
