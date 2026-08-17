"""
Chhattisgarh NEET UG 2025 — state govt closing ranks pipeline.

Authority: Directorate of Medical Education (DME), Chhattisgarh.
           https://cgdme.admissions.nic.in
Source PDFs: cdnbbsr.s3waas.gov.in (DGHS NIC hosted on behalf of CGDME)

Last round used: cumulative R1 + R2 (R1 has bulk; R2 has upgrades). Mop-up
                 round excluded per project pattern.

Files:
  - CG_R1_2025.pdf      — Round 1 (14-Aug-2025)
  - CG_R2_2025.pdf      — Round 2 (25-Sep-2025)
  - CG_MopUp_2025.pdf   — Mop-Up (06-Nov-2025) [downloaded for reference]

Schema differs across rounds:
  R1: SN | Roll | Inst | Course | Choice | Quota | AllottedCat | CandCat
      | PH | FF | EX | NEET Rank | NEET Score | CG State Rank
  R2: SN | Roll | Inst | Course | Choice | Quota | AllottedCat | PH | FF | EX
      | NEET Rank | NEET Score | CG State Rank | Remark
  (R2 dropped CandCat column)

Reservation taxonomy (CG):
  Vertical: UR / OBC / SC / ST / SP (Special ST) / EW (EWS)
  Sub-suffixes in allotted_cat:
    -NC = No Class (boys/general — headline)
    -F  = Female (33% horizontal)
    -PH = PwD
    -FF = Freedom Fighter
    -EX = Ex-servicemen

Govt-college filter: Hard-coded list of 10 govt MBBS + 1 govt BDS:
  PJN MMC Raipur, CIMS Bilaspur, GMC Ambikapur/Kanker/Korba/Mahasamund,
  CCM GMC Durg, ABV MGMC Rajnandgaon, LBKS Jagdalpur, LSL Agrawal Raigarh,
  Govt Dental College Raipur

Outputs (to ../extracted_data/):
  - CG_R1_allotments_2025.csv, CG_R2_allotments_2025.csv — raw rounds
  - CG_all_allotments_2025.csv                          — combined
  - CG_closing_ranks_state_govt_2025.csv                — long format
  - CG_closing_ranks_state_govt_2025_pivot_M.csv        — wide (boys)
  - CG_closing_ranks_state_govt_2025_pivot_F.csv        — wide (girls)

Caveat: CG closing ranks at top govt MBBS may appear higher than
        published "round 1 closing" because we use cumulative through R2
        which includes lower-ranked candidates who upgraded into top
        colleges in R2.
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "CG"
OUT = ROOT / "extracted_data"
STATE_CODE = "CG"

GOVT_CG = {
    "Bharatratna Late shri Atal Bihari Vajpayee MGMC Rajnandgaon",
    "Chandulal Chandrakar Memorial Government Medical College, Durg",
    "Chhattisgarh Institute of Medical Sciences, Bilaspur",
    "GOVERNMENT MEDICAL COLLEGE, AMBIKAPUR",
    "GOVERNMENT MEDICAL COLLEGE, KANKER",
    "GOVERNMENT MEDICAL COLLEGE, KORBA",
    "Government Medical College Mahasamund",
    "LATE BALIRAM KASHYAP SMRITI SH. MEDICAL COLLEGE, JAGDALPUR",
    "LATE SHRI LAKHIRAM AGRAWAL MEMORIAL MEDICAL COLLEGE, RAIGARH",
    "PT.JAWAHAR LAL NEHRU MEMORIAL MEDICAL COLLEGE, RAIPUR",
    "Government Dental College,Raipur",
}
VERTICAL_ORDER = ["UR", "OBC", "EW", "SC", "ST", "SP"]


def parse_r1(path: Path) -> list[dict]:
    """R1 schema (14 cols)."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 14:
                        continue
                    sn = str(r[0] or "").strip()
                    if not sn.isdigit():
                        continue
                    rec = {
                        "sn": int(sn), "roll_no": str(r[1] or "").strip(),
                        "institute": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                        "allotted_course": str(r[3] or "").strip(),
                        "allotted_quota": str(r[5] or "").strip(),
                        "allotted_cat": re.sub(r"\s+", " ", str(r[6] or "")).strip(),
                        "neet_rank": str(r[11] or "").strip().replace(",", ""),
                        "file": "R1",
                    }
                    try:
                        rec["neet_rank"] = int(rec["neet_rank"])
                    except ValueError:
                        continue
                    rows.append(rec)
    return rows


