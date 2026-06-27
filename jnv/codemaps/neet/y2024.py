CODEMAP = {
    "source": {
        "file": "NEET 2024.xlsx",
        "sheet": "Sheet1",
        "header": 0,
    },
    "constants": {
        "test_year": "2024",
        "test_name": "NEET",
        "neet_max_score": 720,
    },
    # 2024 notes:
    # - Has both 10th and 12th board columns.
    # - "Mathematics" column is BIOLOGY percentile — mislabeled in the source sheet.
    # - "Total" is the overall percentile; "Total Marks" is the raw score.
    # - Has Student ID (Avanti internal) and JNV Name — richer metadata than other years.
    # - No explicit appeared/absent column; all rows represent appeared candidates.
    # - No school_code (JNV roll number) in this file.
    "columns": {
        "application_no":            ["Application Number"],
        "student_full_name":         ["Student Name"],
        "dob":                       ["DoB"],
        "student_gender":            ["Gender"],
        "category":                  ["Category"],
        "student_id":                ["Student ID"],
        "jnv_name":                  ["JNV Name"],
        # 10th board
        "year_of_passing_10":        ["Year of Passing 10th"],
        "board_10":                  ["10th Board"],
        "marks_10_obtained":         ["10th Marks Scored"],
        "marks_10_total":            ["10th Total Marks"],
        "marks_10_pct":              ["10th CGPA / %"],
        # 12th board
        "year_of_passing_12":        ["Year of Passing 12th"],
        "board_12":                  ["12th Board"],
        "marks_12_obtained":         ["12th Marks Scored"],
        "marks_12_total":            ["12th Total Marks"],
        "marks_12_pct":              ["12th CGPA / %"],
        "neet_physics_percentile":   ["Physics"],
        "neet_chemistry_percentile": ["Chemistry"],
        # "Mathematics" is Biology in this NEET file (source label error)
        "neet_biology_percentile":   ["Mathematics"],
        "neet_total_percentile":     ["Total"],
        "neet_total_score":          ["Total Marks"],
        "neet_all_india_rank":       ["All India Rank"],
        "neet_category_rank":        ["Category Rank"],
        "neet_all_india_pwd_rank":   ["PwD Rank"],
    },
}
