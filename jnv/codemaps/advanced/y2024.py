import pandas as pd


def post_transform(raw_df, out_df):
    """
    Normalize application_no: the 2024 Excel stores it as a float
    (scientific notation), which must be cast to an integer string so it
    matches the string format in the mains data.
    """
    def _norm(val):
        if pd.isna(val):
            return None
        try:
            return str(int(float(str(val).strip())))
        except (ValueError, TypeError):
            return str(val).strip()

    out_df["application_no"] = out_df["application_no"].apply(_norm)
    return out_df


CODEMAP = {
    "source": {
        "file":   "JEE Advanced 2024.xlsx",
        "sheet":  "Sheet1",
        "header": 0,
    },
    "constants":    {"test_year": "2024", "adv_appeared": True},
    "zero_is_null": False,   # 2024 uses NaN for missing ranks
    "columns": {
        "application_no":        ["JEE Main Application Number"],
        "adv_all_india_rank":    ["CRL"],
        "adv_all_india_pwd_rank": ["CRL_PWD"],
        "adv_obc_rank":          ["OBC_NCL"],
        "adv_sc_rank":           ["SC"],
        "adv_st_rank":           ["ST"],
        "adv_ews_rank":          ["GEN_EWS"],
        "adv_obc_pwd_rank":      ["OBC_NCL_PWD"],
        "adv_sc_pwd_rank":       ["SC_PWD"],
        "adv_st_pwd_rank":       ["ST_PWD"],
        "adv_ews_pwd_rank":      ["GEN_EWS_PWD"],
        "adv_prep_sc_rank":      ["PREP_SC"],
        "adv_prep_st_rank":      ["PREP_ST"],
        "adv_prep_sc_pwd_rank":  ["PREP_SC_PWD"],
        "adv_prep_st_pwd_rank":  ["PREP_ST_PWD"],
        "adv_prep_obc_pwd_rank": ["PREP_OBC_NCL_PWD"],
        "adv_prep_ews_pwd_rank": ["PREP_GEN_EWS_PWD"],
        "adv_prep_crl_pwd_rank": ["PREP_CRL_PWD"],
    },
    "post_transform": post_transform,
}
