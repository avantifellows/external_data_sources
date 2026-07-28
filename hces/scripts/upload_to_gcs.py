#!/usr/bin/env python3
"""
Upload HCES data to GCS.

Default (no flags) uploads both:
  - Raw:   hces/raw/HCES_Data_2023-24_Csv/*.csv   -> gs://.../hces/raw/HCES_Data_2023-24_Csv/
  - Clean: hces/clean/hces_fact_household_master.parquet -> gs://.../hces/clean/

Run transform_hces.py then add_income.py first to produce the clean parquet.
Raw is ~3.4 GB; use --clean-only for the fast path once raw is already staged.

Usage:
    python3 scripts/upload_to_gcs.py                # raw + clean
    python3 scripts/upload_to_gcs.py --clean-only
    python3 scripts/upload_to_gcs.py --raw-only
"""

import argparse
import sys

from google.cloud import storage

from sources import GCS_BUCKET, HOUSEHOLD_MASTER, RAW_LEVEL_CSVS


def _upload_file(bucket, local_path, gcs_path) -> None:
    bucket.blob(gcs_path).upload_from_filename(str(local_path))
    print(f"  ✓ gs://{GCS_BUCKET}/{gcs_path}")


def upload_clean(bucket) -> None:
    t = HOUSEHOLD_MASTER
    if not t.local_path.exists():
        sys.exit(f"  ERROR: {t.local_path} not found. Run transform_hces.py then add_income.py first.")
    print(f"Uploading clean {t.name} ...")
    _upload_file(bucket, t.local_path, t.gcs_path)


def upload_raw(bucket) -> None:
    d = RAW_LEVEL_CSVS
    if not d.local_dir.exists():
        sys.exit(f"  ERROR: {d.local_dir} not found. Stage the raw NSS CSVs there first.")
    csvs = sorted(d.local_dir.glob("*.csv"))
    print(f"Uploading {len(csvs)} raw level CSVs ...")
    for f in csvs:
        _upload_file(bucket, f, f"{d.gcs_prefix}/{f.name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--clean-only", action="store_true")
    group.add_argument("--raw-only", action="store_true")
    args = parser.parse_args()

    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)

    if args.clean_only:
        upload_clean(bucket)
    elif args.raw_only:
        upload_raw(bucket)
    else:
        upload_raw(bucket)
        upload_clean(bucket)


if __name__ == "__main__":
    main()
