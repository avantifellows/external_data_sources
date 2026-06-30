"""
NAS 2021 — aggregate state-level performance/proficiency to NATIONAL, by
management & location, for grades 3 / 5 / 8 / 10. Written to
clean/national_proficiency.parquet.

Inputs (raw/NAS-2021-data/csv_data/):
  performance_percentage_statewise/*_by_management.csv  (semicolon-separated)
  performance_percentage_statewise/*_by_location.csv
  NAS_participation_state.csv

Output (BQ: nas_fact_national_proficiency), one row per
  (grade, subject, dimension, category) → pct_correct_mean,
  pct_proficient_advanced, pct_basic_below_basic                  (90 rows)

Method:
  NAS publishes percent-correct and proficiency-band data at the STATE level
  only. We aggregate to national using student-count weights, derived as
  total_student × share-of-students-from-this-category. The share columns
  (govt_school, private_school, rural_location, …) are percentages of the
  state's sampled student count from each management / location bucket.

  IMPORTANT: NAS reports "% Proficient and Advance" as a single combined band
  (top tail) and "% Basic and Below Basic" as the bottom tail. It does not
  publish the four-band split separately in this data set.

Usage:
  python3 scripts/clean_nas.py
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, SOURCE_CSV_DIR, TABLES

PERF_DIR = SOURCE_CSV_DIR / "performance_percentage_statewise"
PART_CSV = SOURCE_CSV_DIR / "NAS_participation_state.csv"

# (category label, pct_correct col, proficient+advance col, basic+below col, share col)
MGMT_SPECS = [
    ("State Govt", "govt", "govt_proficient_and_advance",
     "govt_basic_and_below_basic", "govt_school"),
    ("Govt Aided", "govt_aided", "govt_aided_proficient_and_advance",
     "govt_aided_basic_and_below_basic", "govt_aided_school"),
    ("Private Recognised", "private", "private_proficient_and_advance",
     "private_basic_and_below_basic", "private_school"),
    ("Central Govt", "central_govt", "central_govt_proficient_and_advance",
     "central_govt_basic_and_below_basic", "central_govt_school"),
]
LOC_SPECS = [
    ("Rural", "rural", "rural_proficient_and_advance",
     "rural_basic_and_below_basic", "rural_location"),
    ("Urban", "urban", "urban_proficient_and_advance",
     "urban_basic_and_below_basic", "urban_location"),
]


def _read_concat(pattern: str) -> pd.DataFrame:
    files = glob.glob(str(PERF_DIR / pattern))
    if not files:
        raise SystemExit(f"no files matched {PERF_DIR / pattern}")
    return pd.concat([pd.read_csv(f, sep=";") for f in files], ignore_index=True)


def load_mgmt() -> pd.DataFrame:
    return _read_concat("*_by_management.csv")


def load_loc() -> pd.DataFrame:
    return _read_concat("*_by_location.csv")


def load_part() -> pd.DataFrame:
    if not PART_CSV.exists():
        raise SystemExit(f"missing participation file: {PART_CSV}")
    p = pd.read_csv(PART_CSV, sep=";")
    # Some states have multiple rows per (state, grade); keep the latest.
    return p.sort_values("id").groupby(["state_name", "grade"]).last().reset_index()


def weighted(df_perf: pd.DataFrame, df_part: pd.DataFrame, val_col: str, share_col: str) -> float:
    """National student-weighted average of val_col across states.
    Weight = total_student × share_col / 100 from the participation file.
    """
    m = df_perf.merge(
        df_part[["state_name", "grade", "total_student", share_col]],
        on=["state_name", "grade"],
        how="inner",
    )
    m["wt"] = m["total_student"] * m[share_col] / 100.0
    m = m.dropna(subset=[val_col, "wt"])
    m = m[m["wt"] > 0]
    if m["wt"].sum() == 0:
        return float("nan")
    return (m[val_col] * m["wt"]).sum() / m["wt"].sum()


def build_df() -> pd.DataFrame:
    mgmt = load_mgmt()
    loc = load_loc()
    part = load_part()
    rows = []
    panels = [(mgmt, MGMT_SPECS, "management"), (loc, LOC_SPECS, "location")]

    # ── STATE-level rows: each state's category values read directly from the
    #    source CSV (NAS publishes at state level; no weighting needed). ──
    for df_perf, specs, dim in panels:
        for _, r in df_perf.iterrows():
            for cat, pc_col, pa_col, bb_col, _share in specs:
                rows.append({
                    "state": r["state_name"],
                    "grade": int(r["grade"]),
                    "subject": r["subject"],
                    "dimension": dim,
                    "category": cat,
                    "pct_correct_mean": r.get(pc_col),
                    "pct_proficient_advanced": r.get(pa_col),
                    "pct_basic_below_basic": r.get(bb_col),
                })

    # ── 'All India' rollup: student-weighted national average across states. ──
    for grade in [3, 5, 8, 10]:
        for df_perf, specs, dim in panels:
            for subj in sorted(df_perf["subject"].unique()):
                sub = df_perf[(df_perf["grade"] == grade) & (df_perf["subject"] == subj)]
                if len(sub) == 0:
                    continue
                for cat, pc_col, pa_col, bb_col, share_col in specs:
                    rows.append({
                        "state": "All India",
                        "grade": grade,
                        "subject": subj,
                        "dimension": dim,
                        "category": cat,
                        "pct_correct_mean": weighted(sub, part, pc_col, share_col),
                        "pct_proficient_advanced": weighted(sub, part, pa_col, share_col),
                        "pct_basic_below_basic": weighted(sub, part, bb_col, share_col),
                    })

    cols = ["state", "grade", "subject", "dimension", "category",
            "pct_correct_mean", "pct_proficient_advanced", "pct_basic_below_basic"]
    df = pd.DataFrame(rows, columns=cols)
    for c in ["pct_correct_mean", "pct_proficient_advanced", "pct_basic_below_basic"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").round(2)
    df["grade"] = df["grade"].astype("int64")
    return df


def main() -> None:
    df = build_df()
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = TABLES[0].local_path
    df.to_parquet(out, index=False, engine="pyarrow")
    print(f"nas_fact_state_proficiency: {len(df):,} rows → {out.name}")
    print(f"  states={df.state.nunique()} (incl. All India)  grades={sorted(df.grade.unique())}  "
          f"subjects={df.subject.nunique()}  dimensions={df.dimension.nunique()}")
    print("\nAll India, Class 5 math:")
    print(df[(df.state == "All India") & (df.grade == 5) & (df.subject == "math")].to_string(index=False))


if __name__ == "__main__":
    main()
