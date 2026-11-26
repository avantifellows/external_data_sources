from pathlib import Path

import numpy as np
import pandas as pd

# JEE Mains 2025.xlsx is a 4,037-row subset of All JNV Candidates that carries
# CNAME, DOB, FNAME, MNAME — columns absent from the main file.
_MAINS_2025 = Path(__file__).resolve().parent.parent.parent / "raw" / "jee_mains" / "JEE Mains 2025.xlsx"

# Recovery copy: a cleaned export of the 2025 results that has the name, the DOB and the
# 12th roll number of the candidates. The NTA raw file with the name and the DOB is missing,
# so this file is not the source of record. It only fills the cells that the raw files
# leave empty. See "JEE 2025: the recovery copy" in jnv/README.md.
_RECOVERY_2025 = Path(__file__).resolve().parent.parent.parent / "raw" / "jee_mains" / "jee_2025_clean.parquet"
_RECOVERY_COLS = ["student_full_name", "dob", "roll_no_12"]


def _blank(series):
    """True where a cell has no value (null, or a string that is empty or a null marker)."""
    return series.isna() | series.astype(str).str.strip().isin(["", "nan", "None", "<NA>"])


def _recovery_dob(series):
    """Write each DOB of the recovery copy as DD-MM-YYYY.

    The file has two formats: DD-MM-YYYY (dash, day first) and M/D/YYYY (slash, month
    first). The slash dates are changed to the dash format; a date that does not parse
    becomes null.
    """
    s = series.astype("string").str.strip()
    slash = s.str.contains("/", na=False)
    parsed = pd.to_datetime(s[slash], format="%m/%d/%Y", errors="coerce").dt.strftime("%d-%m-%Y")
    s = s.astype(object)
    s[slash] = parsed.astype(object)
    return s.where(s.notna(), None)


def fill_from_recovery_copy(out_df):
    """Fill the empty name, DOB and 12th roll number cells from the recovery copy.

    The join key is the JEE application number. A cell that has a value does not change.
    """
    if not _RECOVERY_2025.exists():
        print(f"    [2025] WARN: {_RECOVERY_2025} not found — rows without a name stay empty")
        return out_df

    rec = pd.read_parquet(_RECOVERY_2025, columns=["application_no", *_RECOVERY_COLS])
    rec["application_no"] = rec["application_no"].astype(str).str.strip()
    if rec["application_no"].duplicated().any():
        raise ValueError("jee_2025_clean.parquet has an application number on more than one row")
    rec["dob"] = _recovery_dob(rec["dob"])
    rec = rec.rename(columns={c: f"_r_{c}" for c in _RECOVERY_COLS})

    out_df["application_no"] = out_df["application_no"].astype(str).str.strip()
    n_before = len(out_df)
    out_df = out_df.merge(rec, on="application_no", how="left")
    assert len(out_df) == n_before
    for col in _RECOVERY_COLS:
        src = out_df[f"_r_{col}"]
        if col not in out_df.columns:
            out_df[col] = None
        fill = _blank(out_df[col]) & ~_blank(src)
        out_df[col] = out_df[col].astype(object).where(~fill, src.astype(object))
        out_df = out_df.drop(columns=[f"_r_{col}"])
        print(f"    [2025] recovery copy: {col} filled on {int(fill.sum()):,} rows, "
              f"{int((~_blank(out_df[col])).sum()):,} / {len(out_df):,} rows now have a value")
    return out_df


