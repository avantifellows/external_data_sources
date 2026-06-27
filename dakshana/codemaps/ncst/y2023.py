"""
NCST 2023 column mapping.

Source: NCST 2023.xlsx  sheet: "NCST 2023"
Contact column "parent_mobile 1" is intentionally excluded.
Caste → category; NVS Region → nvs_region.
Reasoning score is stored as a negative integer in some rows (penalty only,
no positive marks) — kept as-is; clean up in analytics if needed.
"""

CODEMAP = {
    "source": {
        "file":  "NCST 2023.xlsx",
        "sheet": "NCST 2023",
        "header": 0,
    },
    "constants": {
        "test_year": "2023",
    },
    "columns": {
        "roll_no":                   ["NCST Roll No"],
        "student_full_name":         ["Student Name"],
        "student_gender":            ["Gender"],
        "category":                  ["Caste"],
        "physically_disabled":       ["P.D."],
        "stream":                    ["Stream"],
        "school_name":               ["School Name"],
        "nvs_region":                ["NVS Region"],
        "annual_family_income":      ["Annual Family Income"],
        "staff_ward":                ["Staff Ward"],
        "is_father_late":            ["is_father_late"],
        "coaching_preference_1":     ["Coaching partner preference 1"],
        "coaching_preference_2":     ["Coaching partner preference 2"],
        "coaching_preference_3":     ["Coaching partner preference 3"],
        "physics_effective_score":   ["Physics Effective Score"],
        "chemistry_effective_score": ["Chemistry Effective Score"],
        "math_bio_effective_score":  ["Math/Biology Effective Score"],
        "reasoning_effective_score": ["Reasoning Effective Score"],
        "total_effective_score":     ["Total Effective Score"],
    },
    # no post_transform needed
}
