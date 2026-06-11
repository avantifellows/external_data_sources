"""
Consolidate all KA per-stream 5-cat closing-rank CSVs into one file.
Mirrors consolidate_MH.py.

For multi-state consolidation across MH/KA/TN/etc., see consolidate_all.py
(which depends on this script's output and the equivalent for other states).
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "extracted_data"

STREAM_FILES = [
    ("engineering",  "KA_engg_consolidated_5cat_govt_2024.csv"),
    ("pharmacy",     "KA_pharm_consolidated_5cat_govt_2024.csv"),
    ("nursing",      "KA_bscnurs_consolidated_5cat_govt_2024.csv"),
    # agriculture and architecture intentionally omitted (no govt scope rows / no source PDF)
]

CANONICAL_COLS = [
    "state", "cet_name", "stream", "year", "round",
    "college_code", "college_name", "college_type",
    "branch_code", "branch_name",
    "quota", "category", "gender",
    "opening_rank", "closing_rank", "last_round_with_max",
    "rank_basis", "source_url",
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    frames = []
    for stream, fname in STREAM_FILES:
        path = OUT / fname
        if not path.exists():
            print(f"  ✗ {fname} missing — skipping {stream}")
            continue
        df = pd.read_csv(path, dtype={"college_code": str, "branch_code": str})
        for c in CANONICAL_COLS:
            if c not in df.columns:
                df[c] = None
        df = df[CANONICAL_COLS]
        print(f"  ✓ {stream:14s} {fname:50s} rows: {len(df):>5,}  unique colleges: {df['college_code'].nunique()}")
        frames.append(df)

    if not frames:
        print("No frames to consolidate")
        return

    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["stream", "college_code", "branch_code",
                            "category", "gender"], na_position="last")

    out_path = OUT / "KA_ALL_STREAMS_consolidated_5cat_govt_2024.csv"
    out.to_csv(out_path, index=False)

    print()
    print(f"=== KA all-streams consolidated 5-cat govt CSV (2024 proxy for 2025) ===")
    print(f"  rows:                {len(out):,}")
    print(f"  streams:             {sorted(out['stream'].unique())}")
    print(f"  unique colleges:     {out['college_code'].nunique()}")
    print(f"  unique college×branch×stream: "
          f"{out.groupby(['stream','college_code','branch_code']).ngroups:,}")
    print(f"  cells per stream:")
    print(out.groupby("stream").size().to_string())
    print(f"\n→ {out_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
