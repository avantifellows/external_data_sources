"""
Odisha NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Odisha Joint Entrance Examination Cell (OJEE).
           https://ojee.nic.in
The official OJEE portal has rolled to 2026 — the 2025 college-wise
allotment PDFs are no longer accessible. To capture *some* college-wise
signal we aggregate from publicly visible third-party education
aggregator pages and clearly mark the data as NOT OFFICIAL.

Sources used (preserved verbatim in source/OD/):
  - THIRDPARTY_2025_NEET_AIR_UR.csv
      vedantu.com/neet/odisha-neet-cut-off (fetched May-2026)
      12 govt MBBS colleges, UR-only, NEET AIR (i.e. national rank)
  - THIRDPARTY_2024_state_rank.csv
      collegedekho.com/articles/neet-cutoff-for-odisha-aiq-state-quota-seats
      7 govt MBBS colleges × {UR, SC, ST}, Odisha state rank (2024
      counselling, used as proxy for state-quota cutoffs)

OBC and EWS category-wise college-level data was not available from any
third-party source we could find. The official OJEE counselling reports
remain the only complete source — refresh once OJEE re-publishes the
2025 round-wise allotment PDFs (or 2026 cycle goes live).

Govt MBBS colleges in Odisha (per NMC list, ~10 total):
  SCB MC Cuttack, MKCG MC Berhampur, VIMSAR Burla, Pt Raghunath Murmu MC
  Baripada, SLN MC Koraput, GMC Balangir, GMC Balasore (Fakir Mohan),
  GMC Keonjhar, GMC Sundargarh, GMC Bhawanipatna, JK Medical College
  Jajpur, Shri Jagannath Medical College Puri.
  + Govt Dental College Cuttack (BDS, not in 3rd-party data).

Outputs (to ../extracted_data/), all suffixed with `_THIRDPARTY` to make
provenance unambiguous:
  - OD_all_allotments_2025_THIRDPARTY.csv      — combined long format
  - OD_closing_ranks_state_govt_2025_THIRDPARTY.csv — long
  - OD_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv — wide
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "OD"
OUT = ROOT / "extracted_data"
STATE_CODE = "OD"

ORDER = ["UR", "OBC", "EWS", "SC", "ST"]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — load third-party CSVs (UNOFFICIAL)...")
    sources = list(SOURCE.glob("THIRDPARTY_*.csv"))
    if not sources:
        raise FileNotFoundError(f"No THIRDPARTY_*.csv files in {SOURCE}")
    parts = []
    for f in sources:
        df = pd.read_csv(f)
        print(f"  {f.name}: {len(df)} rows")
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["program"] = "MBBS"
    df["state_code"] = STATE_CODE
    df["NOT_OFFICIAL"] = True
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025_THIRDPARTY.csv", index=False)
    print(f"  Total: {len(df)} (across {df['source_site'].nunique()} aggregators)")

    print("\nStage 2 — closing rank long format...")
    # Take MAX(closing_rank) per (college, year, rank_type, category) — i.e.
    # if a college appears with the same rank type for the same category
    # in multiple sources, keep the more permissive value.
    cr = (
        df.groupby(["college", "program", "year", "rank_type", "category"])["closing_rank"]
        .max()
        .reset_index()
        .rename(columns={"closing_rank": "closing_rank_THIRDPARTY"})
    )
    cr["NOT_OFFICIAL"] = True
    cr.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_THIRDPARTY.csv",
        index=False,
    )
    print(f"  Long rows: {len(cr)}")

    print("\nStage 3 — wide pivot (per year × rank_type)...")
    piv = cr.pivot_table(
        index=["college", "program", "year", "rank_type"],
        columns="category",
        values="closing_rank_THIRDPARTY",
        aggfunc="first",
    ).reset_index()
    cat_cols = [c for c in ORDER if c in piv.columns]
    piv = piv[["college", "program", "year", "rank_type"] + cat_cols]
    piv["NOT_OFFICIAL"] = True
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv",
        index=False,
    )
    print(f"  Pivot rows: {len(piv)}")

    print("\n=== Odisha govt — by year × rank_type (THIRD-PARTY, NOT OFFICIAL) ===")
    print(piv.sort_values(["year", "rank_type", "UR"], na_position="last").to_string(index=False))

    print("\n⚠️  This data is sourced from third-party education aggregators")
    print("    (vedantu.com, collegedekho.com). Cross-check against official")
    print("    OJEE allotment PDFs once re-published.")


if __name__ == "__main__":
    main()
