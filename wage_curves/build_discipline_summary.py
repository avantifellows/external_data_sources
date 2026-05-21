"""
Cross-discipline wage-curve summary (NIRF + AISHE + PLFS), one row per discipline.

For each discipline: the NIRF-ranked elite (grads, placement rate, weighted
median wage), the AISHE canonical graduating class, the residual "Other X
Colleges" share, and the PLFS population wage anchor. Where a clean DEGREE-based
PLFS anchor exists (Engineering, Agriculture) the residual wage is back-solved
the same way as the engineering curve. Where only an OCCUPATION anchor exists
(Law) or the AISHE total is a shared cluster (Medical), the anchor is shown as
reference and the residual wage is left unsolved (basis mismatch).

Engineering's detailed IIT/NIT/IIIT tiering lives in build_wage_curve.py; here
it appears at discipline level for comparability.

Sources: NIRF (BQ nirf_fact_aggregate), AISHE (../aishe/clean/outturn.parquet),
PLFS anchors (../plfs/analyses/wage_by_discipline.py — degree-based; or PLFS NCO
occupation cuts for doctors/lawyers). All PLFS figures annualised (×12).

Run: python3 wage_curves/build_discipline_summary.py
"""

import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
AISHE_PARQUET = ROOT.parent / "aishe" / "clean" / "outturn.parquet"

# discipline -> config
DISCIPLINES = [
    dict(name="Engineering", nirf=["Engineering"], yr=2022,
         aishe=["Engineering & Technology"],
         plfs=360000, plfs_basis="degree (Eng, 22-28)", reconcile=True),
    dict(name="Law", nirf=["Law"], yr=2022,
         aishe=["Law"],
         plfs=510000, plfs_basis="occupation (legal prof NCO-261, 25-34)", reconcile=False),
    dict(name="Agriculture & Allied", nirf=["Agriculture and Allied Sectors"], yr=2023,
         aishe=["Agriculture", "Veterinary & Animal Sciences", "Fisheries Science"],
         plfs=252000, plfs_basis="degree (Agri, 22-28; small n)", reconcile=True),
    dict(name="Medical cluster", nirf=["Medical", "Dental", "Pharmacy"], yr=2022,
         aishe=["Medical Science", "Paramedical Science"],
         plfs=389000, plfs_basis="degree (Medicine&Health, all ages); MBBS docs ₹64k", reconcile=False,
         note="govt MBBS/BDS detailed in govt_medical_seats.csv + medical_salaries.csv"),
]

# NIRF-only reference (AISHE folds these into Engineering / Medical Science)
NIRF_ONLY = [("Pharmacy", ["Pharmacy"], 2022),
             ("Dental", ["Dental"], 2022),
             ("Architecture & Planning", ["Architecture and Planning"], 2022)]


def nirf_rollup(categories, year):
    cats = ",".join(f'"{c}"' for c in categories)
    sql = f"""
    WITH agg AS (
      SELECT * FROM `avantifellows.external_data_sources.nirf_fact_aggregate`
      WHERE ranking_category IN ({cats}) AND ranking_year = {year}
    ),
    grad AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY institute_id, ranking_category, type ORDER BY academic_year DESC) rn
      FROM agg WHERE students_placed IS NOT NULL
    )
    SELECT COUNT(DISTINCT institute_id) n_inst,
           ROUND(SUM(graduating_on_time)) grads,
           ROUND(100*SUM(students_placed)/NULLIF(SUM(graduating_on_time),0),1) placement_rate,
           ROUND(SUM(median_salary*students_placed)/NULLIF(SUM(students_placed),0)) wtd_median
    FROM grad WHERE rn = 1
    """
    out = subprocess.run(["bq", "query", "--use_legacy_sql=false", "--format=csv"],
                         input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"bq failed for {categories} {year}:\n{out.stderr}")
    return list(csv_dicts(out.stdout))[0]


def csv_dicts(text):
    import csv as _csv
    return _csv.DictReader(io.StringIO(text))


