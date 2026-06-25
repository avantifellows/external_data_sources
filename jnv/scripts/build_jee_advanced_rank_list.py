"""
build_jee_advanced_rank_list.py — raw NTA JEE-Advanced rank lists -> one clean, harmonised table.

NTA publishes a JEE-Advanced result file per year for the JNV cohort. The yearly files do NOT share a
schema: 2025 keys students by `advrollno` + Avanti `student_id`; 2024 keys by JEE-Main application number
+ name/DoB and uses older category labels (GEN_EWS, OBC_NCL). This script reads each year's raw CSV and
emits ONE harmonised parquet: `jnv_fact_jee_advanced_rank_list`.

Grain: one row per ranked candidate per test_year. A candidate appears only if NTA published an Advanced
rank for them (i.e. they qualified Advanced), so every row = an Advanced qualifier.

Raw inputs (canonical home is gs://avantifellows-external-data/jnv/raw/; until staged there, point RAW at
the local working copy). Run:  python3 scripts/build_jee_advanced_rank_list.py [--raw DIR]
Output: clean/jnv_fact_jee_advanced_rank_list.parquet  (gitignored; lives in GCS, not git).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = Path(os.environ.get("JNV_RAW", ROOT / "raw" / "jee_advanced"))
CLEAN = ROOT / "clean"

# canonical reserved-category columns the harmonised table exposes (open + 4 reserved, each +PwD)
RANK_COLS = ["crl", "ews", "obc", "sc", "st",
             "crl_pwd", "ews_pwd", "obc_pwd", "sc_pwd", "st_pwd"]
PREP_COLS = ["prep_crl_pwd", "prep_ews_pwd", "prep_obc_pwd", "prep_sc", "prep_sc_pwd",
             "prep_st", "prep_st_pwd"]

# per-year raw header -> canonical name. Anything not listed is dropped.
MAP_2025 = {"advrollno": "adv_roll_no", "cname": "student_name", "student_id": "student_id",
            "School_or_CollegeName_Address": "school_name", "State": "state",
            "CRL": "crl", "CRL_PwD": "crl_pwd", "EWS": "ews", "EWS_PwD": "ews_pwd",
            "OBC": "obc", "OBC_PwD": "obc_pwd", "SC": "sc", "SC_PwD": "sc_pwd",
            "ST": "st", "ST_PwD": "st_pwd",
            "PREP_CRL_PwD": "prep_crl_pwd", "PREP_EWS_PwD": "prep_ews_pwd",
            "PREP_OBC_PwD": "prep_obc_pwd", "PREP_SC": "prep_sc", "PREP_SC_PwD": "prep_sc_pwd",
            "PREP_ST": "prep_st", "PREP_ST_PwD": "prep_st_pwd"}
MAP_2024 = {"JEE Main Application Number": "jee_main_application_no", "Student Name": "student_name",
            "DoB": "dob", "Gender": "gender", "JNV School Name": "school_name", "JNV State": "state",
            "CRL": "crl", "GEN_EWS": "ews", "OBC_NCL": "obc", "SC": "sc", "ST": "st",
            "CRL_PWD": "crl_pwd", "GEN_EWS_PWD": "ews_pwd", "OBC_NCL_PWD": "obc_pwd",
            "SC_PWD": "sc_pwd", "ST_PWD": "st_pwd",
            "PREP_CRL_PWD": "prep_crl_pwd", "PREP_GEN_EWS_PWD": "prep_ews_pwd",
            "PREP_OBC_NCL_PWD": "prep_obc_pwd", "PREP_SC": "prep_sc", "PREP_SC_PWD": "prep_sc_pwd",
            "PREP_ST": "prep_st", "PREP_ST_PWD": "prep_st_pwd"}

YEARS = {"2024": ("JEE Advanced 2024.csv", MAP_2024),
         "2025": ("JEE Advanced 2025.csv", MAP_2025)}

ALL_OUT = (["test_year", "adv_roll_no", "student_id", "jee_main_application_no", "student_name",
            "dob", "gender", "school_name", "state"] + RANK_COLS + PREP_COLS
           + ["crl_rank", "category", "category_rank", "is_pwd", "prep_qualified", "qualified"])


def load_year(year: str, fname: str, colmap: dict, raw: Path) -> pd.DataFrame:
    df = pd.read_csv(raw / fname, dtype=str, keep_default_na=False)
    df = df.rename(columns={k: v for k, v in colmap.items() if k in df.columns})
    df = df[[c for c in df.columns if c in colmap.values()]].copy()
    df["test_year"] = year
    for c in ALL_OUT:                                            # ensure every output column exists
        if c not in df.columns:
            df[c] = ""
    # ranks to numeric (blank/0 -> 0); a rank > 0 means the candidate is on that list
    for c in RANK_COLS + PREP_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    return df


def derive(df: pd.DataFrame) -> pd.DataFrame:
    reserved = ["ews", "obc", "sc", "st"]                        # open = crl; reserved = the rest
    df["crl_rank"] = df["crl"]
    # category = the reserved list the candidate is ranked on (non-PwD); else 'CRL' if only open; else ''
    def cat_row(r):
        for c in reserved:
            if r[c] > 0 or r[f"{c}_pwd"] > 0:
                return c.upper()
        return "CRL" if (r["crl"] > 0 or r["crl_pwd"] > 0) else ""
    df["category"] = df.apply(cat_row, axis=1)
    df["category_rank"] = df.apply(
        lambda r: next((r[c] or r[f"{c}_pwd"] for c in reserved if r[c] > 0 or r[f"{c}_pwd"] > 0),
                       r["crl"] or r["crl_pwd"]), axis=1).astype(int)
    df["is_pwd"] = df[[c for c in RANK_COLS + PREP_COLS if c.endswith("pwd")]].gt(0).any(axis=1)
    df["prep_qualified"] = df[PREP_COLS].gt(0).any(axis=1)
    df["qualified"] = df[RANK_COLS].gt(0).any(axis=1)            # any real (non-prep) rank = Adv qualifier
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(DEFAULT_RAW))
    a = ap.parse_args()
    raw = Path(a.raw)
    parts = [derive(load_year(y, f, m, raw)) for y, (f, m) in YEARS.items()]
    out = pd.concat(parts, ignore_index=True)[ALL_OUT]
    CLEAN.mkdir(exist_ok=True)
    dest = CLEAN / "jnv_fact_jee_advanced_rank_list.parquet"
    out.to_parquet(dest, index=False)
    print(f"wrote {dest}  ({len(out):,} rows)")
    print(out.groupby(["test_year", "category"]).size().unstack(fill_value=0).to_string())
    print(f"\nqualified={int(out.qualified.sum()):,}  prep={int(out.prep_qualified.sum()):,}  "
          f"pwd={int(out.is_pwd.sum()):,}  with student_id={int((out.student_id != '').sum()):,}  "
          f"with appno={int((out.jee_main_application_no != '').sum()):,}")


if __name__ == "__main__":
    main()