def post_transform(raw_df, out_df):
    """
    1. Merge name/DOB/parent names from JEE Mains 2025.xlsx (4,037-row subset
       that has CNAME/DOB/FNAME/MNAME, absent from All JNV Candidates).
       Then fill the name, DOB and 12th roll number that are still empty
       from the recovery copy (jee_2025_clean.parquet).
    2. Derive mains_category_pwd_rank from per-category PWD rank columns.
    3. Capture jee_adv_qualified / jee_prep_qualified from the mains file
       into the _from_data columns as a fallback.  clean_jee.py will
       override these with rank-derived values for students who appear in
       the advanced Excel file.
    """
    # ── Step 1: merge identity fields from JEE Mains 2025.xlsx ──────────────────
    if _MAINS_2025.exists():
        mains = pd.read_excel(_MAINS_2025, dtype=str)[["APPNO", "CNAME", "DOB", "FNAME", "MNAME"]]
        mains = mains.rename(columns={
            "APPNO": "application_no",
            "CNAME": "_m_name",
            "DOB":   "_m_dob",
            "FNAME": "_m_father",
            "MNAME": "_m_mother",
        })
        mains["application_no"] = mains["application_no"].str.strip()
        out_df["application_no"] = out_df["application_no"].astype(str).str.strip()
        out_df = out_df.merge(mains, on="application_no", how="left")
        # Fill nulls in the canonical columns from the Mains file
        for src, dst in [("_m_name", "student_full_name"), ("_m_dob", "dob"),
                         ("_m_father", "father_name"), ("_m_mother", "mother_name")]:
            if dst in out_df.columns:
                out_df[dst] = out_df[dst].where(out_df[dst].notna(), out_df[src])
            else:
                out_df[dst] = out_df[src]
            out_df = out_df.drop(columns=[src])
        filled = out_df["student_full_name"].notna().sum()
        print(f"    [2025] merged JEE Mains 2025.xlsx: {filled:,} / {len(out_df):,} rows now have a name")
    else:
        print(f"    [2025] WARN: {_MAINS_2025} not found — name/DOB will be null for all 2025 rows")

    # ── Step 1b: fill the cells that are still empty from the recovery copy ──────
    out_df = fill_from_recovery_copy(out_df)

    cols_lower = {c.lower().strip(): c for c in raw_df.columns}

    # ── mains_category_pwd_rank ───────────────────────────────────────────────
    pwd_col_map = {
        "PWD-OBC": "OBC_PH_rank",
        "PWD-SC":  "SC_PH_rank",
        "PWD-ST":  "ST_PH_rank",
        "PWD-EWS": "EWS_PH_rank",
        "PWD-Gen": "AIR_PH_Rank",
    }

    def _resolve(cat):
        raw_name = pwd_col_map.get(str(cat), "")
        actual = cols_lower.get(raw_name.lower(), "")
        return actual if actual and actual in raw_df.columns else None

    pwd_ranks = []
    for cat, idx in zip(out_df["category"], out_df.index):
        col = _resolve(cat)
        val = raw_df.at[idx, col] if col else np.nan
        try:
            pwd_ranks.append(float(val) if not pd.isna(val) else np.nan)
        except (TypeError, ValueError):
            pwd_ranks.append(np.nan)
    out_df["mains_category_pwd_rank"] = pwd_ranks

    # ── mains-file qualification flags (fallback for students not in adv file) ─
    def _to_bool(val):
        if pd.isna(val):
            return None
        return str(val).strip().lower() in ("true", "1", "yes", "y", "eligible")

    for src_col, dst_col in [
        ("jee_adv_qualified",  "jee_advanced_qualified_from_data"),
        ("jee_prep_qualified", "jee_prep_qualified_from_data"),
    ]:
        actual = cols_lower.get(src_col.lower())
        if actual and actual in raw_df.columns:
            out_df[dst_col] = raw_df[actual].apply(_to_bool)
        else:
            out_df[dst_col] = None

    # ── adv_prep_category_rank from mains file ────────────────────────────────
    actual = cols_lower.get("adv_prep_category_rank")
    if actual and actual in raw_df.columns:
        out_df["adv_prep_category_rank"] = raw_df[actual].apply(
            lambda v: float(v) if not pd.isna(v) else np.nan
        )

    return out_df


