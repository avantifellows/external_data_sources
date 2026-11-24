"""
Pull the IIT / NIT / IIIT institute reference from the **Avanti College DB**
into this repo as a documented CSV, for the wage-curve "unranked publics"
adjustment.

WHY: NIRF only ranks a subset of the centrally-funded technical institutes
(2022: 19 of 23 IITs, 28 of 31 NITs, 5 of 30 IIITs). To move the un-ranked ones
out of the "Other Engg Colleges" residual and into their proper tier (at the
tier's NIRF-average wage, per the analysis spec), we need the *full* count of
each type. The Avanti College DB has it.

SOURCE: "Avanti college DB"  (../../College DB)
  - josaa-ranks/extracted_data/_institute_lookup.csv
        institute_type (IIT/NIT/IIIT/GFTI/IIEST), college_id, college_name,
        state, management_type, top_200_nirf, salary_tier
  - avanti-college-db-v1/csv/college_database.csv
        per-college placement_rate (0-1) and median_salary (INR), various
        vintages — deduped here to one row per college_id (latest year with a
        non-null placement_rate).

NOTE ON VINTAGE: the DB's placement_rate (~0.9) and median_salary (IIT ~₹17L,
NIT ~₹9L, IIIT ~₹11L) are a newer/blended NIRF vintage than the wage curve's
NIRF-2022 anchor (IIT ₹13.0L, NIT ₹7.2L, IIIT ₹13.2L). They are carried here as
a documented reference column only; the synthesis applies the NIRF-2022 tier
averages for internal consistency.

OUTPUT: wage_curves/iit_nit_iiit_institutes_avanti_db.csv  (one row per institute)

Run:  python3 wage_curves/extract_avanti_college_db.py
"""

from pathlib import Path
import sys
import pandas as pd

HERE = Path(__file__).resolve().parent
COLLEGE_DB = HERE.parent.parent / "College DB"
LOOKUP = COLLEGE_DB / "josaa-ranks" / "extracted_data" / "_institute_lookup.csv"
DATABASE = COLLEGE_DB / "avanti-college-db-v1" / "csv" / "college_database.csv"
OUT = HERE / "iit_nit_iiit_institutes_avanti_db.csv"

TYPES = ["IIT", "NIT", "IIIT"]
SOURCE = "Avanti college DB"


def main():
    if not LOOKUP.exists() or not DATABASE.exists():
        sys.exit(f"Avanti College DB not found at {COLLEGE_DB}. "
                 f"Expected {LOOKUP} and {DATABASE}.")

    lk = pd.read_csv(LOOKUP)
    lk = lk[lk.institute_type.isin(TYPES)].copy()

    db = pd.read_csv(DATABASE, low_memory=False)
    # One row per college_id: prefer rows that have a placement_rate, then latest year.
    db["_has_pl"] = db.placement_rate.notna().astype(int)
    db = (db.sort_values(["college_id", "_has_pl", "data_year"])
            .groupby("college_id", as_index=False).last())

    m = lk.merge(db[["college_id", "placement_rate", "median_salary"]],
                 on="college_id", how="left")

    out = pd.DataFrame({
        "institute_type": m.institute_type,
        "college_name": m.college_name,
        "state": m.state,
        "management_type": m.management_type,
        "top_200_nirf": m.top_200_nirf,
        # DB placement_rate is a 0-1 fraction; express as percent.
        "placement_rate_pct": (m.placement_rate * 100).round(1),
        "median_salary_inr": m.median_salary,
        "salary_tier": m.salary_tier,
        "source": SOURCE,
    }).sort_values(["institute_type", "college_name"]).reset_index(drop=True)

    out.to_csv(OUT, index=False)

    print(f"Wrote {OUT.relative_to(HERE.parent)}  ({len(out)} institutes)")
    print("\nCounts by type (Avanti College DB):")
    summ = out.groupby("institute_type").agg(
        total_institutes=("college_name", "size"),
        with_placement=("placement_rate_pct", lambda s: s.notna().sum()),
        median_placement_pct=("placement_rate_pct", "median"),
        median_salary_inr=("median_salary_inr", "median"),
    ).reindex(TYPES)
    print(summ.to_string())


if __name__ == "__main__":
    main()
