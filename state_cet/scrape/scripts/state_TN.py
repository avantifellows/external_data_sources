"""
Tamil Nadu TNEA — engineering closing-ranks pipeline.

Authority: Anna University / Directorate of Technical Education TN (DOTE TN)
Portal:    https://cutoff.tneaonline.org/  (Cloudflare Turnstile gated)
Source:    Two CSVs scraped from the portal via Chrome MCP after passing
           the Turnstile captcha:
           - TN_TNEA_2025_cutoff_marks.csv     (3,457 rows, marks /200)
           - TN_TNEA_2025_state_merit_ranks.csv (3,457 rows, state merit rank)

TNEA scoring is unique among Indian state CETs:
  - Cutoff mark out of 200 = Math 100 + (Phys + Chem)/2 to 100
  - Based on Class 12 board marks, NOT a separate test (since 2007)
  - Higher cutoff mark = harder seat (opposite direction from rank)
  - Each (college, branch, category) cell shows the lowest cutoff mark
    that got admitted = closing mark; lowest state merit rank = closing rank

Reservation taxonomy:
  Vertical (TN-specific 69% reservation):
    OC  = Open Category (Forward + EWS rolled in)
    BC  = Backward Class
    BCM = Backward Class Muslim
    MBC = Most Backward Class & DNC (Denotified Communities)
    SC  = Scheduled Caste
    SCA = SC-Arunthathiyar (sub-quota of SC, 3% within 18%)
    ST  = Scheduled Tribe
  Horizontal:
    GSQ-7.5% = Government School Quota — class 6-12 in TN govt/aided
               schools only. **JNV is Central govt school → NOT eligible.**
               GSQ has its own per-college allotment list (in
               static.tneaonline.org/docs/GOVT_ACADEMIC_ROUND*.pdf).
    PwBD, Sports, ESM (small horizontals)
  EWS: rolled into OC bucket by TN's reservation framework, not a separate
       column.

Methodology applied:
  - Year: 2025-26 (the latest published cycle)
  - Round: TNEA publishes ONLY the final post-counselling cutoff numbers,
    not per-round breakdowns. So the data IS the closing rank/mark for
    the final round (no MAX-aggregation needed).
  - Govt scope: state govt + state govt-aided colleges. TN's engineering
    portal doesn't carry an explicit type column, so we use a name-pattern
    + whitelist classifier.

Govt-college classification:
  - "University Departments of Anna University" / "Anna University Regional
    Campus" → Govt (state public university)
  - Names containing "Government" / "Govt." → Govt
  - Whitelisted aided autonomous institutions (PSG Tech, etc.) → Govt-Aided
  - Everything else → Private/Self-Financed/Deemed

For canonical 5-cat mapping (NCST schema):
  OC  → GEN  (Open Category — TN does not have a separate EWS column)
  BC  → OBC-NCL  (TN BC ≈ Central OBC-NCL approximately)
  BCM → OBC-NCL  (BC Muslim — separate sub-list, also OBC-equivalent)
  MBC → OBC-NCL  (Most Backward Class & DNC — TN-specific MBC tier)
  SC  → SC
  SCA → SC  (Arunthathiyar sub-pool of SC — same canonical category)
  ST  → ST
  EWS → not in PDF (TN folds into OC)

For Avanti JNV TN student:
  - JNV is Central govt school → NOT eligible for 7.5% GSQ
  - Compete in regular OC/BC/BCM/MBC/SC/SCA/ST per caste category

Output (to extracted_data/):
  - TN_engg_cutoff_marks_2025.csv          — long, every (college,branch,cat) cell
  - TN_engg_state_ranks_2025.csv           — long format with rank values
  - TN_engg_closing_ranks_govt_2025.csv    — govt scope, joined marks+rank
  - TN_engg_consolidated_5cat_govt_2025.csv — schema-canonical
"""
from __future__ import annotations
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "TN" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "TN"
DATA_YEAR = 2025
CET_NAME = "TNEA"
SOURCE_URL = "https://cutoff.tneaonline.org/"

