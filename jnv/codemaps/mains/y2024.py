CODEMAP = {
    "source": {
        "file": "JEE Mains 2024.xlsx",
        "sheet": "JEE Mains",
        "header": 0,
    },
    "constants": {
        "test_year": "2024",
        "test_name": "JEE",
        "mains_max_score": 300,
        "jee_adv_ineligible": None,
    },
    # 2024 notes:
    # - 10th and 12th board columns use explicit "10th "/"12th " prefixes in the
    #   raw (jee_mains_2024.parquet), e.g. "10th Marks Scored" / "12th Marks Scored".
    # - category_rank and category_pwd_rank are provided as direct columns
    #   (no per-category split), so obc_rank/sc_rank/st_rank/ews_rank are null.
    # - No roll numbers available.
    "columns": {
        "application_no":           ["Application Number", "APPNO"],
        "avanti_student_id":        ["Student ID"],
        "student_full_name":        ["Student Name", "CNAME"],
        "dob":                      ["DoB", "DOB"],
        "student_gender":           ["Gender", "GENDER"],
        "_pwd_raw":                 ["PWD", "PwD"],
        "category":                 ["Category", "CAT"],
        "student_state":            ["State12", "StateName", "State"],
        "district_12":              ["District12", "districtName", "District"],
        "place_of_school":          ["PlaceofSchooling", "PlaceofSchool"],
        "jnv_name":                 ["JNV Name", "Final JNV", "DB JNV Name"],
        "jnv_region":               ["DB JNV Region"],
        # 10th board — raw uses explicit "10th " prefixes (jee_mains_2024.parquet)
        "year_of_passing_10":       ["Year of Passing 10th (Verified)", "Year of Passing", "yearOfPassing"],
        "board_10":                 ["10th Board", "Board", "boardName"],
        "marks_10_obtained":        ["10th Marks Scored", "Marks Scored", "obtainedMark"],
        "marks_10_total":           ["10th Total Marks", "Total Marks", "totalMark"],
        "marks_10_pct":             ["10th CGPA / %", "CGPA/%", "percentageOfMarks"],
        # 12th board — second occurrence (.1 suffix assigned by pandas)
        "year_of_passing_12":       ["Year of Passing 12th", "Year of Passing.1", "yearOfPassing.1"],
        "board_12":                 ["12th Board", "Board.1", "boardName.1"],
        "marks_12_obtained":        ["12th Marks Scored", "Marks Scored.1", "obtainedMark.1"],
        "marks_12_total":           ["12th Total Marks", "Total Marks.1", "totalMark.1"],
        "marks_12_pct":             ["12th CGPA / %", "CGPA/%.1", "percentageOfMarks.1"],
        "mains_appeared_for_exam":        ["Total"],
        "mains_physics_score":            ["Physics"],
        "mains_chemistry_score":          ["Chemistry"],
        "mains_maths_score":              ["Mathematics"],
        "mains_total_score":              ["Total"],
        # Direct category rank columns — no per-category split for 2024
        "mains_all_india_rank":           ["All India Rank"],
        "mains_category_rank":            ["Category Rank"],
        "mains_all_india_pwd_rank":       ["All India Rank (PwD)"],
        "mains_category_pwd_rank":        ["Category Rank (PwD)"],
        "jee_mains_qualified":      ["Qualified"],
    },
}
