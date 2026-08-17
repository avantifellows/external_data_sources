"""
Shared third-party-source aggregation helper.

Used by state scripts that read pre-curated `THIRDPARTY_*.csv` files
from `source/<XX>/` (no PDF parsing) and emit the standard outputs in
`extracted_data/`. All outputs are suffixed `_THIRDPARTY` and every row
carries `NOT_OFFICIAL=True`.

Standard input CSV columns (any subset is OK; missing ones are treated as null):
  source_url, source_site, year, round, rank_type, quota, college, category,
  closing_rank, opening_rank, closing_marks, notes

If `quota` is present (e.g. "AIQ 15%" vs "State quota 85%"), it's added
as an extra grouping key — one row per (college, year, round, quota,
category) instead of (college, year, round, category). Wide pivots get a
`quota` column and one row per (college, year, round, quota) with the
categories spread across columns.

Output files written:
  - <STATE>_all_allotments_2025_THIRDPARTY.csv      (all rows from sources)
  - <STATE>_closing_ranks_state_govt_2025_THIRDPARTY.csv  (long format)
  - <STATE>_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv  (wide)

Usage from a per-state script:

    from _thirdparty_pipeline import run_thirdparty_pipeline
    run_thirdparty_pipeline(state_code="GA", state_name="Goa")
"""
from pathlib import Path
import pandas as pd

ORDER = ["UR", "OBC", "EWS", "SC", "ST"]


def run_thirdparty_pipeline(state_code: str, state_name: str,
                             default_program: str = "MBBS"):
    root = Path(__file__).parent.parent
    source_dir = root / "source" / state_code
    out_dir = root / "extracted_data"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"⚠️  {state_name} ({state_code}) — THIRD-PARTY data, NOT OFFICIAL")
    print("Stage 1 — load THIRDPARTY_*.csv files...")
    sources = sorted(source_dir.glob("THIRDPARTY_*.csv"))
    if not sources:
        raise FileNotFoundError(f"No THIRDPARTY_*.csv files in {source_dir}")
    parts = []
    for f in sources:
        df = pd.read_csv(f)
        # ensure shared columns
        for col in ("opening_rank", "closing_rank", "closing_marks", "notes",
                    "round", "rank_type", "quota"):
            if col not in df.columns:
                df[col] = pd.NA
        print(f"  {f.name}: {len(df)} rows")
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    # detect whether any source had a populated quota column
    has_quota = df["quota"].notna().any()
    if "program" not in df.columns:
        df["program"] = default_program
    df["state_code"] = state_code
    df["NOT_OFFICIAL"] = True
    df.to_csv(
        out_dir / f"{state_code}_all_allotments_2025_THIRDPARTY.csv", index=False
    )
    print(f"  Total: {len(df)} (across {df['source_site'].nunique()} aggregators)")

    print("\nStage 2 — closing rank long format (MAX across sources per cell)...")
    grp_cols = ["college", "program", "year", "round", "rank_type", "category"]
    if has_quota:
        grp_cols.insert(5, "quota")
    cr = (
        df.groupby(grp_cols, dropna=False)
        .agg(
            closing_rank_THIRDPARTY=("closing_rank", "max"),
            closing_marks_THIRDPARTY=("closing_marks", "max"),
        )
        .reset_index()
    )
    cr["NOT_OFFICIAL"] = True
    cr.to_csv(
        out_dir / f"{state_code}_closing_ranks_state_govt_2025_THIRDPARTY.csv",
        index=False,
    )
    print(f"  Long rows: {len(cr)}")

    print("\nStage 3 — wide pivot (one row per college × year × round × quota × rank_type)...")
    pivot_index = ["college", "program", "year", "round", "rank_type"]
    if has_quota:
        pivot_index.insert(4, "quota")
    piv = cr.pivot_table(
        index=pivot_index,
        columns="category",
        values="closing_rank_THIRDPARTY",
        aggfunc="first",
    ).reset_index()
    cat_cols = [c for c in ORDER if c in piv.columns]
    other_cats = [c for c in piv.columns
                  if c not in pivot_index + cat_cols]
    piv = piv[pivot_index + cat_cols + other_cats]
    piv["NOT_OFFICIAL"] = True
    piv.to_csv(
        out_dir / f"{state_code}_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv",
        index=False,
    )
    print(f"  Pivot rows: {len(piv)}")

    print(f"\n=== {state_name} govt — THIRD-PARTY (NOT OFFICIAL) ===")
    sort_cols = [c for c in ["year", "round", "quota", "UR"] if c in piv.columns]
    print(piv.sort_values(sort_cols, na_position="last").to_string(index=False))

    print(f"\n⚠️  {state_name} data is sourced from third-party education")
    print("    aggregators. Refresh once official PDFs become accessible.")
