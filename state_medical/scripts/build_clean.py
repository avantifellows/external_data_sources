"""
Build the clean state-medical fact from the national harmonized CSV.

Reads state_medical/raw/national_closing_ranks_unified_AIR_2025.csv (College DB
output) and projects it to the NEUTRAL published fact:

  KEPT  : state, college, program, category (canonical), category_raw,
          round, closing_rank (native), rank_space (derived), conversion_method
          (native-scale provenance), is_estimated, source_quality, year
  DROPPED (Avanti modeling — stays in College DB):
          air_unified, neet_score_implied, tier, multiplier_applied,
          estimated_R3_closing_rank, confidence

`rank_space` is derived from conversion_method: 'NEET AIR' when the state
reports a native All-India Rank, else 'state-native' (a state merit
rank/score on that state's own scale — NOT comparable across states without
the AIR conversion, which lives in College DB).

Usage:
  python3 scripts/build_clean.py                 # build from raw/, write clean/
  python3 scripts/build_clean.py --dry-run       # build in-mem, summary only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, CYCLE_YEAR, RAW, RAW_FILE, TABLES


def _rank_space(conversion_method: pd.Series) -> pd.Series:
    cm = conversion_method.astype("string").str.strip()
    return pd.Series(
        ["NEET AIR" if c == "native AIR" else "state-native" for c in cm.fillna("")],
        dtype="string",
    )


def build() -> pd.DataFrame:
    src = RAW / RAW_FILE
    if not src.exists():
        raise SystemExit(
            f"missing {src}. Land the College DB output there first "
            "(medical-state-counselling/extracted_data/national_closing_ranks_unified_AIR_2025.csv)."
        )

    raw = pd.read_csv(src, dtype=str)
    out = pd.DataFrame()
    out["state"] = raw["state"].astype("string").str.strip()
    out["college"] = raw["college"].astype("string").str.replace(r"\s*\n\s*", " ", regex=True).str.strip()
    out["program"] = raw["program_norm"].astype("string").str.strip()
    out["category"] = raw["category_canonical"].astype("string").str.strip().replace("", pd.NA)
    out["category_raw"] = raw["category_raw"].astype("string").str.strip().replace("", pd.NA)
    out["round"] = raw["actual_round"].astype("string").str.strip().replace("", pd.NA)
    out["closing_rank"] = pd.to_numeric(raw["actual_closing_rank"], errors="coerce").round().astype("Int64")
    out["rank_space"] = _rank_space(raw["conversion_method"])
    out["conversion_method"] = raw["conversion_method"].astype("string").str.strip()
    out["is_estimated"] = (raw["is_estimated"].astype("string").str.strip().str.lower() == "true")
    out["source_quality"] = raw["source_quality"].astype("string").str.strip()
    out["year"] = pd.array([CYCLE_YEAR] * len(out), dtype="Int64")

    out = out.drop_duplicates().reset_index(drop=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Build in-mem; write nothing")
    args = ap.parse_args()

    df = build()
    air = int((df["rank_space"] == "NEET AIR").sum())
    print(
        f"built state_medical_fact_closing_ranks: {len(df):,} rows, "
        f"{df['state'].nunique()} states, {air:,} native-AIR rows, "
        f"{int(df['is_estimated'].sum()):,} estimated, "
        f"third-party {int((df['source_quality'] == 'third-party').sum()):,}"
    )

    if args.dry_run:
        print("  [dry-run] not writing")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    dest = TABLES[0].local_path
    df.to_parquet(dest, index=False)
    print(f"  wrote {dest}")


if __name__ == "__main__":
    main()
