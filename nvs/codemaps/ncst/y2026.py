"""
NVS NCST 2026 column mapping.

Source: NCST 2026.xlsx  sheet: "NCST Data"  header: 0

Context: 2026 was the first year NCST was conducted at national scale by NVS
directly. Dakshana Foundation set the question paper but the test was
administered to all eligible JNV students across the country. The file covers
~43k students. Dakshana-track students are under-represented (~86 of ~318
Dakshana-selected students appear here; the rest sat a separate process).

Normalization: pre-computed in the source Excel, per-QP-set.
  QP Set A students: Physics × 0.96 | Chemistry × 0.81 | Biology × 1.05
                     Maths × 0.78   | Logical Reasoning × 0.78
  QP Set B students: all subjects × 1.00 (reference set, no adjustment)
  Verified: ratio of normalized/raw is exactly the factor above for every row
  in each set (std = 0.0). Physics column header in source says "0.94" but
  the actual computed factor is 0.96.

Final Score (total_normalized_score) formula — verified exact across all rows:
  NEET: Phy_norm + Chem_norm + LR_norm + 0.5 × Bio_norm
  JEE:  Phy_norm + Chem_norm + LR_norm + 1.0 × Maths_norm
  The 0.5 Bio coefficient exists because Biology raw marks are on a ~2×
  scale vs Maths, so 0.5 × Bio_norm ≈ 1.0 × Maths_norm in contribution.

is_father_late inverts "Is Father alive(Yes/No)":
  Yes (alive) → is_father_late = False
  No  (gone)  → is_father_late = True

PII excluded: Student Mobile, Parent Mobile, Email, Father's Name, Mother's Name.
"""

import pandas as pd


def _post_transform(raw_df: pd.DataFrame, out_df: pd.DataFrame) -> pd.DataFrame:
    # DOB: datetime string → YYYY-MM-DD
    dob_col = next(
        (c for c in raw_df.columns if str(c).strip().lower() == "date of birth"),
        None,
    )
    if dob_col:
        out_df["dob"] = pd.to_datetime(raw_df[dob_col], errors="coerce").dt.strftime("%Y-%m-%d")

    # exam_date: datetime string → YYYY-MM-DD
    edate_col = next(
        (c for c in raw_df.columns if str(c).strip().lower() == "exam date"),
        None,
    )
    if edate_col:
        out_df["exam_date"] = pd.to_datetime(raw_df[edate_col], errors="coerce").dt.strftime("%Y-%m-%d")

    # is_father_late: invert "Is Father alive" (Yes = alive = not late)
    alive_col = next(
        (c for c in raw_df.columns if "father alive" in str(c).lower()),
        None,
    )
    if alive_col:
        alive = raw_df[alive_col].astype(str).str.strip().str.lower()
        # engine's normalize_bool runs after post_transform; pass inverted Yes/No strings
        out_df["is_father_late"] = alive.map(
            lambda s: "Yes" if s in ("no", "n") else ("No" if s in ("yes", "y") else None)
        )

    # household_earning_members: column name has an encoding artifact (Â) — match by partial name
    earning_col = next(
        (c for c in raw_df.columns if "earning members" in str(c).lower()),
        None,
    )
    if earning_col:
        out_df["household_earning_members"] = raw_df[earning_col].values

    return out_df


