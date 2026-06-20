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
    # - "10th Roll Number" (100% populated) is the board-table merge key:
    #   jnv_fact_jee_results.roll_no_10 == jnv_fact_board_results_10th.roll_number
    #   (board exam_year = test_year - 2). "12th Roll Number" is partial (~33%).
    # - "12th Program" (100% populated) carries the program tag for every NTA student
    #   (JNV ENABLE / Non JNV / Avanti Nodal / Dakshana CoE / ENF CoE / Avanti CoE / ...).
    #   "12th Program" (100%) is the primary; "Final Program" (Avanti-verified, sparse)
    #   is only a fallback if the primary is ever absent.
    # - district / state use "10th "/"12th " prefixed columns (100%); the old
    #   District12/State12 candidates never matched, leaving them NULL.
    "columns": {
        "application_no":           ["Application Number", "APPNO"],
        "avanti_student_id":        ["Student ID"],
        "program":                  ["12th Program", "Final Program", "Program Model"],
        "student_full_name":        ["Student Name", "CNAME"],
        "dob":                      ["DoB", "DOB"],
        "student_gender":           ["Gender", "GENDER"],
        "_pwd_raw":                 ["PWD", "PwD"],
        "category":                 ["Category", "CAT"],
        "student_state":            ["12th State", "10th State", "State12", "StateName", "State"],
        "district_12":              ["12th District", "District12", "districtName", "District"],
        "district_10":              ["10th District"],
        "place_of_school":          ["12th School Name", "10th School Name", "PlaceofSchooling", "PlaceofSchool"],
        "jnv_name":                 ["JNV Name", "Final JNV", "DB JNV Name"],
        "jnv_region":               ["DB JNV Region"],
        # 10th board — raw uses explicit "10th " prefixes (jee_mains_2024.parquet)
        "roll_no_10":               ["10th Roll Number"],
        "year_of_passing_10":       ["Year of Passing 10th (Verified)", "Year of Passing", "yearOfPassing"],
        "board_10":                 ["10th Board", "Board", "boardName"],
        "marks_10_obtained":        ["10th Marks Scored", "Marks Scored", "obtainedMark"],
        "marks_10_total":           ["10th Total Marks", "Total Marks", "totalMark"],
        "marks_10_pct":             ["10th CGPA / %", "CGPA/%", "percentageOfMarks"],
        # 12th board — second occurrence (.1 suffix assigned by pandas)
        "roll_no_12":               ["12th Roll Number"],
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
