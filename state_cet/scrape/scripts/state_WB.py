"""
West Bengal WBJEE — engineering closing-ranks pipeline.

Authority:  West Bengal Joint Entrance Examinations Board (WBJEEB)
Portal:     https://wbjeeb.nic.in/wbjee/
Source:     OR-CR (Opening-Closing Rank) consolidated HTML report at
            admissions.nic.in/wbjeeb/Applicant/report/orcrreport.aspx?enc=...
            Returns a single table with all 3,020 (round × institute ×
            branch × category) rows for WBJEE 2025 counselling.

The WBJEE OR-CR endpoint is publicly accessible via an `enc=` token
URL — no captcha, no login needed. The 2025 token is:
    Nm7QwHILXclJQSv2YVS+7ud0s9OnRxxLItScoKR31F4qbKNJ7YB3loiJ7DTFho11

Cutoff data shape (3,020 rows × 10 cols):
  Sr.No | Round | Institute | Program | Stream | Seat Type | Quota |
  Category | Opening Rank | Closing Rank

Reservation taxonomy (West Bengal):
  Vertical: Open / EWS / OBC-A (predominantly Muslim BC) / OBC-B (Hindu BC) /
            SC / ST
  Horizontal: PwD (Open PwD, OBC-A PwD, OBC-B PwD, SC PwD)
  Special: TFW (Tuition Fee Waiver Scheme — economic, ≤₹8 LPA family)
  Quota: Home State (WB domicile) / All India
  Seat Type: WBJEE Seats / JEE(Main) Seats — some institutes accept
             both, with separate cutoffs per seat-type

For canonical 5-cat mapping (NCST schema):
  Open                  → GEN
  EWS                   → EWS
  OBC-A, OBC-B          → OBC-NCL (WB's two OBC sub-pools)
  SC                    → SC
  ST                    → ST
  TFW, PwD              → flagged via sub_pool, not part of canonical 5

Methodology:
  - WBJEE publishes Round 1 + Round 2 cumulative in the OR-CR report.
    Round 3 / Mop-up rounds NOT in this file (excluded per "no stray"
    rule in the project methodology).
  - Closing rank = MAX(Closing Rank) per (Institute, Program, Category,
    Quota, Seat Type) across Round 1 + Round 2.
  - Govt-scope filter: match institute name patterns for state govt /
    state-aided / state university institutions in WB.

Govt + State-Univ institutions in WB engineering (whitelist):
  - Jadavpur University (Faculty of Engineering & Technology)
  - IIEST Shibpur (Indian Institute of Engineering Science & Technology
    — Centrally Funded Technical Institution but participates in WB
    state quota too)
  - University of Calcutta (Tech Campus)
  - Maulana Abul Kalam Azad University of Technology (MAKAUT, formerly WBUT)
  - Government College of Engineering and Leather Technology, Kolkata
  - Government College of Engineering and Textile Technology, Berhampore
  - Government College of Engineering and Ceramic Technology, Kolkata
  - Kalyani Government Engineering College
  - Aliah University, New Town
  - Alipurduar Government Engineering and Management College
  - Cooch Behar Government Engineering College
  - Jalpaiguri Government Engineering College
  - Murshidabad College of Engineering & Technology (govt-aided)

Output (to extracted_data/):
  - WB_engg_all_orcr_2025.csv             — raw (3,020 rows)
  - WB_engg_closing_ranks_govt_2025.csv   — govt scope (long)
  - WB_engg_consolidated_5cat_govt_2025.csv  — schema-canonical
"""
from __future__ import annotations
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "WB" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "WB"
DATA_YEAR = 2025
CET_NAME = "WBJEE"
SOURCE_URL = ("https://admissions.nic.in/wbjeeb/Applicant/report/orcrreport.aspx"
              "?enc=Nm7QwHILXclJQSv2YVS+7ud0s9OnRxxLItScoKR31F4qbKNJ7YB3loiJ7DTFho11")


# State-public universities in WB engineering (as State-Univ-Dept)
WB_STATE_PUB_UNIVS = [
    "Jadavpur University",
    "University of Calcutta",
    "University Of Calcutta",
    "Calcutta University",
    "Maulana Abul Kalam Azad University of Technology",
    "MAKAUT",
    "Aliah University",
    "Indian Institute of Engineering Science",  # IIEST Shibpur
    "IIEST",
    "Kaji Nazrul University",                  # state public, Asansol
    "University of Kalyani",                    # state public, Kalyani
    "UNIVERSITY OF KALYANI",
    "University Institute of Technology, Burdwan University",
    "UNIVERSITY INSTITUTE OF TECHNOLOGY, BURDWAN UNIVERSITY",
    "West Bengal University of Animal",         # state govt univ (vet/fishery)
]

# Private deemed-private universities to exclude (despite "University" in name)
WB_PRIVATE_DEEMED = [
    "Adamas University", "BRAINWARE UNIVERSITY", "JIS University", "Jis University",
    "Seacom Skills University", "Sister Nivedita University", "Swami Vivekananda University",
    "THE NEOTIA UNIVERSITY", "The Neotia University", "Techno India University",
    "Amity University", "Sharda University", "Lovely Professional", "Vidyamandir",
]