CODEMAP = {
    "source": {
        "file":   "NCST 2026.xlsx",
        "sheet":  "NCST Data",
        "header": 0,
    },
    "constants": {
        "test_year": "2026",
    },
    "columns": {
        # identity / demographics
        "roll_no":                    ["NCST Roll Number (12-Digit)"],
        "student_full_name":          ["Name"],
        "student_gender":             ["Gender(Male/Female)"],
        "category":                   ["Category (GEN/GEN-EWS/OBC-NCL/SC/ST)"],
        "physically_disabled":        ["Physically Disabled (Yes/No)"],
        "stream":                     ["Applying for JEE/NEET"],
        # dob: datetime → YYYY-MM-DD in post_transform

        # school / geography
        "school_name":                ["School Name"],
        "school_code":                ["School code"],
        "school_district":            ["School District"],
        "state":                      ["School State"],

        # exam metadata
        "attendance":                 ["Attendance"],
        "qp_set":                     ["QP Set"],
        # exam_date: datetime → YYYY-MM-DD in post_transform

        # socioeconomic
        "annual_family_income":       ["Annual Household Income"],
        "father_annual_income":       ["Father's Annual Income"],
        "mother_annual_income":       ["Mother's Annual Income"],
        "staff_ward":                 ["Staff Ward (Yes/No)"],
        # is_father_late: inverted from "Is Father alive" in post_transform

        # coaching preference
        "coaching_preference_1":      ["Coaching Preference 1(Dakshana/Avanti/Ex-Navodaya)"],
        "coaching_preference_2":      ["Coaching Preference 2(Dakshana/Avanti/)"],
        "coaching_preference_3":      ["Coaching Preference 3(Dakshana/Avanti/Ex-Navodaya)"],

        # aggregate scores
        "total_positive_ques":        ["Total Positive Ques"],
        "total_negative_ques":        ["Total Negative Ques"],
        "total_unattempted_ques":     ["Total Unattempted Ques"],
        "total_raw_score":            ["Total Score"],
        "total_normalized_score":     ["Final Score_After Normalization & Bio/Maths-25% Each"],

        # physics — column header in source says "0.94" but actual factor is 0.96 for QP Set A
        "physics_positive_ques":      ["Phy Positive Ques"],
        "physics_negative_ques":      ["Phy Negative Ques"],
        "physics_unattempted_ques":   ["Phy Unattempted Ques"],
        "physics_raw_score":          ["Phy Score"],
        "physics_normalized_score":   ["Phy Total Score_After Normalization (0.94)"],

        # chemistry — QP Set A factor 0.81, Set B factor 1.00
        "chemistry_positive_ques":    ["Chem Positive Ques"],
        "chemistry_negative_ques":    ["Chem Negative Ques"],
        "chemistry_unattempted_ques": ["Chem Unattempted Ques"],
        "chemistry_raw_score":        ["Chem Score"],
        "chemistry_normalized_score": ["Chem Total Score_After Normalization (0.81)"],

        # biology (NEET stream) — QP Set A factor 1.05, Set B factor 1.00
        "bio_positive_ques":          ["Bio Positive Ques"],
        "bio_negative_ques":          ["Bio Negative Ques"],
        "bio_unattempted_ques":       ["Bio Unattempted Ques"],
        "bio_raw_score":              ["Bio Score"],
        "bio_normalized_score":       ["Bio Total Score_After Normalization (1.05)"],

        # maths (JEE stream) — QP Set A factor 0.78, Set B factor 1.00
        "maths_positive_ques":        ["Maths Positive Ques"],
        "maths_negative_ques":        ["Maths Negative Ques"],
        "maths_unattempted_ques":     ["Maths Unattempted Ques"],
        "maths_raw_score":            ["Maths Score"],
        "maths_normalized_score":     ["Maths Total Score_After Normalization (0.78)"],

        # logical reasoning — QP Set A factor 0.78, Set B factor 1.00
        "reasoning_positive_ques":    ["Logical Reasoning Positive Ques"],
        "reasoning_negative_ques":    ["Logical Reasoning Negative Ques"],
        "reasoning_unattempted_ques": ["Logical Reasoning Unattempted Ques"],
        "reasoning_raw_score":        ["Logical Reasoning Score"],
        "reasoning_normalized_score": ["Logical Reasoning Total Score_After Normalization (0.78)"],

        # academic history (self-reported)
        "grade_9_math_marks":         ["9th Math Marks(out of 100)"],
        "grade_9_science_marks":      ["9th Science Marks(out of 100)"],
        "grade_10_math_marks":        ["10th Math Marks(out of 100)"],
        "grade_10_science_marks":     ["10th Science Marks(out of 100)"],
        "grade_9_aggregate_pct":      ["9th Agreegate %"],
        "grade_10_aggregate_pct":     ["10th Agreegate %"],
        "willing_for_coaching":       ["Willing for JEE/NEET Coaching(Yes/No)"],

        # family
        "is_mother_alive":            ["Is mother alive (Yes/No)"],
        "father_education":           ["Father Education(Below 10th/10th/12th/Above 12th)"],
        "father_occupation":          ["Father's Occupation"],
        "mother_education":           ["Mother Education(Below 10th/10th/12th/Above 12th)"],
        "mother_occupation":          ["Mother's Occupation"],
        "guardian":                   ["Guardian (Only if Father/Mother both are no more)"],

        # home address (separate from school location)
        "home_village":               ["Village/House No."],
        "home_post_office":           ["Post Office"],
        "home_district":              ["District"],
        "home_state":                 ["State"],
        "domicile_state":             ["Domicile is of which state"],
        "pin_code":                   ["PIN Code"],

        # household wealth
        "household_assets_value":     ["Total approximate value of all household assets"],
        # household_earning_members: encoding artifact in column name — handled in post_transform
        "household_annual_income":    ["Total typical annual household income"],
        "father_mother_combined_income": ["Father+Mother Annual Income"],
        "max_household_income":       ["Max of Household/Family Income"],
        "household_cash_savings":     ["Total household cash savings"],
        "house_ownership":            ["own house is(own/Rented)"],
        "house_area_sqft":            ["Area of the house(In square foot)"],
        "house_bedrooms":             ["Number of Bedrooms"],
        "locality_type":              ["City/Town Type you live in(Rural/Semi-Urban/Urban)"],
        "is_bpl":                     ["Belongs to BPL Category(Yes/No)"],
        "has_ration_card":            ["Have Ration Card (Yes/No)"],
        "ration_card_color":          ["Color of ration card"],
        "submission_type":            ["Submission Type"],
    },
    "post_transform": _post_transform,
}
