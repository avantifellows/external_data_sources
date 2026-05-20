#!/usr/bin/env python3
"""
Upload JNV JEE Mains data to GCS.

Uploads:
  - Raw: each Excel file's primary sheet → parquet
        gs://avantifellows-external-data/jnv/raw/jee_mains/<stem>.parquet
  - Clean: jee_mains_clean.csv → parquet
        gs://avantifellows-external-data/jnv/clean/jnv_fact_jee_mains_results.parquet

Run clean_jee_mains.py first to produce the clean CSV before running this.

Usage:
    python3 scripts/upload_to_gcs.py            # upload both raw and clean
    python3 scripts/upload_to_gcs.py --raw-only
    python3 scripts/upload_to_gcs.py --clean-only
"""

import argparse
import io
import sys

import pandas as pd
from google.cloud import storage

from sources import GCS_BUCKET, JEE_MAINS_CLEAN, RAW_FILES


def _upload(client, df: pd.DataFrame, gcs_path: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    bucket = client.bucket(GCS_BUCKET)
    bucket.blob(gcs_path).upload_from_file(buf, content_type="application/octet-stream")
    print(f"  ✓ gs://{GCS_BUCKET}/{gcs_path}  ({len(df):,} rows)")


def upload_raw(client: storage.Client) -> None:
    print("Uploading raw files ...")
    for raw in RAW_FILES:
        print(f"  Reading {raw.file} ...")
        df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
        _upload(client, df, raw.gcs_path)


def upload_clean(client: storage.Client) -> None:
    print("Uploading clean file ...")
    if not JEE_MAINS_CLEAN.local_path.exists():
        print(f"  ERROR: {JEE_MAINS_CLEAN.local_path} not found.")
        print("  Run clean_jee_mains.py first.")
        sys.exit(1)
    df = pd.read_csv(JEE_MAINS_CLEAN.local_path, dtype=str, low_memory=False)
    _upload(client, df, JEE_MAINS_CLEAN.gcs_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--raw-only",   action="store_true")
    group.add_argument("--clean-only", action="store_true")
    args = parser.parse_args()

    client = storage.Client()

    if args.raw_only:
        upload_raw(client)
    elif args.clean_only:
        upload_clean(client)
    else:
        upload_raw(client)
        upload_clean(client)

    print("\nDone.")


if __name__ == "__main__":
    main()