def parse_r2(path: Path) -> list[dict]:
    """R2 schema (13 cols, no CandCat)."""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 13:
                        continue
                    sn = str(r[0] or "").strip()
                    if not sn.isdigit():
                        continue
                    rec = {
                        "sn": int(sn), "roll_no": str(r[1] or "").strip(),
                        "institute": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                        "allotted_course": str(r[3] or "").strip(),
                        "allotted_quota": str(r[5] or "").strip(),
                        "allotted_cat": re.sub(r"\s+", " ", str(r[6] or "")).strip(),
                        "neet_rank": str(r[10] or "").strip().replace(",", ""),
                        "file": "R2",
                    }
                    try:
                        rec["neet_rank"] = int(rec["neet_rank"])
                    except ValueError:
                        continue
                    rows.append(rec)
    return rows


def decompose_cat(c: str):
    """Allotted cat format: VERT-SUB. e.g. UR-NC, UR-F, OBC-NC, SC-Female, ST-EX."""
    c = str(c).strip()
    parts = c.split("-", 1)
    vert = parts[0].strip()
    sub = parts[1].strip() if len(parts) > 1 else ""
    return vert, sub


def gender_from_sub(s: str) -> str:
    s = str(s).strip()
    if s in ("NC", ""):
        return "M"
    if "F" == s or "Female" in s or s.startswith("F"):
        return "F"
    return s


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R1 + R2...")
    r1 = parse_r1(SOURCE / "CG_R1_2025.pdf")
    r2 = parse_r2(SOURCE / "CG_R2_2025.pdf")
    print(f"  R1: {len(r1)} rows, R2: {len(r2)} rows")
    df = pd.DataFrame(r1 + r2)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)

    print("\nStage 2 — filtering to govt + GQ quota...")
    gov = df[(df["institute"].isin(GOVT_CG)) & (df["allotted_quota"] == "GQ")].copy()
    gov = gov.reset_index(drop=True)
    print(f"  Govt rows: {len(gov)}, institutes: {gov['institute'].nunique()}")

    print("\nStage 3 — decomposing categories + closing ranks...")
    deco = gov["allotted_cat"].apply(lambda c: pd.Series(decompose_cat(c)))
    deco.columns = ["vert", "sub"]
    gov = pd.concat([gov, deco], axis=1)
    gov["seat_gender"] = gov["sub"].apply(gender_from_sub)

    cr = (
        gov[gov["seat_gender"].isin(["M", "F"])]
        .groupby(["institute", "allotted_course", "vert", "seat_gender"])["neet_rank"]
        .agg(closing_AIR="max", opening_AIR="min", allotted_count="count")
        .reset_index()
    )
    cr["program"] = cr["allotted_course"]
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    print(f"  CR: {len(cr)} rows")

    print("\nStage 4 — wide pivots (M / F)...")
    for gender in ("M", "F"):
        sub = cr[cr["seat_gender"] == gender]
        piv = sub.pivot_table(
            index=["institute", "program"], columns="vert",
            values="closing_AIR", aggfunc="first",
        ).reset_index()
        piv = piv[["institute", "program"] + [c for c in VERTICAL_ORDER if c in piv.columns]]
        piv.to_csv(
            OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_{gender}.csv",
            index=False,
        )
        print(f"  pivot_{gender}: {len(piv)} rows")

    print(f"\n=== Top 5 CG govt MBBS by UR-Boys closing AIR ===")
    piv_m = pd.read_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_M.csv"
    )
    print(piv_m[piv_m["program"] == "MBBS"]
          .sort_values("UR", na_position="last").head(5).to_string(index=False))


if __name__ == "__main__":
    main()
