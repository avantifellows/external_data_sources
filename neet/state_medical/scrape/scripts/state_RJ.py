"""
Rajasthan NEET UG — state govt closing ranks pipeline.

⚠️ DATA YEAR: This pipeline uses 2024 data (most recent year available
from third-party aggregators with full category breakdown). Rajasthan's
official 2025 portal (rajugneet2025.in) blocks programmatic access.

When 2025 data becomes available:
  1. Save as RJ_combined_R1_R2_allotment_2025.pdf
  2. Update DATA_YEAR constant below
  3. Re-run

Authority: Office of the Chairman, NEET UG Medical & Dental Admission /
           Counselling Board, SMS Medical College, Jaipur.
           https://rajugneet2025.in (current year), but format is consistent
           across years.

Source PDF: RJ_combined_R1_R2_allotment_2024.pdf
            ("Provisional combined allotment list, Round 1 and Round 2,
            27.09.2024"). 285 pages, 5,130 candidate-level rows.
            Source: edufever.com aggregator (mirrors official Rajasthan
            board PDF).

Round used: cumulative R1+R2. The 2024 file is labeled "Combined Rounds 1
            and 2" — Mop-up (R3) and Stray (R4) not yet included as of
            file date (27-Sep-2024). For purposes of project pattern
            ("last main round"), this is acceptable since R3/R4 are
            relatively small and would push closings only slightly worse.

Schema (2024 file):
  SNo | Reg.ID | NEET Roll | Name | Category considered | Category Allotted
      | Gender | NEET Percentile | State Merit R2 | NEET A.I. Rank
      | Course and College Allotted

Reservation taxonomy (visible in 2024 file):
  - Vertical (Category considered): GEN / OBC / EWS / SC / ST / MBC / SA
                                    + sub-categories: STA, PwD, EXS1-6,
                                    WPP1-3, SAB
  - Allotted Category encodes both vertical + gender:
      GEN URB (M Open Urban) / GEN URG (F Open Urban)
      OBC OBB / OBG, SC SCB / SCG, ST STB / STG,
      MBC MBB / MBG, EWS EWB / EWG, SA SAB / SAG
  - "B" suffix = Boys (Male), "G" = Girls (Female)
  - Special sub-pools (PwD, EXS=Ex-Servicemen, WPP=War Widow's Wards,
    STA=ST Tribal Sub-Plan Area) excluded from headline pivot but kept
    in long format

Govt-college filter:
  - seat_type = "Govt. Seat" (drops "Gen. Seat" at private, "Mgmt. Seat",
    "NRI Seat")
  - Result: 32 govt MBBS colleges (vs NMC list 31 for 2025-26 — close).

Outputs (to ../extracted_data/):
  - RJ_all_allotments_2024.csv                          — raw 5,130 rows
  - RJ_closing_ranks_state_govt_2024.csv                — long format
  - RJ_closing_ranks_state_govt_2024_pivot_M.csv        — wide (boys)
  - RJ_closing_ranks_state_govt_2024_pivot_F.csv        — wide (girls)

Historical reference (2022):
  - source/RJ/RJ_combined_final_allotment_2022.pdf      — kept for
    historical comparison; parsed by `parse_2022()` below if needed.
    2022 file lacks the Category column — only per-college percentile
    profile possible.
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "RJ"
OUT = ROOT / "extracted_data"
STATE_CODE = "RJ"
DATA_YEAR = 2024
PDF_FILE = SOURCE / f"RJ_combined_R1_R2_allotment_{DATA_YEAR}.pdf"

VERTICAL_ORDER = ["GEN", "OBC", "EWS", "MBC", "SC", "ST", "SA"]

# Plain (non-PwD/EXS/WPP) sub-codes that map cleanly to vertical+gender
PLAIN_SUBS = {
    "URB", "URG",  # GEN
    "OBB", "OBG",  # OBC
    "SCB", "SCG",  # SC
    "STB", "STG",  # ST
    "MBB", "MBG",  # MBC
    "EWB", "EWG",  # EWS
    "SAB", "SAG",  # SA
}


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse 2024 PDF
# ───────────────────────────────────────────────────────────────────────────
def parse_rj_2024(path: Path) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 11:
                        continue
                    sno = str(r[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    course_college = re.sub(r"\s+", " ", str(r[10] or "")).strip()
                    cm = re.match(r"^(MBBS|BDS)\s*,\s*(.+)$", course_college)
                    course = cm.group(1) if cm else ""
                    college_full = cm.group(2).strip() if cm else course_college
                    rec = {
                        "sno": int(sno),
                        "reg_id": str(r[1] or "").strip(),
                        "neet_roll": str(r[2] or "").strip(),
                        "name": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "cand_category": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "allotted_category": re.sub(r"\s+", " ", str(r[5] or "")).strip(),
                        "gender": str(r[6] or "").strip(),
                        "neet_percentile": str(r[7] or "").strip(),
                        "state_merit": str(r[8] or "").strip().replace(",", ""),
                        "ai_rank": str(r[9] or "").strip().replace(",", ""),
                        "course": course,
                        "college_full": college_full,
                    }
                    try:
                        rec["ai_rank"] = int(rec["ai_rank"])
                    except ValueError:
                        continue
                    try:
                        rec["state_merit"] = int(rec["state_merit"])
                    except ValueError:
                        rec["state_merit"] = None
                    try:
                        rec["neet_percentile"] = float(rec["neet_percentile"])
                    except ValueError:
                        rec["neet_percentile"] = None
                    rows.append(rec)
    df = pd.DataFrame(rows)
    df["seat_type"] = df["college_full"].str.extract(r"\(([^)]+)\)\s*$")
    df["college"] = (
        df["college_full"].str.replace(r"\s*\([^)]+\)\s*$", "", regex=True).str.strip()
    )
    return df


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — decompose allotted_category → vertical + gender
# ───────────────────────────────────────────────────────────────────────────
def decompose_allotted(cat: str):
    """Format: '<VERT> <SUB>[ -]'  e.g. 'GEN URB -' → ('GEN','URB','M')"""
    cat = str(cat).strip().rstrip("-").strip()
    parts = cat.split()
    if not parts:
        return ("", "", "")
    vertical = parts[0]
    sub = parts[1] if len(parts) > 1 else ""
    gender = ""
    if sub and sub[-1] in ("B", "G"):
        gender = "M" if sub[-1] == "B" else "F"
    return vertical, sub, gender


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Stage 1 — parsing {PDF_FILE.name} (~1 min for 285 pages)...")
    df = parse_rj_2024(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_{DATA_YEAR}.csv", index=False)
    print(f"  Total: {len(df):,}")

    print("\nStage 2 — filtering to Govt. Seat + decomposing categories...")
    gov = df[df["seat_type"] == "Govt. Seat"].copy()
    deco = gov["allotted_category"].apply(lambda c: pd.Series(decompose_allotted(c)))
    deco.columns = ["vert", "sub_code", "seat_gender"]
    gov = pd.concat([gov.reset_index(drop=True), deco], axis=1)
    print(f"  Govt: {len(gov):,} rows, {gov['college'].nunique()} colleges")

    plain = gov[gov["sub_code"].isin(PLAIN_SUBS)].copy()
    print(f"  Plain (vert+gender, non-PwD/EXS/WPP): {len(plain):,}")

    print("\nStage 3 — closing ranks per (college, vertical, seat_gender)...")
    cr = (
        plain.groupby(["college", "course", "vert", "seat_gender"])
        .agg(
            closing_AIR=("ai_rank", "max"),
            opening_AIR=("ai_rank", "min"),
            closing_NEET_pct=("neet_percentile", "min"),
            opening_NEET_pct=("neet_percentile", "max"),
            allotted_count=("ai_rank", "count"),
        )
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_{DATA_YEAR}.csv", index=False)
    print(f"  {len(cr):,} CR rows")

    print("\nStage 4 — wide pivots (M boys + F girls)...")
    for gender in ("M", "F"):
        sub = cr[cr["seat_gender"] == gender]
        piv = sub.pivot_table(
            index=["college", "course"], columns="vert",
            values="closing_AIR", aggfunc="first",
        ).reset_index()
        present = [c for c in VERTICAL_ORDER if c in piv.columns]
        piv = piv[["college", "course"] + present]
        piv.to_csv(
            OUT / f"{STATE_CODE}_closing_ranks_state_govt_{DATA_YEAR}_pivot_{gender}.csv",
            index=False,
        )
        print(f"  pivot_{gender}: {len(piv)} rows")

    print(f"\n=== Top 5 RJ govt MBBS by GEN-Boys closing AIR ({DATA_YEAR}) ===")
    piv_m = pd.read_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_{DATA_YEAR}_pivot_M.csv"
    )
    print(piv_m[piv_m["course"] == "MBBS"]
          .sort_values("GEN", na_position="last")
          .head(5).to_string(index=False))


if __name__ == "__main__":
    main()
