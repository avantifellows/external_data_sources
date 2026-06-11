"""
Parse the MCC NEET UG 2025 Final Seat Matrix PDF (AIQ except central
universities). Used as a reference roster of institutes participating in
MCC counselling, with their per-category AIQ seat counts and stable
6-digit institute codes.

Source: ../source/mcc_neet_ug_2025_round1_final_seats.pdf
        Downloaded from
        https://cdnbbsr.s3waas.gov.in/s3e0f7a4d0ef9b84b83b693bbf3feb8e6e/uploads/2025/07/2025072285.pdf
        (Original filename: "updatedFINAL SEATS UG 2025 ROUND 1.xlsx")

Output (to ../extracted_data/):
  - mcc_seat_matrix_2025_clean.csv  — 429 (institute × program) rows
                                      with category-wise AIQ seat split
                                      and stable institute codes.

Note: This file covers AIQ EXCEPT central universities (DU/IPU/AMU/BHU/Jamia).
      Central institutes (AIIMS/JIPMER/ESIC) and central universities are
      counselled through MCC under different sub-pools (100% MCC quota for
      central institutes; specific sub-quotas for central universities).
      The R1 allotments file (05_parse_r1_closing_ranks.py) covers all of
      these.
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
PDF = ROOT / "source" / "mcc_neet_ug_2025_round1_final_seats.pdf"
OUT_DIR = ROOT / "extracted_data"


def main():
    print(f"Parsing {PDF.name}...")
    rows = []
    with pdfplumber.open(PDF) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                rows.extend(table)

    data = []
    for r in rows:
        if not r or len(r) < 12:
            continue
        inst_type = (r[0] or "").strip()
        inst = (r[1] or "").replace("\n", " ").strip()
        program = (r[2] or "").strip()
        quota = (r[3] or "").strip()
        if not inst or not program or inst_type.lower() == "institute type":
            continue
        try:
            total = (
                int(re.sub(r"[^\d]", "", str(r[-1]))) if r[-1] else 0
            )
        except ValueError:
            total = 0
        data.append({
            "institute_type": inst_type.replace("\n", " "),
            "institute_full": inst,
            "program": program,
            "quota": quota,
            "open": r[4], "open_pwd": r[5],
            "ews": r[6], "ews_pwd": r[7],
            "obc": r[8], "obc_pwd": r[9],
            "sc": r[10], "sc_pwd": r[11],
            "st": r[12] if len(r) > 12 else None,
            "st_pwd": r[13] if len(r) > 13 else None,
            "total_seats": total,
        })

    df = pd.DataFrame(data)
    # Extract 6-digit institute code from "Name(200421)" suffix
    df["institute_code"] = df["institute_full"].str.extract(r"\((\d{6})\)$")
    df["institute_name"] = (
        df["institute_full"].str.replace(r"\s*\(\d{6}\)$", "", regex=True).str.strip()
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "mcc_seat_matrix_2025_clean.csv", index=False)

    print(f"  {len(df)} rows ({df['program'].value_counts().to_dict()})")
    print(f"  Institutes with code: {df['institute_code'].notna().sum()}/{len(df)}")
    print(f"  Total AIQ MBBS seats: {df[df['program']=='MBBS']['total_seats'].sum():,}")
    print(f"  Total AIQ BDS seats:  {df[df['program']=='BDS']['total_seats'].sum():,}")


if __name__ == "__main__":
    main()
