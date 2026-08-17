"""
Tamil Nadu NEET UG 2025 — state govt closing ranks pipeline.

Authority: Selection Committee, DME-TN. https://tnmedicalselection.net
Sources: 4 PDFs in ../source/TN/ — R1, R2, R3, Stray GQ allotment lists,
         plus the prospectus (for reservation policy reference).

Last round used: cumulative through Stray Round (R1 + R2 + R3 + Stray).
  - R1 (3-Nov-2025) is the bulk allotment file (7,964 candidates).
  - R2 (17-Nov-2025) and R3 (24-Dec-2025) are tiny mop-ups (194 + 5 rows).
  - Stray (5-Jan-2026) added — only 2 rows, included since it doesn't
    materially distort and matches "last round" preference.
  - Closing rank per (college, program, community) = MAX(GRANK) across all
    rounds. The `last_round_with_max` column tracks which round contributed.

Two cutoff metrics tracked:
  - **GRANK**: TN state-specific merit rank (lower = harder).
  - **T.MARK**: NEET total marks /720 (higher = harder; we report MIN).
  Both columns are useful — GRANK matches TN portal language, T.MARK is
  more universally interpretable to candidates and Avanti.

Govt-college filter:
  - "GQ" = Government Quota (the 65% state-quota seats).
  - The seat pool comes in 4 "college type" buckets:
      - "Govt. Colleges"  → state govt colleges (KEEP)
      - "SF Colleges"     → Self-Financing (private) colleges,
                             govt-quota seats (DROP — not state govt)
      - "Private"         → private MBBS (DROP)
      - "ESIC"            → A1 pool, Central ESIC institutes (separate;
                             dropped for now — these are also in MCC AIQ)
  - Result: 36 govt MBBS + 3 govt BDS = 39 colleges (vs NMC list of 38+3,
    missing 2 new 2025-26 colleges (Kallakurichi, Tiruvannamalai) and
    Rajah Muthiah which has its own approval history).

Reservation taxonomy (see state_reservation_taxonomy.csv for full doc):
  - Vertical: OC / BC / BCM / MBC&DNC / SC / SCA / ST + EWS (10%, applied
    within OC primarily; doesn't appear as separate code in this file)
  - Horizontal:
      - **GSQ-7.5%** — TN Government School Quota (separate counselling
                       portal — NOT counselled in the GQ stream parsed
                       here. We grabbed `TN_GQ_75pct_15122025.pdf` as a
                       reference but it's BDS-only and small. JNV
                       students are NOT eligible for TN GSQ — see
                       taxonomy CSV.)
      - PwBD, Sports, ESM (small horizontals)

For Avanti JNV TN student (typical):
  - Vertical: BC / MBC&DNC / SC / OC (per caste in TN community list)
  - GSQ-7.5%: NO (JNV is Central govt school, not TN govt)
  - EWS: likely (most below ₹8L family income)
  - So look up the headline community closing rank in this output.

For Avanti's wider TN state-govt-school student pool (non-JNV):
  - Eligible for 7.5% GSQ — see TN_75pct_*.csv (separate output, lower
    cutoffs since pool is restricted to TN-govt-school graduates).

Outputs (to ../extracted_data/):
  - TN_all_allotments_2025.csv                          — raw 8,165 rows
  - TN_closing_ranks_state_govt_2025.csv                — 249 rows
  - TN_closing_ranks_state_govt_2025_pivot_grank.csv    — wide (state rank)
  - TN_closing_ranks_state_govt_2025_pivot_tmark.csv    — wide (NEET marks)
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "TN"
OUT = ROOT / "extracted_data"
STATE_CODE = "TN"

ROUND_FILES = [
    ("TN_R1_GQ_03112025.pdf", "R1"),
    ("TN_R2_GQ_17112025.pdf", "R2"),
    ("TN_R3_GQ_24122025.pdf", "R3"),
    ("TN_stray_GQ_05012026.pdf", "Stray"),
]


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse all round PDFs
# ───────────────────────────────────────────────────────────────────────────
def parse_tn_pdf(path: Path, round_label: str) -> list[dict]:
    """Schema: SNO | GRANK | ARNO | NAME | COMMUNITY | T.MARK |
       ALLOTTED FROM | ALLOTTED TO | CATEGORY | STATUS"""
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 7:
                        continue
                    sno = str(r[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    grank = str(r[1] or "").strip().replace(",", "")
                    if not grank.isdigit():
                        continue
                    rows.append({
                        "round": round_label,
                        "sno": int(sno),
                        "grank": int(grank),
                        "arno": str(r[2] or "").strip(),
                        "name": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "community": str(r[4] or "").strip(),
                        "tmark": str(r[5] or "").strip(),
                        "allotted_from": re.sub(r"\s+", " ", str(r[6] or "")).strip(),
                        "allotted_to": (
                            re.sub(r"\s+", " ", str(r[7] or "")).strip()
                            if len(r) > 7 else ""
                        ),
                        "category": (
                            re.sub(r"\s+", " ", str(r[8] or "")).strip()
                            if len(r) > 8 else ""
                        ),
                        "status": (
                            re.sub(r"\s+", " ", str(r[9] or "")).strip()
                            if len(r) > 9 else ""
                        ),
                    })
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — parse the "ALLOTTED TO" string into pool/college type/college
# ───────────────────────────────────────────────────────────────────────────
ALLOC_PATTERN = re.compile(
    r"^(GQ_MBBS|GQ_BDS|A1_MBBS|A1_BDS|MQ_MBBS|MQ_BDS|NRI_MBBS|NRI_BDS)"
    r"\s*\(([^)]+)\)\s*(.*)$"
)


def parse_allocation(s: str):
    m = ALLOC_PATTERN.match(str(s))
    if m:
        seat_pool = m.group(1)
        college_type = m.group(2).strip()
        college = m.group(3).strip()
        program = "MBBS" if "MBBS" in seat_pool else "BDS"
        return seat_pool, college_type, college, program
    return None, None, str(s), None


# ───────────────────────────────────────────────────────────────────────────
# Stage 3 — closing ranks per (college, program, community)
# ───────────────────────────────────────────────────────────────────────────
def compute_closing_ranks(state_gov_df: pd.DataFrame) -> pd.DataFrame:
    df = state_gov_df.copy()
    df["tmark"] = pd.to_numeric(df["tmark"], errors="coerce")

    cr = (
        df.groupby(["college", "program", "community"])
        .agg(
            closing_grank=("grank", "max"),
            opening_grank=("grank", "min"),
            closing_tmark=("tmark", "min"),
            opening_tmark=("tmark", "max"),
            allotted_count=("grank", "count"),
        )
        .reset_index()
    )
    last_round = (
        df.sort_values("grank", ascending=False)
        .drop_duplicates(["college", "program", "community"])
        [["college", "program", "community", "round"]]
        .rename(columns={"round": "last_round_with_max"})
    )
    return cr.merge(last_round, on=["college", "program", "community"]).sort_values(
        ["college", "program", "community"]
    )


# ───────────────────────────────────────────────────────────────────────────
# Stage 4 — wide pivots (one for GRANK, one for T.MARK)
# ───────────────────────────────────────────────────────────────────────────
COMMUNITY_ORDER = ["OC", "BC", "BCM", "MBC&DNC", "SC", "SCA", "ST"]


def build_pivot(cr: pd.DataFrame, value_col: str) -> pd.DataFrame:
    piv = cr.pivot_table(
        index=["college", "program"],
        columns="community", values=value_col,
        aggfunc="first",
    ).reset_index()
    present = [c for c in COMMUNITY_ORDER if c in piv.columns]
    return piv[["college", "program"] + present]


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing 4 round PDFs (~30s for the big R1)...")
    all_rows = []
    for fname, label in ROUND_FILES:
        path = SOURCE / fname
        rows = parse_tn_pdf(path, label)
        print(f"  {fname} ({label}): {len(rows):,} rows")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df):,}")

    print("\nStage 2 — parsing 'ALLOTTED TO' into seat-pool / college-type / college...")
    parsed = df["allotted_to"].apply(parse_allocation)
    df["seat_pool"] = [p[0] for p in parsed]
    df["college_type"] = [p[1] for p in parsed]
    df["college"] = [p[2] for p in parsed]
    df["program"] = [p[3] for p in parsed]

    state_gov = df[
        df["seat_pool"].isin(["GQ_MBBS", "GQ_BDS"])
        & df["college_type"].fillna("").str.contains("Govt", case=False)
    ].copy()
    print(f"  State govt rows: {len(state_gov):,}")

    print("\nStage 3 — computing closing ranks...")
    cr = compute_closing_ranks(state_gov)
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    print(f"  {len(cr):,} closing-rank rows over "
          f"{cr['college'].nunique()} colleges "
          f"({cr[cr['program']=='MBBS']['college'].nunique()} MBBS + "
          f"{cr[cr['program']=='BDS']['college'].nunique()} BDS)")

    print("\nStage 4 — building wide pivots...")
    piv_g = build_pivot(cr, "closing_grank")
    piv_g.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_grank.csv",
        index=False,
    )
    piv_t = build_pivot(cr, "closing_tmark")
    piv_t.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_tmark.csv",
        index=False,
    )

    print(f"\n=== TN state govt MBBS — top 5 by OC closing GRANK ===")
    mbbs_g = piv_g[piv_g["program"] == "MBBS"].sort_values("OC").head(5)
    print(mbbs_g.to_string(index=False))


if __name__ == "__main__":
    main()