CODEMAP = {
    "source": {
        # Use the full JNV cohort file — it supersedes JEE Mains 2025.xlsx
        # (12,103 rows vs 4,037) and carries richer JNV metadata.
        "file": "JEE 2025 - All JNV Candidates.xlsx",
        "sheet": "JEE 2025 - All JNV Candidates",
        "header": 0,
    },
    "constants": {
        "test_year": "2025",
        "test_name": "JEE",
        "mains_max_score": 300,
        "jee_adv_ineligible": None,
    },
    # 2025 notes:
    # - Final scores only in this file (no session-level P1A/P1B columns).
    # - mains_category_pwd_rank derived via post_transform.
    # - jee_advanced_qualified_from_data / jee_prep_qualified_from_data written
    #   by post_transform as fallback; overridden for students in the advanced
    #   Excel file during the merge step in clean_jee.py.
    # - SOURCE MUST BE THE appno-MERGE of three 2025 files (all keyed on the JEE
    #   application number, 12,103 rows each, perfect 1:1 overlap):
    #     1. "JEE 2025 - All JNV Candidates" (Avanti enrichment): avanti_studentid,
    #        `final program`, jeeTotal (percentile), YEAROFPASSING12.
    #     2. NTA "Appeared Candidates Data": CNAME, DOB, GENDER, CAT, ranks.  <- names/DOB
    #     3. NTA "Registered Candidates Data": rollno (12th board roll), QualDistrict,
    #        QualState, 12th marks (obtainedMark/totalMark/percentageOfMarks).
    #   The current pipeline points at file (1) ALONE, so student_full_name / dob /
    #   12th roll / district / state come out NULL. The candidates below resolve
    #   correctly once the merged file is the source.
    # - NO 10th board roll exists in ANY 2025 NTA file (registration captures only the
    #   12th marksheet). So jnv_fact_board_results_10th can only be linked by name+DOB
    #   (district-scoped via QualDistrict) — ~50-64% per program, not the 92-99%
    #   id-join that 2024's "10th Roll Number" allows. roll_no_10 stays NULL for 2025.
    # - `final program` tags only the 813 Avanti-touched students; the ~11,290 untagged
    #   rows are the JNV PMU control pool (program NULL by design).
    "columns": {
        "application_no":           ["JEEApplicationNumber", "APPNO"],
        "program":                  ["final program", "12th Program", "Program Model"],
        "student_full_name":        ["CNAME", "Student Name"],
        "dob":                      ["DOB", "DoB"],
        "student_gender":           ["Gender", "GENDER"],
        "_pwd_raw":                 ["PWD"],
        "category":                 ["Category", "CAT"],
        "student_state":            ["State12", "QualState"],
        "district_12":              ["District", "QualDistrict", "District12"],
        "place_of_school":          ["PlaceofSchool", "PlaceofSchooling", "School_or_CollegeName_Address"],
        "jnv_name":                 ["jnvname", "JNV Name"],
        "roll_no_12":               ["rollno", "12th Roll Number"],
        "year_of_passing_12":       ["YEAROFPASSING12", "yearOfPassing"],
        "board_12":                 ["boardName", "Board", "School_Board"],
        "marks_12_obtained":        ["obtainedMark"],
        "marks_12_total":           ["totalMark"],
        "marks_12_pct":             ["percentageOfMarks"],
        "mains_appeared_for_exam":  ["jeeTotal", "PS_TOT_P1F"],
        "mains_physics_score":      ["jeePhysics", "PS_PHY_P1F"],
        "mains_chemistry_score":    ["jeeChemistry", "PS_CHE_P1F"],
        "mains_maths_score":        ["jeeMathematics", "PS_MAT_P1F"],
        "mains_total_score":        ["jeeTotal", "PS_TOT_P1F"],
        "mains_all_india_rank":     ["AIR_Rank"],
        "mains_all_india_pwd_rank": ["AIR_PH_Rank"],
        "mains_obc_rank":           ["OBC_rank"],
        "mains_sc_rank":            ["SC_rank"],
        "mains_st_rank":            ["ST_rank"],
        "mains_ews_rank":           ["EWS_rank"],
        "jee_mains_qualified":      ["JeeQualified"],
    },
    "post_transform": post_transform,
}
