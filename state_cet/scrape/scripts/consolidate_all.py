"""
Consolidate per-state 5-cat closing-rank CSVs into a single national table.

This is the project-level deliverable — the analogue of the parent project's
`nit_hs_closing_ranks_all_categories.csv` but for state CET closing ranks.

Currently included states (engineering + per-state additional streams):
  - MAHARASHTRA: engineering / pharmacy / architecture (1,688 rows × 38 colleges)
  - KARNATAKA:   engineering / nursing / pharmacy (569 rows × 44 colleges, 2024 proxy for 2025)
  - TAMIL NADU:  engineering only (1,040 rows × 36 colleges)
                 — TN engineering uses board-marks (out of 200) AND state merit
                   ranks both. Schema includes `closing_mark` and `closing_rank`.

Schema notes:
  - Maharashtra & Karnataka populate `closing_rank` (rank-based admission)
    and leave `closing_mark` empty.
  - Tamil Nadu populates BOTH `closing_mark` (out of 200) and `closing_rank`
    (state merit rank).
  - The `rank_basis` column distinguishes which metric is authoritative
    per state.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "extracted_data"

INPUTS = [
    ("MAHARASHTRA",   "MH_ALL_STREAMS_consolidated_5cat_govt_2025.csv"),
    ("KARNATAKA",     "KA_ALL_STREAMS_consolidated_5cat_govt_2024.csv"),
    ("TAMIL NADU",    "TN_engg_consolidated_5cat_govt_2025.csv"),
    ("TELANGANA",     "TG_engg_consolidated_5cat_govt_2024.csv"),
    ("ANDHRA PRADESH","AP_engg_consolidated_5cat_govt_2022.csv"),
    ("WEST BENGAL",   "WB_engg_consolidated_5cat_govt_2025.csv"),
    ("KERALA",        "KL_engg_consolidated_5cat_govt_2025.csv"),
    ("GUJARAT",       "GJ_engg_consolidated_5cat_govt_2025.csv"),
    ("BIHAR",         "BR_engg_consolidated_5cat_govt_2025.csv"),
    ("ODISHA",        "OD_engg_consolidated_5cat_govt_2024.csv"),
]

CANONICAL_COLS = [
    "state", "cet_name", "stream", "year", "round",
    "college_code", "college_name", "college_type",
    "branch_code", "branch_name",
    "quota", "category", "gender",
    "opening_rank", "closing_rank",
    "opening_mark", "closing_mark",
    "last_round_with_max",
    "rank_basis", "source_url",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    frames = []
    for state, fname in INPUTS:
        path = OUT / fname
        if not path.exists():
            print(f"  ✗ {fname} missing — skipping {state}")
            continue
        df = pd.read_csv(path, dtype={"college_code": str, "branch_code": str})
        for c in CANONICAL_COLS:
            if c not in df.columns:
                df[c] = None
        df = df[CANONICAL_COLS]
        print(f"  ✓ {state:14s} {fname:55s} rows: {len(df):>5,}  unique colleges: {df['college_code'].nunique()}")
        frames.append(df)

    if not frames:
        print("No frames to consolidate")
        return

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["state", "stream", "college_code", "branch_name",
                            "category", "gender"], na_position="last")

    out_path = OUT / "ALL_STATES_consolidated_5cat_govt.csv"
    out.to_csv(out_path, index=False)

    print()
    print(f"=== Multi-state consolidated 5-cat govt CSV ===")
    print(f"  Rows:                    {len(out):,}")
    print(f"  States:                  {sorted(out['state'].unique())}")
    print(f"  Streams (state × stream cells):")
    print(out.groupby(["state", "stream"]).size().to_string())
    print(f"  Unique state × college:  {out.groupby(['state', 'college_code']).ngroups}")
    print(f"\n→ {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