def classify_wb_college(name: str) -> str:
    if not name:
        return "Unknown"
    upper = name.upper()
    # Private deemed-private check first (overrides "University" generic match)
    if any(p.upper() in upper for p in WB_PRIVATE_DEEMED):
        return "Private/Deemed"
    # State-public university match
    for p in WB_STATE_PUB_UNIVS:
        if p.upper() in upper:
            return "State-Univ-Dept"
    # Govt engineering colleges — handle "Government" + WBJEE's typo "Goverment"
    if re.search(r"\b(GOVERNMENT|Government|GOVT|Govt\.?|Goverment|GOVERMENT)\b.*\b(College of (Engineering|Engg)|Engineering College|Engineering and Management)\b",
                 name, re.IGNORECASE):
        return "Govt"
    if re.search(r"^(Cooch Behar|Jalpaiguri|Alipurduar|Kalyani|Murshidabad|Ramkrishna)\s+(Government|Goverment)",
                 name, re.IGNORECASE):
        return "Govt"
    # Catch "Goverment" (WBJEE typo) at start
    if re.search(r"^(GOVERNMENT|Government|Goverment|GOVERMENT)\s", name):
        return "Govt"
    # Murshidabad College of Engineering & Technology — govt-aided
    if "Murshidabad College of Engineering" in name:
        return "Govt-Aided"
    # Ghani Khan Choudhury Institute — govt-aided?
    return "Private/SF"

GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


# ───────────────────────────────────────────────────────────────────────────
# Canonical 5-cat mapping
# ───────────────────────────────────────────────────────────────────────────
def normalise_category(c: str) -> tuple[str, str]:
    """Return (canonical_category, sub_pool)."""
    c = c.strip()
    if c == "Open":                return ("GEN", "")
    if c == "EWS":                 return ("EWS", "")
    if c.startswith("OBC - A"):    return ("OBC-NCL", "OBC-A" + (" PwD" if "PwD" in c else ""))
    if c.startswith("OBC - B"):    return ("OBC-NCL", "OBC-B" + (" PwD" if "PwD" in c else ""))
    if c.startswith("SC"):         return ("SC", "PwD" if "PwD" in c else "")
    if c.startswith("ST"):         return ("ST", "PwD" if "PwD" in c else "")
    if c == "Open (PwD)":          return ("GEN", "PwD")
    if c == "Tuition Fee Waiver":  return ("OTHER", "TFW")
    return ("OTHER", c)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — load WBJEE OR-CR HTML")
    html_path = SOURCE / "WBJEE_2025_ORCR.html"
    df = pd.read_html(html_path, attrs={"id": "ORCRGridView"})[0]
    print(f"  Total rows: {len(df):,}")
    print(f"  Distinct institutes: {df['Institute'].nunique()}")
    print(f"  Round counts: {df['Round'].value_counts().to_dict()}")

    df.to_csv(OUT / f"{STATE_CODE}_engg_all_orcr_{DATA_YEAR}.csv", index=False)

    print("\nStage 2 — aggregate MAX-rank closing per (institute × program × category × quota × seat_type)")
    agg = (df.groupby(
        ["Institute", "Program", "Stream", "Seat Type", "Quota", "Category"],
        dropna=False,
    ).agg(
        opening_rank=("Opening Rank", "min"),
        closing_rank=("Closing Rank", "max"),
        last_round_with_max=("Round",
                              lambda s: s.value_counts().index[0]),
    ).reset_index())

    print(f"  closing-rank rows (all institutes): {len(agg):,}")

    print("\nStage 3 — classify govt scope")
    agg["college_type"] = agg["Institute"].apply(classify_wb_college)
    print("  by college_type:")
    for t, n in (agg.groupby(["Institute", "college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = agg[agg["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['Institute'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    cat_norm = govt["Category"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "sub_pool"]
    govt = pd.concat([govt, cat_norm], axis=1)

    govt["state"] = "WEST BENGAL"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "R1+R2 (cumulative, Mop-up excluded)"
    govt["gender"] = "All"  # WBJEE doesn't split by gender in OR-CR data
    govt["rank_basis"] = "WBJEE GMR (General Merit Rank)"
    govt["source_url"] = SOURCE_URL
    govt["college_code"] = govt["Institute"]  # WBJEE doesn't use stable codes

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "Institute", "college_type",
        "Program", "Seat Type", "Quota",
        "Category", "category", "sub_pool", "gender",
        "opening_rank", "closing_rank", "last_round_with_max",
        "rank_basis", "source_url",
    ]].rename(columns={
        "Institute": "college_name",
        "Program": "branch_name",
        "Seat Type": "seat_type",
        "Quota": "quota",
        "Category": "category_raw",
    }).sort_values(["college_name", "branch_name", "category_raw"])

    govt_out.to_csv(OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False)

    # Schema-canonical 5-cat — Home State quota only, no sub-pools
    print("\nStage 4 — schema-canonical 5-cat consolidated")
    canon = govt_out[
        (govt_out["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"]))
        & (govt_out["sub_pool"].isin(["", "OBC-A", "OBC-B"]))
        & (govt_out["quota"] == "Home State")
    ].copy()
    canon["branch_code"] = canon["branch_name"]  # WBJEE uses branch name as identifier
    canon = canon.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(
        opening_rank=("opening_rank", "min"),
        closing_rank=("closing_rank", "max"),
        last_round_with_max=("last_round_with_max",
                              lambda s: s.value_counts().index[0]),
    ).reset_index()
    canon["rank_basis"] = "WBJEE GMR"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== WB sanity (govt scope, Open/Home State, hardest 12) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "Open")
        & (govt_out["quota"] == "Home State")
    ].sort_values("closing_rank").head(12)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
