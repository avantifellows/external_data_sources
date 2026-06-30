#!/usr/bin/env python3
"""
Upload NMC seat-matrix data to GCS.

Uploads (mirrors the board_results/ convention):
  - Raw:   the source NMC seat-matrix PDF, as-is (it IS the raw artifact)
           gs://avantifellows-external-data/nmc/raw/<pdf>
           (traceability only; not loaded to BQ)
  - Clean: the parsed table → parquet
           gs://avantifellows-external-data/nmc/clean/mbbs_seats.parquet
           (this is what load_bq.py loads)

Run clean_nmc.py first to produce clean/mbbs_seats.parquet.

Usage:
  python3 scripts/upload_to_gcs.py                 # raw + clean
  python3 scripts/upload_to_gcs.py --raw-only
  python3 scripts/upload_to_gcs.py --clean-only
  python3 scripts/upload_to_gcs.py --dry-run       # show plan only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, RAW_FILES, TABLES


def upload_raw(client, dry_run: bool) -> None:
    print(f"Raw → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/ ...")
    for rf in RAW_FILES:
        if not rf.local_path.exists():
            raise SystemExit(f"missing raw PDF: {rf.local_path}")
        size_mb = rf.local_path.stat().st_size / 1e6
        msg = f"{rf.local_path.name} ({size_mb:.1f} MB) → {rf.gcs_uri}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        client.bucket(GCS_BUCKET).blob(rf.gcs_path).upload_from_filename(
            str(rf.local_path), content_type="application/pdf"
        )
        print(f"  ✓ {msg}")


def upload_clean(client, dry_run: bool) -> None:
    print(f"Clean → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/ ...")
    for t in TABLES:
        if not t.local_path.exists():
            raise SystemExit(f"missing local parquet: {t.local_path}\nRun clean_nmc.py first.")
        size_mb = t.local_path.stat().st_size / 1e6
        msg = f"{t.parquet} ({size_mb:.2f} MB) → {t.gcs_uri}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        client.bucket(GCS_BUCKET).blob(t.gcs_path).upload_from_filename(
            str(t.local_path), content_type="application/octet-stream"
        )
        print(f"  ✓ {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--raw-only", action="store_true", help="Upload only the raw PDF")
    group.add_argument("--clean-only", action="store_true", help="Upload only the clean table")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't upload")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    if args.raw_only:
        upload_raw(client, args.dry_run)
    elif args.clean_only:
        upload_clean(client, args.dry_run)
    else:
        upload_raw(client, args.dry_run)
        upload_clean(client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
