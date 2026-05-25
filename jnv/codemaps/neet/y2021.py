CODEMAP = {
    "source": {
        "file": "NEET 2021.xlsx",
        "sheet": "Total Students Applied",
        "header": 0,
    },
    "constants": {
        "test_year": "2021",
        "test_name": "NEET",
        "neet_max_score": 720,
    },
    # 2021 notes:
    # - Per-subject columns are percentiles (PTILE_PHY/CHE/BIO), TOTAL is raw marks.
    # - NEET_R (rank among appeared) used as neet_all_india_rank; AI_RANK also present
    #   but differs slightly (NEET_R is more consistent with later years).
    # - Only 12th board summary columns (BD_12, YEAR_12, PERC_12) — no marks/total.
    # - RLRW = 'P' (present) / 'A' (absent).
    "columns": {
        "application_no":           ["APPNO"],
        "roll_no":                  ["ROLL"],
        "student_full_name":        ["CNAME"],
        "dob":                      ["DOB_N"],
        "student_gender":           ["SEX_N"],
        "category":                 ["CAT"],
        "_pwd_raw":                 ["PH"],
        "student_state":            ["APPSTATE_N"],
        "year_of_passing_12":       ["YEAR_12"],
        "board_12":                 ["BD_12"],
        "marks_12_pct":             ["PERC_12"],
        "neet_appeared_for_exam":   ["RLRW"],
        "neet_physics_percentile":  ["PTILE_PHY"],
        "neet_chemistry_percentile":["PTILE_CHE"],
        "neet_biology_percentile":  ["PTILE_BIO"],
        "neet_total_percentile":    ["PTILE"],
        "neet_total_score":         ["TOTAL"],
        "neet_all_india_rank":      ["NEET_R", "AI_RANK"],
        "neet_category_rank":       ["NEET_CAT_R"],
        "neet_all_india_pwd_rank":  ["NEET_PWD_R"],
    },
}
