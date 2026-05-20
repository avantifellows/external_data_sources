CODEMAP = {
    "source": {
        "file": "JEE Mains 2024.xlsx",
        "sheet": "JEE Mains",
        "header": 0,
    },
    "constants": {
        "test_year": "2024",
        "test_name": "JEE Mains Overall",
        "max_score": 300,
        "jee_adv_ineligible": None,
    },
    # 2024 notes:
    # - Has both 10th and 12th board columns; pandas assigns .1 suffix to the
    #   second (12th) occurrence of duplicate column names.
    # - category_rank and category_pwd_rank are provided as direct columns
    #   (no per-category split), so obc_rank/sc_rank/st_rank/ews_rank are null.
    # - No roll numbers available.
    "columns": {
        "application_no":           ["Application Number", "APPNO"],
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
        # 10th board — first occurrence of duplicate column names
        "year_of_passing_10":       ["Year of Passing", "yearOfPassing"],
        "board_10":                 ["Board", "boardName"],
        "marks_10_obtained":        ["Marks Scored", "obtainedMark"],
        "marks_10_total":           ["Total Marks", "totalMark"],
        "marks_10_pct":             ["CGPA/%", "percentageOfMarks"],
        # 12th board — second occurrence (.1 suffix assigned by pandas)
        "year_of_passing_12":       ["Year of Passing.1", "yearOfPassing.1"],
        "board_12":                 ["Board.1", "boardName.1"],
        "marks_12_obtained":        ["Marks Scored.1", "obtainedMark.1"],
        "marks_12_total":           ["Total Marks.1", "totalMark.1"],
        "marks_12_pct":             ["CGPA/%.1", "percentageOfMarks.1"],
        "appeared_for_exam":        ["Total"],
        "physics_score":            ["Physics"],
        "chemistry_score":          ["Chemistry"],
        "maths_score":              ["Mathematics"],
        "total_score":              ["Total"],
        # Direct category rank columns — no per-category split for 2024
        "all_india_rank":           ["All India Rank"],
        "category_rank":            ["Category Rank"],
        "all_india_pwd_rank":       ["All India Rank (PwD)"],
        "category_pwd_rank":        ["Category Rank (PwD)"],
        "jee_mains_qualified":      ["Qualified"],
    },
}
