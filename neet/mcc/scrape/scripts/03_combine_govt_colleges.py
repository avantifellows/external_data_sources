"""
Combine govt MBBS + BDS lists into a single canonical roster with state
name harmonisation.

Inputs (from ../extracted_data/):
  - mbbs_govt_colleges_2025-26.csv  (from 01_parse_nmc_mbbs.py)
  - bds_govt_colleges_2025-26.csv   (from 02_parse_dci_bds.py)

Output (to ../extracted_data/):
  - govt_medical_colleges_2025-26.csv  — combined 515 rows
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA = ROOT / "extracted_data"

# Harmonise state-name variants (NMC/DCI use slightly different conventions)
STATE_MAP = {
    "Orissa": "Odisha",
    "Pondicherry": "Puducherry",
    "Chattisgarh": "Chhattisgarh",
    "Jammu & Kashmir": "Jammu and Kashmir",
    "Uttaranchal": "Uttarakhand",
}


def main():
    mbbs = pd.read_csv(DATA / "mbbs_govt_colleges_2025-26.csv")
    mbbs["program"] = "MBBS"
    mbbs = mbbs[["state", "college", "mgmt", "intake_2025_26", "program"]]

    bds = pd.read_csv(DATA / "bds_govt_colleges_2025-26.csv")
    bds["program"] = "BDS"
    bds = bds[["state", "college", "mgmt", "intake_2025_26", "program"]]

    combined = pd.concat([mbbs, bds], ignore_index=True)
    combined["state"] = combined["state"].replace(STATE_MAP)

    combined.to_csv(DATA / "govt_medical_colleges_2025-26.csv", index=False)
    print(f"Wrote govt_medical_colleges_2025-26.csv: {len(combined)} rows")

    print("\nGrand totals:")
    print(combined.groupby("program").agg(
        colleges=("college", "count"),
        intake=("intake_2025_26", "sum"),
    ))
    print(f"\nTotal seats: {combined['intake_2025_26'].sum():,.0f}")


if __name__ == "__main__":
    main()
