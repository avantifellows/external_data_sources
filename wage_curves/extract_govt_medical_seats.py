"""
Pull the government MBBS + BDS seat counts into the source context for the
medical wage curve. Government medical colleges are the targeted segment
(analogous to IIT/NIT/IIIT on the engineering side) — they lead to MBBS/BDS
doctors and are what Avanti targets.

SOURCES (two, documented per row in the output CSV):
  MBBS -> repo nmc/ source: ../nmc/clean/mbbs_seats.parquet
          NMC "Revised UG Seat Matrix 2024-25" (as on 31-03-2025), nmc.org.in.
          Government = any management label containing "Govt" (incl. govt-society).
  BDS  -> "Avanti college DB": ../../College DB/medical-national-ranks/extracted_data/
          bds_govt_colleges_2025-26.csv and bds_all_colleges_2025-26.csv
          (DCI/MCC seat matrix). BDS is not in NMC (it's regulated by the DCI).

Cross-check: NMC govt MBBS (430 colleges / 60,324 seats) matches the College DB
mbbs_govt_colleges_2024-25.csv exactly.

NOTE: placement rate + wages for these are NOT here. Doctor outcomes don't work
like engineering placements (internship → PG entrance / govt service), so they
need an external source. PLFS "Medicine & Health" is the available population
wage anchor (see wage_by_discipline.py).

OUTPUT: wage_curves/govt_medical_seats.csv
Run:    python3 wage_curves/extract_govt_medical_seats.py
"""

from pathlib import Path
import sys
import pandas as pd

HERE = Path(__file__).resolve().parent
NMC_PARQUET = HERE.parent / "nmc" / "clean" / "mbbs_seats.parquet"
CDB_MED = HERE.parent.parent / "College DB" / "medical-national-ranks" / "extracted_data"
OUT = HERE / "govt_medical_seats.csv"

NMC_SRC = "NMC Revised UG Seat Matrix 2024-25 (repo nmc/ source)"
BDS_SRC = "Avanti college DB (medical-national-ranks; DCI/MCC)"


def main():
    rows = []

    # ---- MBBS from the repo NMC source ----
    if not NMC_PARQUET.exists():
        sys.exit(f"NMC parquet not found at {NMC_PARQUET}")
    mbbs = pd.read_parquet(NMC_PARQUET)
    is_govt = mbbs.management.str.contains("Govt", case=False, na=False)
    g = mbbs[is_govt]
    rows.append(["MBBS", "Government", len(g), int(g.annual_intake_seats.sum()),
                 "2024-25", NMC_SRC, "management contains 'Govt' incl. govt-society"])
    rows.append(["MBBS", "Private", int((~is_govt).sum()), int(mbbs.loc[~is_govt, "annual_intake_seats"].sum()),
                 "2024-25", NMC_SRC, "Trust / Society / Private"])
    rows.append(["MBBS", "All", len(mbbs), int(mbbs.annual_intake_seats.sum()),
                 "2024-25", NMC_SRC, ""])

    # ---- BDS from the Avanti College DB ----
    bds_g = pd.read_csv(CDB_MED / "bds_govt_colleges_2025-26.csv")
    bds_a = pd.read_csv(CDB_MED / "bds_all_colleges_2025-26.csv")
    gseats = int(pd.to_numeric(bds_g["intake_2025_26"], errors="coerce").sum())
    aseats = int(pd.to_numeric(bds_a["intake_2025_26"], errors="coerce").sum())
    rows.append(["BDS", "Government", len(bds_g), gseats, "2025-26", BDS_SRC, "govt dental colleges"])
    rows.append(["BDS", "Private", len(bds_a) - len(bds_g), aseats - gseats, "2025-26", BDS_SRC, "All − Government"])
    rows.append(["BDS", "All", len(bds_a), aseats, "2025-26", BDS_SRC, ""])

    out = pd.DataFrame(rows, columns=["program", "segment", "colleges", "ug_seats",
                                      "year", "source", "note"])
    out.to_csv(OUT, index=False)
    print(f"Wrote {OUT.relative_to(HERE.parent)}\n")
    print(out.to_string(index=False))
    gov = out[(out.segment == "Government")]
    print(f"\nGovernment medical (target) total: "
          f"{int(gov.colleges.sum())} colleges, {int(gov.ug_seats.sum()):,} UG seats.")


if __name__ == "__main__":
    main()
