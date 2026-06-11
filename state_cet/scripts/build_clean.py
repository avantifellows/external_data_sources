"""
Build the clean state-CET fact from the consolidated all-states CSV.

Reads state_cet/raw/ALL_STATES_consolidated_5cat_govt.csv (produced by the
College DB state-cet-scrape pipeline), types the rank/mark columns, tidies
embedded newlines in college_name, and writes a single clean parquet to
state_cet/clean/state_cet_fact_closing_ranks.parquet.

This is the auditable raw→clean recipe; the parquet it writes is exactly what
upload_to_gcs.py stages and load_bq.py loads.

NOTE on provenance: the consolidated CSV is already curated upstream —
filtered to government colleges, categories harmonized to Avanti's 5-cat
space (GEN/EWS/OBC-NCL/SC/ST), and closing rank taken as the last/MAX round.
This source ships that analyst-ready product as-is (it does NOT re-derive
from per-state raw). The harmonization + govt-scope are documented in the
schema so the curation is explicit, not hidden.

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
from sources import CLEAN, RAW, RAW_FILE, TABLES

INT_COLS = ["year", "opening_rank", "closing_rank"]
FLOAT_COLS = ["opening_mark", "closing_mark"]
STR_COLS = [
    "state", "cet_name", "stream", "round", "college_code", "college_name",
    "college_type", "branch_code", "branch_name", "quota", "category",
    "gender", "last_round_with_max", "rank_basis", "source_url",
]


def build() -> pd.DataFrame:
    src = RAW / RAW_FILE
    if not src.exists():
        raise SystemExit(
            f"missing {src}. Land the College DB consolidated file there first "
            "(state-cet-scrape/extracted_data/ALL_STATES_consolidated_5cat_govt.csv)."
        )

    raw = pd.read_csv(src, dtype=str)
    out = pd.DataFrame()

    for c in STR_COLS:
        out[c] = raw[c].astype("string").str.strip() if c in raw else pd.NA
    # college_name carries embedded newlines from PDF extraction — flatten.
    out["college_name"] = out["college_name"].str.replace(r"\s*\n\s*", " ", regex=True)

    for c in INT_COLS:
        out[c] = pd.to_numeric(raw.get(c), errors="coerce").astype("Int64")
    for c in FLOAT_COLS:
        out[c] = pd.to_numeric(raw.get(c), errors="coerce").astype("Float64")

    # column order: keys, ranks/marks, provenance
    ordered = [
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name", "quota", "category", "gender",
        "opening_rank", "closing_rank", "opening_mark", "closing_mark",
        "last_round_with_max", "rank_basis", "source_url",
    ]
    out = out[ordered].drop_duplicates().reset_index(drop=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Build in-mem; write nothing")
    args = ap.parse_args()

    df = build()
    print(
        f"built state_cet_fact_closing_ranks: {len(df):,} rows, "
        f"{df['state'].nunique()} states, {df['cet_name'].nunique()} CETs, "
        f"years {sorted(df['year'].dropna().unique().tolist())}"
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
