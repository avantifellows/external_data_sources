"""
Karnataka NEET UG 2025 — state govt closing ranks pipeline.

Authority: Karnataka Examinations Authority (KEA), https://cetonline.karnataka.gov.in
Sources: 6 PDFs in ../source/KA/ — R1/R2/R3 final allotment lists for MBBS+BDS,
         plus seat matrix and guidelines (the latter for reservation policy).

Last round used: Round 3 (Final, 8-Dec-2025).
  - Stray rounds (16-Dec, 17-Dec) excluded — fill leftover seats at much
    lower ranks, not a meaningful target.
  - R1 (2-Aug) + R2 (23-Sep) + R3 (8-Dec) are unioned; closing rank per
    (college, program, category) = MAX(rank) across the union.
  - The `last_round_with_max` column in the output records which round
    contributed the closing rank for each row.

Govt-college filter:
  - KEA's "MBBS-GOVT/BDS-GOVT" course type includes BOTH state govt colleges
    AND the 40% govt-fee quota seats at private colleges (low-fee but private
    campus). The user's scope is state govt colleges only.
  - Filter: median fee ≤ ₹80,000, plus explicit ESIC inclusion (~₹109k fee
    but central-govt institutes that count as govt under our definition).
  - Result: 24 govt MBBS + 2 govt BDS colleges (matches NMC list of 24+3,
    minus 1 BDS — ESIC Dental Gulbarga only appears under PRIV in KEA).

Reservation taxonomy (see state_reservation_taxonomy.csv for full doc):
  Vertical: GM / 1 / 2A / 2B / 3A / 3B / SC / ST
  Horizontal: G (default) / R (Rural 15%) / K (Kannada Medium 5%)
  Domicile sub-pool: RK (default) / H (Hyderabad-Karnataka 8% under Art. 371J)
  Combined codes: e.g. 2ARH = Cat 2A + Rural + HK domicile
  Special verticals: NCC, SPO, D, XD, JK, CAP, PHM (small quotas, dropped
    from the wide pivot)

For Avanti JNV Karnataka student (typical):
  - Domicile: Karnataka → eligible for state quota
  - JNV is in rural area but Hindi/English medium → R likely yes, K no
  - HK applies only if from Bidar/Kalaburagi/Yadgir/Raichur/Koppal/Ballari/
    Vijayanagara districts
  - Vertical: based on caste — most OBC central students map to KA 2A/3A/3B

Outputs (to ../extracted_data/):
  - KA_all_allotments_R1_R2_R3_2025.csv         — raw 24,418 allotments
  - KA_college_govt_classification.csv          — fee-based govt flag per college
  - KA_closing_ranks_govt_2025.csv              — all "GOVT" course-name (incl 40% at private)
  - KA_closing_ranks_govt_2025_pivot.csv        — wide pivot of above
  - KA_closing_ranks_state_govt_2025.csv        — TRUE state govt only (26 colleges)
  - KA_closing_ranks_state_govt_2025_pivot.csv  — wide pivot for state govt
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "KA"
OUT = ROOT / "extracted_data"
STATE_CODE = "KA"
ROUND_LAST = 3
EXCLUDE_STRAY = True  # state stray rounds 1+2 excluded

PROGRAMS = ["MBBS", "BDS"]
ROUNDS = [1, 2, 3]


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse all 6 R1/R2/R3 × MBBS/BDS allotment PDFs
# ───────────────────────────────────────────────────────────────────────────
def parse_kea_allotment(pdf_path: Path, round_num: int) -> list[dict]:
    """Extract all rows from a KEA round-final allotment PDF.

    Schema: SL.NO | All India Rank | Course Code | College | Course Name
            | Allotted Category | Fees | Status (R2/R3 only)
    """
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 7:
                        continue
                    sl = str(r[0] or "").strip()
                    if not sl.isdigit():
                        continue
                    rank = str(r[1] or "").strip().replace(",", "")
                    if not rank.isdigit():
                        continue
                    rows.append({
                        "round": round_num,
                        "sl": int(sl),
                        "rank": int(rank),
                        "course_code": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                        "college": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "course_name": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "category": re.sub(r"\s+", " ", str(r[5] or "")).strip(),
                        "fees": re.sub(r"\s+", " ", str(r[6] or "")).strip(),
                        "status": (re.sub(r"\s+", " ", str(r[7] or "")).strip()
                                   if len(r) > 7 else "Allotted"),
                    })
    return rows


def parse_all_rounds() -> pd.DataFrame:
    all_rows = []
    for prog in PROGRAMS:
        for rd in ROUNDS:
            f = SOURCE / f"KA_R{rd}_{prog}_final_2025.pdf"
            print(f"  parsing {f.name}...", end="", flush=True)
            rows = parse_kea_allotment(f, rd)
            print(f" {len(rows):,} rows")
            all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df["program"] = df["course_name"].str.extract(r"^(MBBS|BDS)")
    return df


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — classify true govt vs private-with-govt-quota by fee
# ───────────────────────────────────────────────────────────────────────────
TRUE_GOVT_FEE_THRESHOLD = 80_000  # govt colleges charge ~₹64k MBBS / ~₹49k BDS


def classify_govt(df_govt_pool: pd.DataFrame) -> pd.DataFrame:
    df = df_govt_pool.copy()
    df["fees_n"] = pd.to_numeric(df["fees"], errors="coerce")
    df["college_clean"] = df["college"].astype(str).str.split(",").str[0].str.strip()
    fee_stats = (
        df.groupby(["college_clean", "program"])
        .agg(median_fee=("fees_n", "median"),
             min_fee=("fees_n", "min"),
             n=("fees_n", "count"))
        .reset_index()
    )

    def is_true_govt(row):
        if row["median_fee"] <= TRUE_GOVT_FEE_THRESHOLD:
            return True
        # Include ESIC central institutes (~₹109k fee but govt-funded)
        n = row["college_clean"].lower()
        if "esi" in n and ("medical college" in n or "dental college" in n):
            return True
        return False

    fee_stats["is_true_govt"] = fee_stats.apply(is_true_govt, axis=1)
    return fee_stats


# ───────────────────────────────────────────────────────────────────────────
# Stage 3 — closing ranks per (college, program, category)
# ───────────────────────────────────────────────────────────────────────────
def compute_closing_ranks(df_govt_pool: pd.DataFrame) -> pd.DataFrame:
    df = df_govt_pool.copy()
    df["college_clean"] = df["college"].astype(str).str.split(",").str[0].str.strip()

    # Closing rank = MAX(rank) per (college, program, category)
    cr = (
        df.groupby(["college_clean", "program", "category"])
        .agg(closing_rank=("rank", "max"),
             opening_rank=("rank", "min"),
             allotted_count=("rank", "count"))
        .reset_index()
    )
    # Track which round contributed the MAX rank
    last_round = (
        df.sort_values("rank", ascending=False)
        .drop_duplicates(["college_clean", "program", "category"])
        [["college_clean", "program", "category", "round"]]
        .rename(columns={"round": "last_round_with_max"})
    )
    cr = cr.merge(last_round, on=["college_clean", "program", "category"])

    # Decompose category into vertical + horizontal flags
    cr[["vertical", "horizontal", "domicile_subpool"]] = (
        cr["category"].apply(decompose_ka_category).apply(pd.Series)
    )

    return cr.sort_values(["college_clean", "program", "category"])


def decompose_ka_category(cat: str):
    """Decompose KEA category code into vertical + horizontal + domicile.

    Returns: (vertical, horizontal, domicile_subpool)
      vertical: GM / 1 / 2A / 2B / 3A / 3B / SC / ST / NCC / etc.
      horizontal: '' (None) / Rural / Kannada-Medium
      domicile_subpool: RK (default) / HK
    """
    cat = str(cat).strip()
    SPECIAL = {"NCC", "SPO", "S-G", "D", "XD", "XDF", "CAP", "CAPF",
               "JK", "PHM", "NRI", "OPN", "OTH", "GMP",
               "MA", "ME", "MU", "MM", "MC", "MK"}
    if cat in SPECIAL:
        return cat, "", ""

    is_hk = cat.endswith("H")
    base = cat[:-1] if is_hk else cat
    is_kan = base.endswith("K")
    is_rur = base.endswith("R")
    if is_kan or is_rur:
        base = base[:-1]
    if base.endswith("G") and base != "G":
        base = base[:-1]

    horizontal = "Rural" if is_rur else ("Kannada-Medium" if is_kan else "")
    domicile = "HK" if is_hk else "RK"
    return base, horizontal, domicile


# ───────────────────────────────────────────────────────────────────────────
# Stage 4 — wide pivot for the main verticals (× G horizontal × RK subpool)
# ───────────────────────────────────────────────────────────────────────────
MAIN_VERTICALS = ["GM", "1G", "2AG", "2BG", "3AG", "3BG", "SCG", "STG"]


def build_pivot(cr: pd.DataFrame) -> pd.DataFrame:
    # The "G" suffix isn't always present in raw category codes — GM appears
    # plain. Match on either.
    mask = cr["category"].isin(MAIN_VERTICALS) | cr["category"].isin(
        ["GM", "1", "2A", "2B", "3A", "3B", "SC", "ST"]
    )
    piv = (
        cr[mask].pivot_table(
            index=["college_clean", "program"],
            columns="category", values="closing_rank",
            aggfunc="first",
        ).reset_index()
    )
    present = [c for c in MAIN_VERTICALS if c in piv.columns]
    return piv[["college_clean", "program"] + present]


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print("Stage 1 — parsing 6 round-allotment PDFs (~3 min)...")
    df = parse_all_rounds()
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_R1_R2_R3_2025.csv", index=False)
    print(f"  Total rows: {len(df):,}")

    govt_pool = df[df["course_name"].str.contains("GOVT", na=False)].copy()
    print(f"  Govt-pool rows: {len(govt_pool):,}")

    print("\nStage 2 — classifying true state govt vs private-with-govt-quota...")
    fee_stats = classify_govt(govt_pool)
    fee_stats.to_csv(
        OUT / f"{STATE_CODE}_college_govt_classification.csv", index=False
    )
    true_set = set(
        (fee_stats[fee_stats["is_true_govt"]]["college_clean"]
         + "||"
         + fee_stats[fee_stats["is_true_govt"]]["program"]).tolist()
    )
    print(f"  True state govt: {len(true_set)} (college, program) combos")

    print("\nStage 3 — computing closing ranks...")
    cr = compute_closing_ranks(govt_pool)
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_govt_2025.csv", index=False)
    cr["key"] = cr["college_clean"] + "||" + cr["program"]
    cr_true = cr[cr["key"].isin(true_set)].drop(columns=["key"])
    cr_true.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False
    )
    print(f"  All-govt-pool rows: {len(cr):,}")
    print(f"  State-govt-only rows: {len(cr_true):,}")

    print("\nStage 4 — building wide pivot...")
    piv = build_pivot(cr)
    piv.to_csv(OUT / f"{STATE_CODE}_closing_ranks_govt_2025_pivot.csv", index=False)
    piv["key"] = piv["college_clean"] + "||" + piv["program"]
    piv_true = piv[piv["key"].isin(true_set)].drop(columns=["key"])
    piv_true.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )

    print(f"\n=== Karnataka state govt MBBS — sample (top 8 by GM closing) ===")
    mbbs = piv_true[piv_true["program"] == "MBBS"].sort_values("GM").head(8)
    print(mbbs.to_string(index=False))


if __name__ == "__main__":
    main()
