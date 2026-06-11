"""
Consolidate all MH per-stream 5-cat closing-rank CSVs into one file.

This is the final MH deliverable for the parent project's per-state cutoff
methodology — one row per (state, stream, cet_name, college, branch, quota,
category, gender) with closing rank and provenance.

Streams included (all that have ≥1 govt-scope row):
  - engineering (MHT-CET PCM)
  - pharmacy    (MHT-CET PCM/PCB)
  - architecture (MAH-AAC-CET / NATA)

Streams deferred (no clean source / out of scope):
  - bdesign       (no govt institutes — all private)
  - agriculture   (MCAER doesn't publish per-college closing-rank PDFs)
  - 5-yr LL.B     (per-college dropdown UX, no batch download)
  - B.HMCT        (no clear PDF source for 2025-26)
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "extracted_data"

STREAM_FILES = [
    ("engineering",  "MH_engg_consolidated_5cat_govt_2025.csv"),
    ("pharmacy",     "MH_pharm_consolidated_5cat_govt_2025.csv"),
    ("architecture", "MH_arch_consolidated_5cat_govt_2025.csv"),
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
        # Some streams may not have all canonical columns — fill missing
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
    out = out.sort_values(["stream", "college_code", "branch_code", "quota",
                            "category", "gender"], na_position="last")

    out_path = OUT / "MH_ALL_STREAMS_consolidated_5cat_govt_2025.csv"
    out.to_csv(out_path, index=False)

    print()
    print(f"=== MH all-streams consolidated 5-cat govt CSV ===")
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
