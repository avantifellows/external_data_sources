CODEMAP = {
    "source": {
        "file": "NEET 2025.xlsx",
        "sheet": "Sheet1",
        "header": 0,
    },
    "constants": {
        "test_year": "2025",
        "test_name": "NEET",
        "neet_max_score": 720,
    },
    # 2025 notes:
    # - Minimal columns: only total marks and total percentile; no per-subject scores.
    # - PwBD column (Yes/No string) is the PWD indicator.
    # - STATE OF ELIGIBILITY maps to student_state.
    # - schoolType10th / schoolType12th indicate JNV vs non-JNV school type; not mapped
    #   to canonical columns but available via post_transform if needed.
    # - PRESENT/ABSENT = 'P' or 'A'.
    "columns": {
        "application_no":           ["APPLICATION NUMBER"],
        "roll_no":                  ["ROLL"],
        "student_full_name":        ["CANDIDATE NAME"],
        "dob":                      ["DOB"],
        "student_gender":           ["GENDER"],
        "category":                 ["CATEGORY"],
        "_pwd_raw":                 ["PwBD"],
        "student_state":            ["STATE OF ELIGIBILITY"],
        "neet_appeared_for_exam":   ["PRESENT/ABSENT"],
        "neet_total_percentile":    ["TOTAL PERCENTILE"],
        "neet_total_score":         ["TOTAL MARKS"],
        "neet_all_india_rank":      ["ALL INDIA RANK"],
        "neet_category_rank":       ["NEET CATEGORY RANK"],
        "neet_all_india_pwd_rank":  ["NEET PWD RANK"],
    },
}
