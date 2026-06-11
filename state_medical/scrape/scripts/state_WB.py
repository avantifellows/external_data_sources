"""
West Bengal NEET UG 2025 — state govt closing ranks pipeline.

Authority: West Bengal Medical Counselling Committee (WBMCC).
           https://wbmcc.nic.in
Source PDFs: cdnbbsr.s3waas.gov.in/s3aae8d1e00b15a30e5901227e97ffbef7/uploads/

Last round used: cumulative through R2 (R1 + R2). WB had no formal
"R3" — only an Online Stray Round (Nov 18, 2025) which we exclude per
the project pattern. R2 is the final main round.

Govt-college filter:
  - WB state quota counselling includes BOTH state govt colleges AND
    state-quota seats at private colleges (the "State Quota" allotted-
    quota label).
  - We filter institutes by name (containing "GOVT"/"GOVERNMENT" OR in
    a known govt institution list — old colleges like Medical College
    Kolkata, NRS, RG Kar etc. don't have "Govt" in their name).
  - Then filter to allotted_quota = "State Quota" only (drops Private
    Management Quota + NRI).
  - Result: 25 govt MBBS + 3 govt BDS = 28 colleges (vs NMC list 26+3,
    missing 1 new college).

Reservation taxonomy (see state_reservation_taxonomy.csv):
  - Vertical: UR (Open) / EWS / OBC-A (predominantly Muslim BC) /
    OBC-B (Hindu BC) / SC / ST
  - Horizontal: PwD (5%)
  - WB does NOT have a separate "OBC" central category in state
    counselling — only OBC-A and OBC-B sub-categories per WB Backward
    Class Rules.
  - WB has NO horizontal Govt-School-Student quota.

For Avanti JNV WB student (typical):
  - JNV is Central govt school. WB doesn't have govt-school horizontal
    quota → student competes in regular state quota under their WB caste
    sub-category (UR/EWS/OBC-A/OBC-B/SC/ST per WB list).
  - Look up: WB_closing_ranks_state_govt_2025_pivot.csv

Outputs (to ../extracted_data/):
  - WB_all_allotments_2025.csv             — raw 11,087 rows
  - WB_closing_ranks_state_govt_2025.csv   — long format
  - WB_closing_ranks_state_govt_2025_pivot.csv — wide pivot
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "WB"
OUT = ROOT / "extracted_data"
STATE_CODE = "WB"

ROUNDS = [
    ("WB_R1_2025.pdf", "R1"),
    ("WB_R2_2025.pdf", "R2"),
]

# Govt institutions in WB whose name doesn't contain "GOVT/GOVERNMENT"
KNOWN_GOVT_NAMES = {
    "MEDICAL COLLEGE, KOLKATA", "R.G. KAR MEDICAL COLLEGE",
    "NILRATAN SIRCAR MEDICAL COLLEGE", "CALCUTTA NATIONAL MEDICAL COLLEGE",
    "INSTITUTE OF PG MEDICAL EDUCATION AND RESEARCH",
    "BURDWAN MEDICAL COLLEGE", "BANKURA SAMMILANI MEDICAL COLLEGE",
    "MIDNAPORE MEDICAL COLLEGE", "NORTH BENGAL MEDICAL COLLEGE",
    "MALDA MEDICAL COLLEGE", "MURSHIDABAD MEDICAL COLLEGE",
    "COLLEGE OF MEDICINE AND JNM HOSPITAL",
    "COLLEGE OF MEDICINE AND SAGORE DUTTA HOSPITAL",
    "MAHARAJA JITENDRA NARAYAN MEDICAL COLLEGE", "ESI PGI MSR",
    "BURDWAN DENTAL COLLEGE", "DR. R. AHMED DENTAL COLLEGE",
    "NORTH BENGAL DENTAL COLLEGE",
}

VERTICAL_ORDER = ["UR", "EWS", "OBC-A", "OBC-B", "OBC", "SC", "ST"]


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse round PDFs (table extraction)
# ───────────────────────────────────────────────────────────────────────────
def parse_wb_pdf(path: Path, label: str) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 9:
                        continue
                    rd = str(r[0] or "").strip()
                    air = str(r[1] or "").strip().replace(",", "")
                    if not (rd.isdigit() and air.isdigit()):
                        continue
                    rows.append({
                        "file_round": label,
                        "allotted_round": int(rd),
                        "air": int(air),
                        "choice": str(r[2] or "").strip(),
                        "institute": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "course": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "allotted_quota": re.sub(r"\s+", " ", str(r[5] or "")).strip(),
                        "allotted_category": re.sub(r"\s+", " ", str(r[6] or "")).strip(),
                        "candidate_category": re.sub(r"\s+", " ", str(r[7] or "")).strip(),
                        "status": re.sub(r"\s+", " ", str(r[8] or "")).strip(),
                    })
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — govt filter + category cleanup
# ───────────────────────────────────────────────────────────────────────────
def is_govt(name: str) -> bool:
    n = str(name).upper()
    if "GOVT" in n or "GOVERNMENT" in n:
        return True
    return any(k in n for k in KNOWN_GOVT_NAMES)


def normalize_category(cat: str) -> tuple[str, bool]:
    """Strip PwD; collapse WB OBC-A/B variants ('OBC-A (Non- Creamy Layer)' → 'OBC-A')."""
    is_pwd = cat.endswith("PwD")
    base = cat.replace(" PwD", "").strip()
    # Collapse WB OBC-A and OBC-B variants
    base = re.sub(r"OBC-A\s*\(.*?\)", "OBC-A", base)
    base = re.sub(r"OBC-B\s*\(.*?\)", "OBC-B", base)
    base = re.sub(r"OBC\s*\(.*?\)", "OBC", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base, is_pwd


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R1+R2 PDFs (~1 min)...")
    all_rows = []
    for fname, label in ROUNDS:
        path = SOURCE / fname
        rows = parse_wb_pdf(path, label)
        print(f"  {fname} ({label}): {len(rows):,} rows")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df):,}")

    print("\nStage 2 — filtering to govt + State Quota...")
    gov = df[df["institute"].apply(is_govt)].copy()
    gov_sq = gov[gov["allotted_quota"] == "State Quota"].copy()
    print(f"  Govt institutes: {gov_sq['institute'].nunique()}, "
          f"rows: {len(gov_sq):,}")

    # Normalize categories
    norm = gov_sq["allotted_category"].apply(normalize_category)
    gov_sq["category"] = [n[0] for n in norm]
    gov_sq["is_pwd"] = [n[1] for n in norm]

    print("\nStage 3 — closing ranks...")
    cr = (
        gov_sq.groupby(["institute", "course", "category", "is_pwd"])
        .agg(
            closing_air=("air", "max"),
            opening_air=("air", "min"),
            allotted_count=("air", "count"),
        )
        .reset_index()
    )
    last_round = (
        gov_sq.sort_values("air", ascending=False)
        .drop_duplicates(["institute", "course", "category", "is_pwd"])
        [["institute", "course", "category", "is_pwd", "file_round"]]
        .rename(columns={"file_round": "last_round_with_max"})
    )
    cr = cr.merge(last_round, on=["institute", "course", "category", "is_pwd"])
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    print(f"  {len(cr):,} CR rows")

    print("\nStage 4 — wide pivot (non-PwD)...")
    nonpwd = cr[~cr["is_pwd"]]
    piv = nonpwd.pivot_table(
        index=["institute", "course"], columns="category",
        values="closing_air", aggfunc="first",
    ).reset_index()
    present = [c for c in VERTICAL_ORDER if c in piv.columns]
    piv = piv[["institute", "course"] + present]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print(f"\n=== Top 5 WB govt MBBS by UR closing AIR ===")
    print(piv[piv["course"] == "MBBS"].sort_values("UR").head(5).to_string(index=False))


if __name__ == "__main__":
    main()
