"""
Bihar NEET UG 2025 — state govt closing ranks pipeline.

Authority: Bihar Combined Entrance Competitive Examination Board (BCECEB).
           https://bceceboard.bihar.gov.in
Source PDF: BR_R3_revised_2025.pdf
URL: https://bceceboard.bihar.gov.in/pdf_Result/REV_UGMAC25_TALT.pdf
     ("Revised Third Round Allotment", 38 pages, dated 09-Nov-2025)

Last round used: R3 Revised (last main round; Stray Vacancy Round excluded).

Schema (from BCECEB R3 PDF):
  UGMAC ID | NEET ROLL | NEET APL | NEET AIR | NAME | GENDER | CATEGORY (cand)
  | NEET CAT | UR RANK | CAT RANK | RCG RANK | DQ RANK | INSTITUTE | COURSE
  | ALLOTTED CAT | SEAT TYPE | REMARK | ALLOT STATUS

Reservation taxonomy (Bihar):
  Vertical:
    UR  = Unreserved/Open
    BC  = Backward Class (Bihar BC list — separate from central OBC)
    EBC = Extremely Backward Class (Bihar-specific sub-category)
    SC, ST, EWS
  Horizontal: Female (33% — appears in SEAT TYPE column as "FEMALE SEAT")
              + small special quotas (RCG, DQ, MM, NRI, SM, WQ — excluded
              from headline pivot)

Govt-college filter: Hard-coded list of 14 known govt MBBS + 1 govt BDS
  by abbreviation (PMC Patna, IGIMS, NMC Patna, NMC Sasaram, DMC
  Laheriasarai, JLNMC Bhagalpur, SKMC Muzaffarpur, ANMMC Gaya, BMIMS
  Pawapuri, GMC Purnea, GMC Bettiah, ESIC Bihta, JKTMC Madhepura, KMC
  Katihar, GDC Rahui Nalanda).

For Avanti JNV BR student: JNV is Central govt school. Bihar has no
Govt-School horizontal quota. Compete in regular state quota under Bihar
caste sub-category (UR/BC/EBC/SC/ST/EWS).

Outputs (to ../extracted_data/):
  - BR_all_allotments_2025.csv             — raw 1,621 rows
  - BR_closing_ranks_state_govt_2025.csv   — long format
  - BR_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "BR"
OUT = ROOT / "extracted_data"
STATE_CODE = "BR"
PDF_FILE = SOURCE / "BR_R3_revised_2025.pdf"

GOVT_BR_PATTERNS = [
    "PMC", "PATNA MEDICAL", "P.M.C",
    "NMC PATNA", "N.M.C. PATNA", "NALANDA MEDICAL",
    "IGIMS", "I.G.I.M.S",
    "DMC LAHERIA", "D.M.C.LAHERIASARAI", "DARBHANGA MEDICAL",
    "JLNMC", "J.L.N.M.C", "JAWAHARLAL NEHRU",
    "SKMC", "S.K.M.C", "SRI KRISHNA",
    "ANMMC", "A.N.M.M.C", "ANUGRAH NARAYAN",
    "BMIMS", "B.M.I.M.S", "PAWAPURI",
    "GMC PURNEA", "G.M.C. PURNEA",
    "GMC BETTIAH", "G.M.C., BETTIAH",
    "ESIC",
    "JKTMC", "J.K.T.M.C", "MADHEPURA",
    "KMC KATIHAR", "K.M.C. KATIHAR",
    "NMC SASARAM", "N.M.C &.H, SASARAM",
    "GDC RAHUI", "G.D.C. RAHUI",
]
MAIN_VERTS = {"UR", "EBC", "BC", "EWS", "SC", "ST"}
VERTICAL_ORDER = ["UR", "EBC", "BC", "EWS", "SC", "ST"]


def parse_br_pdf(path: Path) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 14:
                        continue
                    ugid = str(r[0] or "").strip()
                    if not re.match(r"^25\d{11,}$", ugid):
                        continue
                    rec = {
                        "ugmac_id": ugid,
                        "neet_roll": str(r[1] or "").strip(),
                        "neet_apl": str(r[2] or "").strip(),
                        "neet_air": str(r[3] or "").strip().replace(",", ""),
                        "name": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "gender": str(r[5] or "").strip(),
                        "cand_category": str(r[6] or "").strip(),
                        "neet_cat": str(r[7] or "").strip(),
                        "institute": re.sub(r"\s+", " ", str(r[12] or "")).strip(),
                        "course": str(r[13] or "").strip(),
                        "allotted_cat": str(r[14] or "").strip() if len(r) > 14 else "",
                        "seat_type": str(r[15] or "").strip() if len(r) > 15 else "",
                        "remark": (
                            re.sub(r"\s+", " ", str(r[16] or "")).strip()
                            if len(r) > 16 else ""
                        ),
                        "allot_status": str(r[17] or "").strip() if len(r) > 17 else "",
                    }
                    try:
                        rec["neet_air"] = int(rec["neet_air"])
                    except ValueError:
                        continue
                    rows.append(rec)
    return pd.DataFrame(rows)


def is_govt(name: str) -> bool:
    n = str(name).upper()
    return any(p.upper() in n for p in GOVT_BR_PATTERNS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R3 Revised PDF...")
    df = parse_br_pdf(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  {len(df)} rows, {df['institute'].nunique()} institutes")

    print("\nStage 2 — filtering to govt + main verticals + MBBS/BDS...")
    df["is_govt"] = df["institute"].apply(is_govt)
    gov = df[
        df["is_govt"]
        & df["course"].isin(["M.B.B.S.", "B.D.S."])
        & df["allotted_cat"].isin(MAIN_VERTS)
    ].copy()
    gov["program"] = gov["course"].map({"M.B.B.S.": "MBBS", "B.D.S.": "BDS"})
    print(f"  Govt: {len(gov)} rows, {gov['institute'].nunique()} institutes")

    print("\nStage 3 — closing ranks per (institute, program, allotted_cat)...")
    cr = (
        gov.groupby(["institute", "program", "allotted_cat"])
        .agg(
            closing_AIR=("neet_air", "max"),
            opening_AIR=("neet_air", "min"),
            allotted_count=("neet_air", "count"),
        )
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 4 — wide pivot...")
    piv = cr.pivot_table(
        index=["institute", "program"], columns="allotted_cat",
        values="closing_AIR", aggfunc="first",
    ).reset_index()
    present = [c for c in VERTICAL_ORDER if c in piv.columns]
    piv = piv[["institute", "program"] + present]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print(f"\n=== Top 5 Bihar govt MBBS by UR closing AIR ===")
    print(piv[piv["program"] == "MBBS"]
          .sort_values("UR", na_position="last").head(5)
          .to_string(index=False))


if __name__ == "__main__":
    main()
