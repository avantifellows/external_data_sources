"""
Haryana NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Department of Medical Education and Research (DMER), Haryana.
           https://dmer.haryana.gov.in / https://uhsrugcounselling.com
The DMER Haryana site only publishes counselling SCHEDULES, not college-
wise allotments. The actual allotment portal (uhsrugcounselling.com,
operated by Pt B D Sharma UHS Rohtak) has been in persistent maintenance
mode through May-2026. As a stopgap we aggregate from publicly visible
third-party education aggregator pages and clearly mark the data as NOT
OFFICIAL.

Sources used (preserved verbatim in source/HR/):
  - THIRDPARTY_2025_R3_open.csv
      classtocollege.com — Round 3 closing approx AIR + marks for 7
      govt MBBS colleges, UR/Open category only.
  - THIRDPARTY_2025_PGIMS_categorywise.csv
      pw.live — Round 3 PGIMS Rohtak by category (UR/OBC/EWS/SC/ST),
      reported as ranges; we capture the upper bound (= closing rank).

Govt MBBS colleges in Haryana (per NMC list):
  Pt B D Sharma PGIMS Rohtak, Kalpana Chawla GMC Karnal, BPS GMC Sonepat
  (women), SHKM GMC Mewat (Nalhar), Maharaja Agrasen MC Agroha, Shri
  Atal Bihari Vajpayee GMC Faridabad, ESIC MC Faridabad, plus newer:
  GMC Bhiwani, GMC Narnaul, GMC Jind, GMC Kaithal.

Outputs (to ../extracted_data/), all suffixed with `_THIRDPARTY`:
  - HR_all_allotments_2025_THIRDPARTY.csv
  - HR_closing_ranks_state_govt_2025_THIRDPARTY.csv
  - HR_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "HR"
OUT = ROOT / "extracted_data"
STATE_CODE = "HR"

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
        # normalize: ensure shared columns; drop closing_marks/notes for the union
        for col in ("closing_marks", "notes"):
            if col not in df.columns:
                df[col] = pd.NA
        print(f"  {f.name}: {len(df)} rows")
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["program"] = "MBBS"
    df["state_code"] = STATE_CODE
    df["NOT_OFFICIAL"] = True
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025_THIRDPARTY.csv", index=False)
    print(f"  Total: {len(df)} (across {df['source_site'].nunique()} aggregators)")

    print("\nStage 2 — closing rank long format (MAX across sources per cell)...")
    cr = (
        df.groupby(["college", "program", "year", "round", "rank_type", "category"])["closing_rank"]
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

    print("\nStage 3 — wide pivot...")
    piv = cr.pivot_table(
        index=["college", "program", "year", "round", "rank_type"],
        columns="category",
        values="closing_rank_THIRDPARTY",
        aggfunc="first",
    ).reset_index()
    cat_cols = [c for c in ORDER if c in piv.columns]
    piv = piv[["college", "program", "year", "round", "rank_type"] + cat_cols]
    piv["NOT_OFFICIAL"] = True
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv",
        index=False,
    )
    print(f"  Pivot rows: {len(piv)}")

    print("\n=== Haryana govt — 2025 R3 (THIRD-PARTY, NOT OFFICIAL) ===")
    print(piv.sort_values("UR", na_position="last").to_string(index=False))

    print("\n⚠️  This data is sourced from third-party education aggregators")
    print("    (classtocollege.com, pw.live). Closing ranks are approximate")
    print("    and represent ranges cited in those articles. Cross-check")
    print("    against official DMER Haryana / uhsrugcounselling.com")
    print("    allotment lists once they become accessible.")


if __name__ == "__main__":
    main()
