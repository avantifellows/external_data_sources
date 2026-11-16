#!/usr/bin/env python3
"""
NCST 2027 Screening test (4 Oct 2026) -> clean parquet, one row per registered student.

Source: NVS's combined shortlisting file of 16 Nov 2026 (sheet "NCST List"), sent by Dakshana to NVS
on behalf of the three agencies (Avanti Fellows, Dakshana, ENF). It holds every Class X student who
registered (46,191: 43,244 present, 2,947 absent), their registration details, the test-day sheet's
details, marks by subject, stream and coaching preferences, and which agency shortlisted them for the
NCST main test on 13 Dec 2026 (11,993 in all).

Dropped at intake (PII not needed for analysis, same call as nvs_fact_ncst_results):
Mobile Number, Alternate Mobile Number, MobileNo, Class Roll Number.
Dropped as unreliable or redundant: Rank (167 distinct values over 43k students, not a rank of any
score here), Class-IX Rank-AIR (mostly blank, negative values), Count (number of agencies; wrong
for 345 students, re-derived from the agency columns), Final Shortlisted.1 (duplicate of Final Shortlisted), School Code+District.

Parse notes (checked on the 16 Nov file):
- Marks: +5 per right answer, -2 per wrong. "+Ve Marks"/"-Ve Marks" (the -ve stored negative) per
  subject; <subject>_score = positive + negative. total_score = sum of the five (max 300).
- "PCMLR/PCBLR" is a FRACTION of 240: (Physics + Chemistry + LR + Maths or Biology) / 240. NVS chose
  Maths for "Engineering" first and Biology for "Medical" first; for the rest it is mixed.
- "1st_choice" is NVS's own reading of the four stream ranks. On paper sets B, C and D it labels every
  student who ranked Medical 1 "Engineering/Medical"; only set A says "Medical". Kept as
  nvs_first_choice for the record; use the four stream_rank_* columns.
- Stream ranks are text: "1"-"4", "0" and "*" appear as written on the sheet.
- Registration columns (gender, category, disability, income) and the test-day sheet's (Gender,
  Category, Phy Disability, Income/Income Range) disagree for some students; both are kept.
- Registration category has both "GEN" and "Gen": category_raw keeps it as written; category is canonical
  (Gen / Gen-EWS / OBC / SC / ST, the values the results tables use).

Usage:
    python3 scripts/clean_screening.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import SCREENING_CLEAN, RAW_SCREENING_FILES

SUBJECTS = [("physics", "", "Phy_Total"), ("chemistry", ".1", "Chem_Total"), ("biology", ".2", "Bio_Total"),
            ("maths", ".3", "Math_Total"), ("lr", ".4", "LR_Total")]
# canonical values as in nvs_fact_ncst_results / dakshana_fact_ncst_results, so the tables UNION
CATEGORY = {"GEN": "Gen", "Gen": "Gen", "GEN-EWS": "Gen-EWS", "Gen-EWS": "Gen-EWS", "OBC-NCL": "OBC", "SC": "SC", "ST": "ST"}


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def yes_no(s: pd.Series) -> pd.Series:
    v = s.astype("string").str.strip().str.lower()
    return v.map({"yes": True, "no": False}).astype("boolean")


def build(raw: pd.DataFrame) -> pd.DataFrame:
    d = raw.apply(lambda c: c.str.strip() if c.dtype == object else c)
    out = pd.DataFrame({
        "test_year": "2027",
        "exam_stage": "screening",
        "exam_date": "2026-10-04",
        "roll_no": d["NCST Roll No"],
        "student_full_name": d["Student Name"],
        "student_gender": d["Gender(Male/Female)"],
        "category_raw": d["Category (GEN/GEN-EWS/OBC-NCL/SC/ST)"],
        "category": d["Category (GEN/GEN-EWS/OBC-NCL/SC/ST)"].map(CATEGORY),
        "physically_disabled": yes_no(d["Physically Disabled (Yes/No)"]),
        "staff_ward": yes_no(d["Staff Ward (Yes / No)"]),
        "annual_family_income": num(d["Family Annual Income"]),
        "school_code": num(d["School Code"]).astype("Int64"),
        "school_name": d["School Name"],
        "school_district": d["School District"],
        "state": d["School State"],
        "attendance": d["Attendance"],
        "test_day_gender": d["Gender"],
        "test_day_category": d["Category"],
        "test_day_physically_disabled": d["Phy Disability"],
        "test_day_income_bracket": d["Income"],
        "test_day_income_range": d["Income Range"],
        "test_day_school_code": d["SchoolCode"],
        "cc_drn_code": d["CC-DRN"],
        "qp_set": d["PaperSet"],
        "grade_9_maths_marks": num(d["9th Maths Marks (out of 100) - Annual Exam"]),
        "grade_9_science_marks": num(d["9th Science Marks (out of 100) - Annual Exam"]),
        "grade_9_maths_science_avg": num(d["9th M+Sc Avg"]),
        "grade_9_english_marks": num(d["9th English Marks (out of 100) - Annual Exam"]),
        "coaching_preference_1": d["Coaching Preference 1(Dakshana/Avanti/Ex-Navodaya)"],
        "coaching_preference_2": d["Coaching Preference 2(Dakshana/Avanti/Ex-Navodaya)"],
        "coaching_preference_3": d["Coaching Preference 3(Dakshana/Avanti/Ex-Navodaya)"],
        "stream_rank_engineering": d["Engineering"],
        "stream_rank_medical": d["Medical"],
        "stream_rank_commerce": d["Commerce"],
        "stream_rank_humanities": d["Humanities"],
        "nvs_first_choice": d["1st_choice"],
    })
    for name, sfx, tot in SUBJECTS:
        out[f"{name}_positive_marks"] = num(d[f"+Ve Marks{sfx}"])
        out[f"{name}_negative_marks"] = num(d[f"-Ve Marks{sfx}"])
        out[f"{name}_score"] = num(d[tot])
    out["total_score"] = num(d["All Subject"])
    out["nvs_stream_score_fraction"] = num(d["PCMLR/PCBLR"])
    out["final_status"] = d["Final Shortlisted"]
    out["is_shortlisted"] = d["Final Shortlisted"].eq("Yes")
    for col, agency in (("shortlisted_by_avanti", "Shortlisted by Avanti"), ("shortlisted_by_enf", "Shortlisted by ENF"),
                        ("shortlisted_by_dakshana", "Shortlisted by Dakshana")):
        out[col] = d[agency].notna()
    out["shortlisting_agency_count"] = out[["shortlisted_by_avanti", "shortlisted_by_enf", "shortlisted_by_dakshana"]].sum(axis=1).astype("int64")
    return out


def check(raw: pd.DataFrame, out: pd.DataFrame) -> None:
    """Quality gates: the build fails rather than load a table that disagrees with its source."""
    assert len(out) == len(raw) == 46191, len(out)
    assert out["roll_no"].is_unique and out["roll_no"].notna().all()
    assert not out.duplicated().any()
    assert (out["attendance"].value_counts().to_dict() == {"Present": 43244, "Absent": 2947})
    assert out["category"].notna().all(), out.loc[out["category"].isna(), "category_raw"].unique()
    p = out["attendance"].eq("Present")
    for name, _, _ in SUBJECTS:
        ok = (out[f"{name}_positive_marks"] + out[f"{name}_negative_marks"] - out[f"{name}_score"]).abs().lt(1e-9)
        assert ok[p].all(), name
    tot = out[[f"{s}_score" for s, _, _ in SUBJECTS]].sum(axis=1)
    assert (tot - out["total_score"]).abs()[p].lt(1e-9).all()
    assert out.loc[~p, "total_score"].isna().all()
    assert out["is_shortlisted"].sum() == 11993 and out.loc[out["is_shortlisted"], "attendance"].eq("Present").all()
    assert out["is_shortlisted"].equals(out["shortlisting_agency_count"] > 0)
    assert (out["shortlisted_by_avanti"].sum(), out["shortlisted_by_enf"].sum(), out["shortlisted_by_dakshana"].sum()) == (9081, 5000, 4405)
    # NVS's own "Count" says 2 for 345 students marked by one agency only (202 ENF, 143 Dakshana) on
    # 16 Nov; the agency columns reconcile with each agency's list, so the count is derived from them.
    off = num(raw["Count"]).fillna(0).astype(int) != out["shortlisting_agency_count"]
    assert off.sum() == 345, off.sum()
    print("  ✓ gates: 46,191 rows, unique roll_no, no duplicates, subject and total marks reconcile, "
          "11,993 shortlisted (Avanti 9,081, ENF 5,000, Dakshana 4,405)")


def main() -> None:
    src = RAW_SCREENING_FILES[0]
    print(f"Reading {src.local_path.name} [{src.sheet}] ...")
    raw = pd.read_excel(src.local_path, sheet_name=src.sheet, dtype=str)
    out = build(raw)
    check(raw, out)
    SCREENING_CLEAN.local_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(SCREENING_CLEAN.local_path, index=False)
    print(f"  ✓ {SCREENING_CLEAN.local_path}  ({len(out):,} rows, {len(out.columns)} columns)")


if __name__ == "__main__":
    main()
