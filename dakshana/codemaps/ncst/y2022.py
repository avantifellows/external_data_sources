"""
NCST 2022 column mapping.

Source: NCST 2022.xlsx  sheet: "NCST2022 Full Data"
The file has two columns named "Region" — pandas renames the duplicate to
"Region.1" (a district-code column we ignore). Only the first "Region" is
mapped to nvs_region.
DOB is stored as a datetime object; the engine converts it to YYYY-MM-DD.
father_annual_income and mother_annual_income are income-bracket labels
(e.g. "Less than 1 lakh"), not numeric — kept as strings.
The Y/N column encodes is_father_late.
"""

import pandas as pd


def _post_transform(raw_df: pd.DataFrame, out_df: pd.DataFrame) -> pd.DataFrame:
    # DOB: datetime → YYYY-MM-DD string
    dob_col = next(
        (c for c in raw_df.columns if str(c).strip().lower() == "dob"),
        None,
    )
    if dob_col:
        out_df["dob"] = pd.to_datetime(raw_df[dob_col], errors="coerce").dt.strftime("%Y-%m-%d")

    return out_df


CODEMAP = {
    "source": {
        "file":  "NCST 2022.xlsx",
        "sheet": "NCST2022 Full Data",
        "header": 0,
    },
    "constants": {
        "test_year": "2022",
    },
    "columns": {
        "roll_no":                  ["Dakshana ID"],
        "student_full_name":        ["Student Name"],
        "student_gender":           ["Gender"],
        "category":                 ["Category"],
        "physically_disabled":      ["P.D."],
        "stream":                   ["Stream"],
        "school_name":              ["School Name"],
        "nvs_region":               ["Region"],           # first occurrence wins
        "annual_family_income":     ["Annual Family Income"],
        "father_annual_income":     ["father_annual_income"],
        "mother_annual_income":     ["mother_annual_income"],
        "staff_ward":               ["Staff Ward"],
        "is_father_late":           ["Y/N"],
        "coaching_preference_1":    ["Preference_1"],
        "coaching_preference_2":    ["Preference_2"],
        "coaching_preference_3":    ["Preference_3"],
        "physics_effective_score":  ["Physics Effective Score"],
        "chemistry_effective_score": ["Chemistry Effective Score"],
        "math_bio_effective_score": ["Maths/Bio Effective Score"],
        "reasoning_effective_score": ["Reasoning Effective Score"],
        "total_effective_score":    ["Total Effective Score"],
    },
    "post_transform": _post_transform,
}
