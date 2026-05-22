#!/usr/bin/env python3
"""
Stage PLFS to GCS: raw microdata + the joined year-on-year parquet tables.

PLFS is the heavy-parse source — raw is gated behind microdata.gov.in (login),
so there is no fetch.py; the raw copy on GCS is the regenerable source of record.
This stages two things under gs://avantifellows-external-data/plfs/:

  raw/    ← the per-release unit-level microdata (rsync of the local raw/ tree)
  clean/  ← the 6 joined tables as parquet (produced by `load_bq.py --dry-run`,
            which unions all 11 releases): persons, households, releases,
            dim_nco, dim_nic, dim_geo. Uploaded with source-prefixed names so
            they map 1:1 to the eventual BQ tables (plfs_fact_*, plfs_dim_*).

BQ load is deliberately deferred (post-approval) — this only stages to GCS.

Bulk uploads use gsutil (-m parallel rsync/cp); raw is several GB.

Usage:
  python3 scripts/upload_to_gcs.py --raw-dir <dir> --parquet-dir <dir>
  python3 scripts/upload_to_gcs.py --clean-only           # just the parquets
  python3 scripts/upload_to_gcs.py --raw-only             # just the raw tree
  python3 scripts/upload_to_gcs.py --dry-run              # print gsutil commands
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PLFS_DIR = Path(__file__).resolve().parent.parent

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "plfs"

# Parquet stem (as written by load_bq.py --dry-run) → GCS / future-BQ name.
PARQUET_RENAME = {
    "plfs_fact_persons": "plfs_fact_persons",
    "plfs_fact_households": "plfs_fact_households",
    "plfs_releases": "plfs_releases",
    "plfs_dim_nco": "plfs_dim_nco",
    "plfs_dim_nic": "plfs_dim_nic",
    "plfs_dim_geo": "plfs_dim_geo",
}


def _run(cmd: list[str], dry_run: bool) -> None:
    print(("  [dry-run] " if dry_run else "  $ ") + " ".join(cmd))
    if not dry_run:
        subprocess.run(cmd, check=True)


def upload_raw(raw_dir: Path, dry_run: bool) -> None:
    if not raw_dir.is_dir():
        raise SystemExit(f"raw dir not found: {raw_dir}")
    dst = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/raw"
    print(f"Raw → {dst}  (rsync of {raw_dir})")
    _run(["gsutil", "-m", "rsync", "-r", str(raw_dir), dst], dry_run)


def upload_clean(parquet_dir: Path, dry_run: bool) -> None:
    if not parquet_dir.is_dir():
        raise SystemExit(
            f"parquet dir not found: {parquet_dir}\n"
            f"Run `python3 scripts/load_bq.py --dry-run` first (writes to /tmp/plfs_bq)."
        )
    dst = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean"
    print(f"Clean parquet → {dst}/")
    for stem, bq_name in PARQUET_RENAME.items():
        src = parquet_dir / f"{stem}.parquet"
        if not src.exists():
            print(f"  • {src.name} not found, skipping")
            continue
        size_mb = src.stat().st_size / 1e6
        print(f"    {stem}.parquet ({size_mb:,.1f} MB) → {bq_name}.parquet")
        _run(["gsutil", "-m", "cp", str(src), f"{dst}/{bq_name}.parquet"], dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", default=str(PLFS_DIR / "raw"),
                    help="Local raw/ tree to stage (default: plfs/raw)")
    ap.add_argument("--parquet-dir", default="/tmp/plfs_bq",
                    help="Dir holding the joined parquets from load_bq.py --dry-run (default: /tmp/plfs_bq)")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--raw-only", action="store_true")
    group.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Print gsutil commands; don't upload")
    args = ap.parse_args()

    if not args.clean_only:
        upload_raw(Path(args.raw_dir), args.dry_run)
    if not args.raw_only:
        upload_clean(Path(args.parquet_dir), args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
