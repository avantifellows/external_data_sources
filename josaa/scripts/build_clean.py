"""
Build the clean JoSAA fact from the raw per-(year, round) CSVs.

Reads every `josaa/raw/<year>_R<round>.csv` (the scraper output landed from
the College DB repo), unions them, normalizes column names to snake_case,
parses JoSAA's preparatory-rank encoding, types the columns, and writes a
single clean parquet to `josaa/clean/josaa_fact_cutoffs.parquet`.

This is the auditable raw→clean recipe. The parquet it produces is the
exact byte set that upload_to_gcs.py stages and load_bq.py loads — nothing
is transformed downstream.

JoSAA preparatory ranks: a rank shown with a trailing `P` (e.g. `50P`) is a
rank from the *preparatory* merit list (a separate list for certain
SC/ST/PwD candidates), NOT the main Common Rank List. Its numeric scale is
not comparable to a main-list rank. We strip the `P`, keep the integer, and
flag it so analysts never compare a prep rank against a main-list rank by
accident.

Usage:
  python3 scripts/build_clean.py                 # build from raw/, write clean/
  python3 scripts/build_clean.py --dry-run       # build in-mem, print summary, write nothing
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, COLUMN_RENAMES, RAW, TABLES

RAW_GLOB = "*_R*.csv"                          # <year>_R<round>.csv
_PREP_RE = re.compile(r"^\s*(\d+)\s*P\s*$", re.IGNORECASE)


def _parse_rank(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Split a JoSAA rank column into (integer rank, is_preparatory flag).

    '50P' -> (50, True);  '12345' -> (12345, False);  '' -> (NA, False).
    """
    s = series.astype("string").str.strip()
    is_prep = s.str.match(_PREP_RE.pattern, case=False).fillna(False)
    digits = s.str.replace(r"[Pp]\s*$", "", regex=True)
    rank = pd.to_numeric(digits, errors="coerce").round().astype("Int64")
    return rank, is_prep.astype(bool)


def build() -> pd.DataFrame:
    files = sorted(RAW.glob(RAW_GLOB))
    if not files:
        raise SystemExit(
            f"no raw CSVs matching {RAW_GLOB!r} in {RAW}. "
            "Land the JoSAA scraper output there first (see README)."
        )

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str)
        missing = set(COLUMN_RENAMES) - set(df.columns)
        if missing:
            raise SystemExit(f"{f.name}: missing expected columns {sorted(missing)}")
        frames.append(df[list(COLUMN_RENAMES)])

    raw = pd.concat(frames, ignore_index=True).rename(columns=COLUMN_RENAMES)

    out = pd.DataFrame()
    out["institute"] = raw["institute"].str.strip()
    out["academic_program_name"] = raw["academic_program_name"].str.strip()
    out["quota"] = raw["quota"].str.strip()
    out["seat_type"] = raw["seat_type"].str.strip()
    out["gender"] = raw["gender"].str.strip()
    out["opening_rank"], out["opening_is_preparatory"] = _parse_rank(raw["opening_rank"])
    out["closing_rank"], out["closing_is_preparatory"] = _parse_rank(raw["closing_rank"])
    out["year"] = pd.to_numeric(raw["year"], errors="coerce").astype("Int64")
    out["round"] = pd.to_numeric(raw["round"], errors="coerce").astype("Int64")

    out = out.drop_duplicates().reset_index(drop=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Build in-mem; write nothing")
    args = ap.parse_args()

    df = build()
    yrs = f"{int(df['year'].min())}–{int(df['year'].max())}"
    print(f"built josaa_fact_cutoffs: {len(df):,} rows, {df['year'].nunique()} years ({yrs})")
    print(f"  prep closing ranks: {int(df['closing_is_preparatory'].sum()):,}")

    if args.dry_run:
        print("  [dry-run] not writing")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    dest = TABLES[0].local_path
    df.to_parquet(dest, index=False)
    print(f"  wrote {dest}")


if __name__ == "__main__":
    main()
