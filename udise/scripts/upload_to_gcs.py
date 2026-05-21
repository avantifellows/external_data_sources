#!/usr/bin/env python3
"""
Upload UDISE+ data to GCS.

  - Raw:   the dashboard-export xlsx, as-is (it IS the raw artifact)
           gs://avantifellows-external-data/udise/raw/<xlsx>   (traceability)
  - Clean: the parsed long-form fact → parquet
           gs://avantifellows-external-data/udise/clean/enrolment.parquet

Run clean_udise.py first to produce clean/enrolment.parquet.

Usage:
  python3 scripts/upload_to_gcs.py                 # raw + clean
  python3 scripts/upload_to_gcs.py --raw-only / --clean-only / --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, SOURCE_XLSX, TABLES


def _cp(client, local: Path, gcs_path: str, content_type: str, dry_run: bool) -> None:
    size_mb = local.stat().st_size / 1e6
    msg = f"{local.name} ({size_mb:.2f} MB) → gs://{GCS_BUCKET}/{gcs_path}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_filename(str(local), content_type=content_type)
    print(f"  ✓ {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--raw-only", action="store_true")
    group.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    if not args.clean_only:
        if not SOURCE_XLSX.exists():
            raise SystemExit(f"missing raw xlsx: {SOURCE_XLSX}")
        print(f"Raw → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/")
        _cp(client, SOURCE_XLSX, f"{GCS_PREFIX}/raw/{SOURCE_XLSX.name}",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", args.dry_run)

    if not args.raw_only:
        print(f"Clean → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/")
        for t in TABLES:
            if not t.local_path.exists():
                raise SystemExit(f"missing parquet: {t.local_path}\nRun scripts/clean_udise.py first.")
            _cp(client, t.local_path, t.gcs_path, "application/octet-stream", args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
