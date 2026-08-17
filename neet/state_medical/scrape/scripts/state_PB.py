"""
Punjab NEET UG 2025 — state govt closing ranks pipeline.

Authority: Baba Farid University of Health Sciences (BFUHS), Faridkot.
           https://bfuhs.ac.in
Source PDF: PB_R3_FinalAllotment_2025.pdf
URL: https://bfuhs.ac.in/MBBS2025/FinalAllotmentR3AfterWeedingOut03.11.2025.pdf

Last round used: Round 3 Final (cumulative through R3, after weeding out
                 joined AIQ candidates). Stray Round excluded.

Schema: Sno | Mno | RegNo | Name | Father | NEET Roll | NEET Marks
        | NEET Rank | Categories Applied | Allotted College | Allotted Course
        | Allotted Quota | Allotted Category

Govt-college filter: 4 govt MBBS + 2 govt BDS + 1 ESIC = 7 govt institutions
  - GMC Amritsar, GMC Patiala, GGS MC Faridkot, BR Ambedkar SIMS Mohali
  - Govt Dental College Amritsar/Patiala
  - ESIC Medical College Ludhiana

Reservation taxonomy (Punjab):
  Vertical: Open / Backward Classes / Scheduled Caste / EWS
  Sub-pools: Backward Area, Border Area, J&K Migrants, NRI, Defence,
             Riots Affected, Sports Person, PWD

Outputs (to ../extracted_data/):
  - PB_all_allotments_2025.csv             — raw rows
  - PB_closing_ranks_state_govt_2025.csv   — long format
  - PB_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "PB"
OUT = ROOT / "extracted_data"
STATE_CODE = "PB"
PDF_FILE = SOURCE / "PB_R3_FinalAllotment_2025.pdf"

GOVT_PB = {
    "Government Medical College, Amritsar",
    "Government Medical College, Patiala",
    "Guru Gobind Singh Medical College Faridkot",
    "Dr.B.R Ambedkar State Institute of Medical Sciences S.A.S Nagar,Mohali",
    "ESIC Medical College, Bharat Nagar, Ludhiana",
    "Government Dental College, Amritsar",
    "Government Dental College, Patiala",
}
CAT_MAP = {"Open": "Open", "Scheduled Caste": "SC", "Backward Classes": "BC", "EWS": "EWS"}
ORDER = ["Open", "BC", "EWS", "SC"]


def parse_pb_pdf(path: Path) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 13:
                        continue
                    sno = str(r[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    rec = {
                        "sno": int(sno),
                        "mno": str(r[1] or "").strip(),
                        "reg_no": str(r[2] or "").strip(),
                        "name": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "father": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "neet_roll": str(r[5] or "").strip(),
                        "neet_marks": str(r[6] or "").strip(),
                        "neet_rank": str(r[7] or "").strip().replace(",", ""),
                        "cat_applied": str(r[8] or "").strip(),
                        "allotted_college": re.sub(r"\s+", " ", str(r[9] or "")).strip(),
                        "allotted_course": str(r[10] or "").strip(),
                        "allotted_quota": str(r[11] or "").strip(),
                        "allotted_category": re.sub(r"\s+", " ", str(r[12] or "")).strip(),
                    }
                    try:
                        rec["neet_rank"] = int(rec["neet_rank"])
                    except ValueError:
                        continue
                    rows.append(rec)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Stage 1 — parsing {PDF_FILE.name}...")
    df = parse_pb_pdf(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  {len(df)} rows, {df['allotted_college'].nunique()} colleges")

    print("\nStage 2 — filtering to govt + Govt. Quota...")
    gov = df[
        (df["allotted_college"].isin(GOVT_PB))
        & (df["allotted_quota"] == "Govt. Quota")
    ].copy()
    plain = gov[gov["allotted_category"].isin(CAT_MAP)].copy()
    plain["vert"] = plain["allotted_category"].map(CAT_MAP)
    print(f"  Govt: {len(gov)} rows, plain: {len(plain)}")

    print("\nStage 3 — closing ranks + pivot...")
    cr = (
        plain.groupby(["allotted_college", "allotted_course", "vert"])["neet_rank"]
        .agg(closing_AIR="max", opening_AIR="min", allotted_count="count")
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    piv = cr.pivot_table(
        index=["allotted_college", "allotted_course"], columns="vert",
        values="closing_AIR", aggfunc="first",
    ).reset_index()
    piv = piv[["allotted_college", "allotted_course"]
              + [c for c in ORDER if c in piv.columns]]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")
    print("\n=== Punjab govt ===")
    print(piv.to_string(index=False))


if __name__ == "__main__":
    main()
