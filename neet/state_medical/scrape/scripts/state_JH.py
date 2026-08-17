"""
Jharkhand NEET UG 2025 — state govt closing ranks pipeline.

Authority: Jharkhand Combined Entrance Competitive Examination Board (JCECEB).
           https://jceceb.jharkhand.gov.in
Counselling portal: https://neetug.jceceb.org.in

Source PDFs hosted at jceceb.jharkhand.gov.in/download/<id>.pdf:
  - JH_R1_2025.pdf  ID 1780 (18-Aug-2025)  — Round 1 allotment
  - JH_R3_2025.pdf  ID 1911 (03-Nov-2025)  — Round 3 allotment

(R3 supersedes R2 for the candidates who upgraded; R1 has the bulk that
stuck. We union R1 + R3 and take MAX(rank) per (college, category).)

Last round used: R1 + R3 cumulative. Stray Vacancy + Special Stray +
                 Additional Round excluded per project pattern.

Schema (R1 & R3 share format): Sl.No | App.No | NEET App.No | Name
       | Category | DOB | Gender | Is PH | Disability Type | Is EWS
       | Is PTG | PTG Type | Applied Category Seats Status | CML Rank
       | Category Rank | EWS Rank | PTG Rank | PH Rank | Allotted Institute
       | Allotted Course | Allotted Category/Quota | + previous-round cols

Closing-rank metric: CML Rank (Combined Merit List — Jharkhand state-
                     specific NEET-based merit rank, lower = harder).

Reservation taxonomy (Jharkhand):
  Vertical: UR / BC-I / BC-II / SC / ST / EWS
  Horizontal: PH (PwD), Female, PTG (Primitive Tribal Group)
  Sub-pools: Numbered quotas 1-10 (college-specific affiliated-school
             reservations) — excluded from headline pivot

Govt-college filter: 6 govt MBBS + 1 govt BDS hard-coded:
  RIMS Ranchi, MGM Jamshedpur, Shaheed Nirmal Mahto Dhanbad, Phulo Jhano
  Dumka, Sheikh Bhikhari Hazaribagh, Medinirai (Palamu) MC,
  RIMS Dental Institute Ranchi.

Outputs (to ../extracted_data/):
  - JH_all_allotments_2025.csv             — raw rows (1,029)
  - JH_closing_ranks_state_govt_2025.csv   — long format
  - JH_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "JH"
OUT = ROOT / "extracted_data"
STATE_CODE = "JH"

ROUND_FILES = [
    ("JH_R1_2025.pdf", "R1"),
    ("JH_R3_2025.pdf", "R3"),
]

GOVT_JH = {
    "Rajendra Institute of Medical Sciences, Ranchi",
    "M.G.M. Medical College, Dimna Road, Mango, Jamshedpur",
    "Mahatma Gandhi Memorial Medical College, Dimna Road, Mango, Jamshedpur-831020",
    "Shaheed Nirmal Mahto Medical College, B.C.C.L. Township, Koyla Nagar, Dhanbad-826005",
    "Medinirai Medical College (Previously Known as Palamu Medical College), Palamu At-Pokhraha Khurd, P.O- Rajwadih, P.S- Medininagar, Dist.- Palamu, State- Jharkhand, Pin Code- 822118",
    "PHULO JHANO MEDICAL COLLEGE DUMKA (DUMKA MEDICAL COLLEGE DUMKA) Shri Amra PO Diggi Dumka Jharkhand Pin 814110",
    "SHEIKH BHIKHARI MEDICAL COLLEGE & HOSPITAL , HAZARIBAGH",
    "Dental Institute, Rajendra Institute of Medical Sciences, Ranchi",
}
MAIN_QUOTAS = {"UR", "ST", "SC", "BC-I", "BC-II", "EWS"}
ORDER = ["UR", "BC-I", "BC-II", "EWS", "SC", "ST"]


def parse_jh_pdf(path: Path, label: str) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 18:
                        continue
                    sl = str(r[0] or "").strip()
                    if not sl.isdigit():
                        continue
                    cml = str(r[13] or "").strip().replace(",", "")
                    if not cml.isdigit():
                        continue
                    score = str(r[12] or "").strip()
                    rows.append({
                        "file": label,
                        "sl": int(sl),
                        "app_no": str(r[1] or "").strip(),
                        "neet_app": str(r[2] or "").strip(),
                        "name": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "category": str(r[4] or "").strip(),
                        "gender": str(r[6] or "").strip(),
                        "neet_score": int(score) if score.isdigit() else None,  # NEW: needed for AIR conversion
                        "cml_rank": int(cml),
                        "cat_rank": str(r[14] or "").strip(),
                        "allotted_institute": re.sub(r"\s+", " ", str(r[18] or "")).strip(),
                        "allotted_course": str(r[19] or "").strip(),
                        "allotted_quota": re.sub(r"\s+", " ", str(r[20] or "")).strip(),
                    })
    return rows


def canonicalize_college(name: str) -> str:
    n = str(name).strip()
    if "Mahatma Gandhi Memorial" in n or n.startswith("M.G.M"):
        return "MGM Medical College, Jamshedpur"
    if "PHULO JHANO" in n:
        return "Phulo Jhano Medical College, Dumka"
    if "SHEIKH BHIKHARI" in n:
        return "Sheikh Bhikhari Medical College, Hazaribagh"
    if "Shaheed Nirmal Mahto" in n:
        return "Shaheed Nirmal Mahto Medical College, Dhanbad"
    if "Medinirai" in n:
        return "Medinirai Medical College, Palamu"
    if "Rajendra Institute of Medical Sciences" in n and "Dental" not in n:
        return "RIMS, Ranchi"
    if "Dental Institute, Rajendra" in n:
        return "RIMS Dental Institute, Ranchi"
    return n


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R1 + R3 PDFs...")
    all_rows = []
    for fname, label in ROUND_FILES:
        rows = parse_jh_pdf(SOURCE / fname, label)
        print(f"  {fname}: {len(rows)}")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df["cml_rank"] = pd.to_numeric(df["cml_rank"], errors="coerce")
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df)}")

    print("\nStage 2 — filtering to govt + main verticals + MBBS/BDS...")
    gov = df[
        df["allotted_institute"].isin(GOVT_JH)
        & df["allotted_course"].isin(["M.B.B.S.", "B.D.S."])
        & df["allotted_quota"].isin(MAIN_QUOTAS)
    ].copy()
    gov["college_canon"] = gov["allotted_institute"].apply(canonicalize_college)
    gov["program"] = gov["allotted_course"].map({"M.B.B.S.": "MBBS", "B.D.S.": "BDS"})
    print(f"  Govt rows: {len(gov)}, colleges: {gov['college_canon'].nunique()}")

    print("\nStage 3 — closing ranks per (college, program, quota)...")
    cr = (
        gov.groupby(["college_canon", "program", "allotted_quota"])["cml_rank"]
        .agg(closing_state_rank="max", opening_state_rank="min", allotted_count="count")
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 4 — wide pivot...")
    piv = cr.pivot_table(
        index=["college_canon", "program"], columns="allotted_quota",
        values="closing_state_rank", aggfunc="first",
    ).reset_index()
    piv = piv[["college_canon", "program"] + [c for c in ORDER if c in piv.columns]]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print(f"\n=== Jharkhand govt by UR closing state rank ===")
    print(piv.sort_values("UR", na_position="last").to_string(index=False))


if __name__ == "__main__":
    main()
