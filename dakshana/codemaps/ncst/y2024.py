"""
NCST 2024 column mapping.

Source: NCST 2024.xlsx  sheet: "Result"
Contact columns "Mobile" and "Email" are intentionally excluded.
id_candidate, CoE Name, father_education, pincode are also excluded
(not in canonical schema or are contact-adjacent PII).
"FatherName" → father_name (100% populated — enables identity matching in the
DOB-less 2024 file).
NOTE: this file also carries an "Avanti ID" column (a source-provided direct
Avanti student id, populated for ~213/5,988 rows). It is intentionally NOT
mapped into this table — instead the NCST→Avanti fk-linkage step reads it
straight from this raw Excel as a highest-confidence direct-id crosswalk
(mirroring how build_student_outcome_mapping.py reads the JEE-2024 file's
Student ID), and writes the result into fk_avanti_student_id.
father_financial_income / mother_financial_income map to the canonical
income columns; Parents Income → annual_family_income.
State → state (only year with a dedicated state column).
"""

CODEMAP = {
    "source": {
        "file":  "NCST 2024.xlsx",
        "sheet": "Result",
        "header": 0,
    },
    "constants": {
        "test_year": "2024",
    },
    "columns": {
        "roll_no":                   ["Dakshana Roll Number"],
        "student_full_name":         ["Student Name"],
        "father_name":               ["FatherName"],
        "student_gender":            ["gender"],
        "category":                  ["Category"],
        "physically_disabled":       ["PD"],
        "stream":                    ["Stream"],
        "school_name":               ["SchoolName"],
        "state":                     ["State"],
        "annual_family_income":      ["Parents Income"],
        "father_annual_income":      ["father_financial_income"],
        "mother_annual_income":      ["mother_financial_income"],
        "staff_ward":                ["Staff ward"],
        "is_father_late":            ["IsFatherLate"],
        "coaching_preference_1":     ["college_preference_one"],
        "coaching_preference_2":     ["college_preference_two"],
        "coaching_preference_3":     ["college_preference_three"],
        "physics_effective_score":   ["Physics Effective Score"],
        "chemistry_effective_score": ["Chemistry Effective Score"],
        "math_bio_effective_score":  ["Math/Biology Effective Score"],
        "reasoning_effective_score": ["Reasoning Effective Score"],
        "total_effective_score":     ["Total Effective Score"],
    },
    # no post_transform needed
}