CATEGORIES = ["OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"]


# ───────────────────────────────────────────────────────────────────────────
# Govt-college classifier
# ───────────────────────────────────────────────────────────────────────────
GOVT_PATTERNS = [
    (r"^University Departments of Anna University", "Govt"),
    (r"\bAnna University Regional Campus", "Govt"),
    (r"\bGovernment College of Engineering", "Govt"),
    (r"\bGovernment Engineering College", "Govt"),
    (r"\bGovt\.?\s+College", "Govt"),
    (r"\bGovernment College of Tech", "Govt"),
    (r"\bAlagappa\s+Chettiar", "Govt"),  # ACGCET Karaikudi — govt
    (r"\bUniversity College of Engineering", "Govt"),  # Anna Univ regional centres
    (r"\bIndian Institute", "Govt"),  # IIITs at TN (e.g. IIITDM)
    (r"\bM\.I\.T\.\s+Anna University|MIT Anna University|Madras Institute of Technology, Anna", "Govt"),
]

# Curated whitelist of TN govt-aided engineering colleges (legacy aided autonomous)
GOVT_AIDED_WHITELIST = [
    r"\bP\.?S\.?G\.?\s+College of Technology\b",       # PSG Tech Coimbatore (govt-aided)
    r"\bPSG Institute of Technology\b",
    r"\bThiagarajar College of Engineering\b",         # TCE Madurai (aided autonomous)
    r"\bC\.?S\.?I\.? Institute of Technology\b",       # Some are aided
    r"\bK\.?L\.?N\.? College of Engineering\b",
    r"\bCoimbatore Institute of Technology\b",         # CIT (aided autonomous)
    r"\bMepco Schlenk Engineering College\b",          # Mepco Sivakasi (aided)
    r"\bSethu Institute of Technology\b",              # aided in some lists
    r"\bSSN College of Engineering\b",                 # Sometimes classified aided
    r"\bA C College of Engineering and Technology\b",  # AC Tech Karaikudi
]


def classify_tn_college(name: str) -> str:
    if not name:
        return "Unknown"
    for pat, cls in GOVT_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            return cls
    for pat in GOVT_AIDED_WHITELIST:
        if re.search(pat, name, re.IGNORECASE):
            return "Govt-Aided"
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided"}


# ───────────────────────────────────────────────────────────────────────────
# Canonical 5-cat mapping
# ───────────────────────────────────────────────────────────────────────────
def normalise_category(c: str) -> str:
    return {
        "OC":  "GEN",
        "BC":  "OBC-NCL",
        "BCM": "OBC-NCL",
        "MBC": "OBC-NCL",
        "SC":  "SC",
        "SCA": "SC",
        "ST":  "ST",
    }.get(c, "OTHER")