def aishe_total(disciplines):
    df = pd.read_parquet(AISHE_PARQUET)
    sl = df[(df.aishe_year == "2021-22") & (df.state == "All") & (df.social_category == "All")
            & (df.programme == "All") & (df.gender == "Total") & (df.level == "Under Graduate")
            & (df.discipline.isin(disciplines))]
    return float(sl.out_turn.sum())


def f0(x):
    return f"{float(x):,.0f}" if x not in (None, "", "NULL") else "—"


def main():
    rows = []
    print("=" * 122)
    print("CROSS-DISCIPLINE WAGE-CURVE SUMMARY  —  NIRF ranked elite vs AISHE total vs PLFS anchor")
    print("=" * 122)
    hdr = (f'{"Discipline":<22}{"NIRF yr":>7}{"NIRF n":>7}{"NIRF grads":>11}{"Place%":>8}'
           f'{"NIRF ₹/yr":>11}{"AISHE total":>12}{"Other %":>8}{"PLFS ₹/yr":>11}{"Other ₹/yr":>11}')
    print(hdr); print("-" * 122)
    for d in DISCIPLINES:
        r = nirf_rollup(d["nirf"], d["yr"])
        ngrads = float(r["grads"]) if r["grads"] not in (None, "", "NULL") else 0
        atot = aishe_total(d["aishe"])
        resid = atot - ngrads
        other_pct = resid / atot * 100 if atot else None
        other_wage = None
        if d["reconcile"] and r["wtd_median"] not in (None, "", "NULL") and resid > 0:
            known = ngrads * float(r["wtd_median"])
            other_wage = (d["plfs"] * atot - known) / resid
        print(f'{d["name"]:<22}{d["yr"]:>7}{f0(r["n_inst"]):>7}{f0(r["grads"]):>11}'
              f'{(r["placement_rate"]+"%" if r["placement_rate"] not in (None,"","NULL") else "—"):>8}'
              f'{f0(r["wtd_median"]):>11}{f0(atot):>12}'
              f'{(f"{other_pct:.0f}%" if other_pct is not None else "—"):>8}'
              f'{f0(d["plfs"]):>11}{f0(other_wage):>11}')
        rows.append(dict(discipline=d["name"], nirf_year=d["yr"], nirf_n_inst=r["n_inst"],
                         nirf_grads=r["grads"], nirf_placement_pct=r["placement_rate"],
                         nirf_median_inr=r["wtd_median"], aishe_total_ug=int(atot),
                         other_share_pct=round(other_pct, 1) if other_pct is not None else None,
                         plfs_anchor_inr=d["plfs"], plfs_basis=d["plfs_basis"],
                         implied_other_inr=round(other_wage) if other_wage else None,
                         note=d.get("note", "")))
    print("-" * 122)
    print("NIRF-only (AISHE folds these into Engineering / Medical Science — no clean residual):")
    for name, cats, yr in NIRF_ONLY:
        r = nirf_rollup(cats, yr)
        print(f'  {name:<26} {yr}  n={f0(r["n_inst"])}  grads={f0(r["grads"])}  '
              f'place={r["placement_rate"]}%  median=₹{f0(r["wtd_median"])}/yr')
        rows.append(dict(discipline=name + " (NIRF-only)", nirf_year=yr, nirf_n_inst=r["n_inst"],
                         nirf_grads=r["grads"], nirf_placement_pct=r["placement_rate"],
                         nirf_median_inr=r["wtd_median"], aishe_total_ug=None, other_share_pct=None,
                         plfs_anchor_inr=None, plfs_basis="", implied_other_inr=None,
                         note="AISHE total subsumed in another discipline"))

    pd.DataFrame(rows).to_csv(ROOT / "discipline_summary.csv", index=False)
    print(f"\nWrote {ROOT.name}/discipline_summary.csv")
    print("Notes: Law/Medical not reconciled (occupation anchor / shared AISHE cluster). "
          "Engineering detailed tiers in build_wage_curve.py; medical detail in "
          "govt_medical_seats.csv + medical_salaries.csv.")


if __name__ == "__main__":
    main()
