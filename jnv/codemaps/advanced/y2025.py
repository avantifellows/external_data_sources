CODEMAP = {
    "source": {
        "file":   "JEE Advanced 2025 .xlsx",
        "sheet":  "Sheet1",
        "header": 0,
    },
    "constants":    {"test_year": "2025", "adv_appeared": True},
    # 2025 file uses 0 for "no rank" instead of NaN — to_adv_rank treats 0 as null.
    "zero_is_null": True,
    "columns": {
        # student_id in the advanced file equals JEEApplicationNumber in the mains file
        # (confirmed: 1142/1142 overlap across both datasets).
        "application_no":        ["student_id"],
        "adv_all_india_rank":    ["CRL"],
        "adv_all_india_pwd_rank": ["CRL_PwD"],
        "adv_obc_rank":          ["OBC"],
        "adv_sc_rank":           ["SC"],
        "adv_st_rank":           ["ST"],
        "adv_ews_rank":          ["EWS"],
        "adv_obc_pwd_rank":      ["OBC_PwD"],
        "adv_sc_pwd_rank":       ["SC_PwD"],
        "adv_st_pwd_rank":       ["ST_PwD"],
        "adv_ews_pwd_rank":      ["EWS_PwD"],
        "adv_prep_sc_rank":      ["PREP_SC"],
        "adv_prep_st_rank":      ["PREP_ST"],
        "adv_prep_sc_pwd_rank":  ["PREP_SC_PwD"],
        "adv_prep_st_pwd_rank":  ["PREP_ST_PwD"],
        "adv_prep_obc_pwd_rank": ["PREP_OBC_PwD"],
        "adv_prep_ews_pwd_rank": ["PREP_EWS_PwD"],
        "adv_prep_crl_pwd_rank": ["PREP_CRL_PwD"],
    },
}