# ───────────────────────────────────────────────────────────────────────────
# Long format conversion
# ───────────────────────────────────────────────────────────────────────────
def to_long(df: pd.DataFrame, value_name: str) -> pd.DataFrame:
    """Wide → long: one row per (college, branch, category)."""
    long = df.melt(
        id_vars=["Code", "College", "Branch"],
        value_vars=CATEGORIES,
        var_name="category_raw",
        value_name=value_name,
    )
    long = long.dropna(subset=[value_name])
    # Strip * (vacant seats marker) and "—" / "-" / blanks
    long[value_name] = long[value_name].astype(str).str.strip()
    long = long[~long[value_name].isin(["—", "-", "", "nan"])]
    long["has_vacant"] = long[value_name].str.contains(r"\*", regex=True)
    long[value_name] = long[value_name].str.replace("*", "", regex=False)
    long[value_name] = long[value_name].str.replace(",", "", regex=False)
    long[value_name] = pd.to_numeric(long[value_name], errors="coerce")
    long = long.dropna(subset=[value_name])
    return long


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — load Cutoff Marks + Ranks CSVs")
    marks_df = pd.read_csv(SOURCE / f"TN_TNEA_{DATA_YEAR}_cutoff_marks.csv",
                            dtype={"Code": str})
    ranks_df = pd.read_csv(SOURCE / f"TN_TNEA_{DATA_YEAR}_state_merit_ranks.csv",
                            dtype={"Code": str})
    print(f"  Cutoff marks rows: {len(marks_df):,}  unique colleges: {marks_df['Code'].nunique()}")
    print(f"  State ranks rows:  {len(ranks_df):,}  unique colleges: {ranks_df['Code'].nunique()}")

    # Sanity check shape match
    assert len(marks_df) == len(ranks_df), "Marks and Ranks CSVs differ in length!"

    print("\nStage 2 — wide → long")
    marks_long = to_long(marks_df, "closing_mark")
    ranks_long = to_long(ranks_df, "closing_rank")
    print(f"  Marks long: {len(marks_long):,}  Ranks long: {len(ranks_long):,}")

    print("\nStage 3 — join marks + ranks on (Code, College, Branch, category_raw)")
    merged = marks_long.merge(
        ranks_long[["Code", "College", "Branch", "category_raw", "closing_rank"]],
        on=["Code", "College", "Branch", "category_raw"],
        how="outer",
    )
    print(f"  Merged rows: {len(merged):,}")

    # Save raw merged
    merged.to_csv(OUT / f"{STATE_CODE}_engg_all_cutoffs_{DATA_YEAR}.csv", index=False)

    print("\nStage 4 — classify govt scope, normalise to 5-cat")
    merged["college_type"] = merged["College"].apply(classify_tn_college)
    print("  by college_type:")
    for t, n in merged.groupby(["Code", "College", "college_type"]).size().reset_index().college_type.value_counts().items():
        print(f"    {t:18s} {n:>4} colleges")

    govt = merged[merged["college_type"].isin(GOVT_TYPES)].copy()
    govt["category"] = govt["category_raw"].apply(normalise_category)
    govt["state"] = "TAMIL NADU"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "Final (post-counselling 2025-26)"
    govt["quota"] = "State (TN domicile)"
    govt["gender"] = "All"
    govt["rank_basis"] = "TNEA Cutoff Mark (out of 200) and TNEA State Merit Rank"
    govt["source_url"] = SOURCE_URL

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "Code", "College", "college_type",
        "Branch",
        "quota", "category_raw", "category", "gender",
        "closing_mark", "closing_rank", "has_vacant",
        "rank_basis", "source_url",
    ]].rename(columns={
        "Code": "college_code",
        "College": "college_name",
        "Branch": "branch_name",
    }).sort_values(["college_code", "branch_name", "category_raw"])

    govt_out.to_csv(OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False)
    print(f"\n  govt closing-rank rows: {len(govt_out):,}")
    print(f"  unique govt colleges:   {govt_out['college_code'].nunique()}")
    print(f"  unique govt × branch:   {govt_out.groupby(['college_code','branch_name']).ngroups}")

    # Schema-canonical 5-cat: aggregate SCA→SC, BC/BCM/MBC→OBC-NCL
    print("\nStage 5 — schema-canonical 5-cat consolidated")
    canon = govt_out.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(
        opening_mark=("closing_mark", "max"),  # higher mark = stricter
        closing_mark=("closing_mark", "min"),  # lower = lowest admitted
        opening_rank=("closing_rank", "min"),
        closing_rank=("closing_rank", "max"),
    ).reset_index()
    canon["last_round_with_max"] = "Final (post-counselling)"
    canon["rank_basis"] = "TNEA Cutoff Mark / State Merit Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    print(f"\n=== TN sanity (govt scope, OC/GEN, top 10 hardest by closing_mark) ===")
    sample = govt_out[(govt_out["category_raw"] == "OC")].sort_values("closing_mark", ascending=False).head(10)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_mark", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
