"""
Bihar BCECE — engineering closing-ranks pipeline.

Authority:  Bihar Combined Entrance Competitive Examination Board (BCECEB)
Portal:     https://bceceboard.bihar.gov.in/
Source:     "COMBINED FIRST AND SECOND ROUND OPENING AND CLOSING RANK OF
            BCECE[ENGINEERING]-2025" PDF at
            bceceboard.bihar.gov.in/pdf_Web/BC_ENG25_SCOFF.pdf

PDF format (clean tabular, 69 pages):
  8 columns:
    INSTITUTE | BRANCH | SEAT TYPE (Female/General) | CATEGORY |
    UR OPENING RANK | UR CLOSING RANK | CAT OPENING RANK | CAT CLOSING RANK

Bihar's reservation framework is unique:
  - Each row has TWO rank pairs:
    * UR ranks (when UR/E-UR seat) — used for UR/E-UR rows
    * CAT ranks (when reserved seat) — used for SC/ST/EBC/BC/BCL/etc. rows
    Only one pair is filled per row depending on category type.

Reservation taxonomy (Bihar):
  Vertical: UR (Open) / EWS / EBC (Extremely Backward Class) /
            BC (Backward Class) / SC / ST / RCG (Reserved Category Girls)
  Horizontal: Female (33% women's reservation, encoded in SEAT TYPE column)
  Special sub-pools:
    BCL  = BC-Female sub-pool
    DQ   = Divyangjan (PwD)
    SMQ  = Sports/Misc Quota
    E-UR = Bihar-domicile economic UR (in-state)

Methodology:
  - Source PDF is "Combined R1 + R2" — already cumulative through Round 2.
  - BCECEB's Round 3 is mop-up only, allotment-without-cutoff. Excluded.
  - Closing rank per (institute, branch, seat_type, category) directly
    in the PDF — no aggregation needed.

For canonical 5-cat mapping (NCST schema):
  UR, E-UR  → GEN
  EWS       → EWS
  BC, EBC   → OBC-NCL  (Bihar's two OBC tiers)
  BCL       → OBC-NCL  (BC-Female — flagged as Girls gender)
  SC        → SC
  ST        → ST
  RCG       → flagged Girls horizontal (sub_pool)
  DQ, SMQ   → flagged via sub_pool

For Avanti JNV BR student:
  - JNV is Central govt school. Bihar has no horizontal "govt school"
    reservation. Compete in regular state quota under the Bihar BC/EBC/
    SC/ST taxonomy (state-specific community certificate required).

Output (to extracted_data/):
  - BR_engg_all_cutoffs_2025.csv          — long format (every row)
  - BR_engg_closing_ranks_govt_2025.csv   — govt scope
  - BR_engg_consolidated_5cat_govt_2025.csv  — schema-canonical
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "BR" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "BR"
DATA_YEAR = 2025
CET_NAME = "BCECE"
SOURCE_URL = "https://bceceboard.bihar.gov.in/pdf_Web/BC_ENG25_SCOFF.pdf"
PHASE_FILE = "BR_BCECE_2025_R12_Closing.pdf"


def parse_br_pdf(path: Path) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) < 8:
                        continue
                    inst = (r[0] or "").replace("\n", " ").strip()
                    branch = (r[1] or "").replace("\n", " ").strip()
                    seat = (r[2] or "").strip()
                    cat = (r[3] or "").strip()
                    ur_open = (r[4] or "").strip()
                    ur_close = (r[5] or "").strip()
                    cat_open = (r[6] or "").strip()
                    cat_close = (r[7] or "").strip()
                    # Skip header
                    if inst in ("INSTITUTE", "") or "INSTITUTE" in cat:
                        continue
                    if seat in ("SEAT TYPE", ""):
                        continue
                    # Determine which pair to use based on which is filled
                    closing = ur_close if ur_close else cat_close
                    opening = ur_open if ur_open else cat_open
                    try:
                        c_rank = int(closing.replace(",", ""))
                        o_rank = int(opening.replace(",", ""))
                    except ValueError:
                        continue
                    rows.append({
                        "college_name": inst,
                        "branch_name": branch,
                        "seat_type": seat,
                        "category_raw": cat,
                        "opening_rank": o_rank,
                        "closing_rank": c_rank,
                    })
    return rows


# Bihar govt engineering colleges — name-pattern based
BR_GOVT_PATTERNS = [
    r"\bB\.?C\.?E\.?\s",                    # B.C.E. = Bihar College of Engineering
    r"\bBHAGALPUR COLLEGE OF ENGINEERING",
    r"\bMUZAFFARPUR\b.*ENGINEERING",
    r"\bMIT MUZAFFARPUR",
    r"\bMUZAFFARPUR INSTITUTE",
    r"\bN\.?S\.?I\.?T\.?\s",                # NSIT = Netaji Subhas Institute of Tech Patna
    r"\bDARBHANGA COLLEGE OF ENGINEERING",
    r"\bGAYA COLLEGE OF ENGINEERING",
    r"\bMOTIHARI COLLEGE OF ENGINEERING",
    r"\bSITAMARHI INSTITUTE OF TECHNOLOGY",
    r"\bKATIHAR ENGINEERING COLLEGE",
    r"\bSARAN ENGINEERING COLLEGE",
    r"\bSUPAUL COLLEGE OF ENGINEERING",
    r"\bNALANDA COLLEGE OF ENGINEERING",
    r"\bGOVERNMENT ENGINEERING COLLEGE",
    r"\bGOVT\.\s*ENGINEERING",
    r"^L\.?N\.?J\.?P\.?I\.?T\.?\s",         # Loknayak Jayaprakash Inst of Tech, Chhapra
    r"\bGEC\b",
]


def classify_br_college(name: str) -> str:
    if not name:
        return "Unknown"
    for pat in BR_GOVT_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            return "Govt"
    if "PRIVATE" in name.upper() or "PVT" in name.upper():
        return "Private/SF"
    # In Bihar, BCECE counselling is largely for state govt engineering colleges.
    # If the institute name doesn't match private patterns, default to Govt
    # (BCECE is the gateway to ALL Bihar govt engineering colleges, ~15 institutions).
    return "Govt"   # default — refine if needed


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def normalise_category(c: str) -> tuple[str, str, str]:
    """Return (canonical_category, sub_pool, gender_hint)."""
    c = c.strip().upper()
    if c in ("UR", "E-UR"):    return ("GEN", "E-UR" if c == "E-UR" else "", "All")
    if c == "EWS":             return ("EWS", "", "All")
    if c in ("BC", "BCL"):     return ("OBC-NCL", c, "Girls" if c == "BCL" else "All")
    if c == "EBC":             return ("OBC-NCL", "EBC", "All")
    if c == "SC":              return ("SC", "", "All")
    if c == "ST":              return ("ST", "", "All")
    if c == "RCG":             return ("OTHER", "RCG", "Girls")  # Reserved Category Girls
    if c == "DQ":              return ("OTHER", "DQ", "All")     # Divyangjan/PwD
    if c == "SMQ":             return ("OTHER", "SMQ", "All")    # Sports/Misc
    return ("OTHER", c, "All")


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse BCECE Combined R1+R2 closing PDF")
    rows = parse_br_pdf(SOURCE / PHASE_FILE)
    df = pd.DataFrame(rows)
    print(f"  Total rows: {len(df):,}")
    print(f"  Distinct institutes: {df['college_name'].nunique()}")
    print(f"  Categories: {sorted(df['category_raw'].unique())}")
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_cutoffs_{DATA_YEAR}.csv", index=False)

    print("\nStage 2 — classify govt scope")
    df["college_type"] = df["college_name"].apply(classify_br_college)
    print("  by college_type (distinct colleges):")
    for t, n in (df.groupby(["college_name", "college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = df[df["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_name'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    cat_norm = govt["category_raw"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "sub_pool", "gender_hint"]
    govt = pd.concat([govt, cat_norm], axis=1)

    # Combine seat_type + gender_hint to determine effective gender
    govt["gender"] = govt.apply(
        lambda r: "Girls" if r["seat_type"] == "Female" or r["gender_hint"] == "Girls" else "All",
        axis=1,
    )

    govt["state"] = "BIHAR"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "R1+R2 cumulative (mop-up excluded)"
    govt["quota"] = "State (Bihar domicile)"
    govt["college_code"] = govt["college_name"]
    govt["rank_basis"] = "BCECE State Rank"

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_name", "seat_type",
        "quota", "category_raw", "category", "sub_pool", "gender",
        "opening_rank", "closing_rank",
        "rank_basis",
    ]].sort_values(["college_name", "branch_name", "seat_type", "category_raw"])
    govt_out["source_url"] = SOURCE_URL
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    # 5-cat consolidated
    print("\nStage 3 — schema-canonical 5-cat consolidated")
    canon = govt_out[
        govt_out["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"])
    ].copy()
    canon["branch_code"] = canon["branch_name"]
    canon = canon.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(
        opening_rank=("opening_rank", "min"),
        closing_rank=("closing_rank", "max"),
    ).reset_index()
    canon["last_round_with_max"] = "R2"
    canon["rank_basis"] = "BCECE State Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== BR sanity (govt scope, UR/General, hardest 12) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "UR")
        & (govt_out["seat_type"] == "General")
    ].sort_values("closing_rank").head(12)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
