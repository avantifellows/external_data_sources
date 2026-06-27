#!/usr/bin/env python3
"""
Upload Dakshana NCST data to GCS.

Uploads:
  - Raw NCST:   each NCST Excel → parquet
        gs://avantifellows-external-data/dakshana/raw/ncst/<stem>.parquet
  - Clean NCST: ncst_clean.csv → parquet
        gs://avantifellows-external-data/dakshana/clean/dakshana_fact_ncst_results.parquet

Run clean_ncst.py first to produce the clean CSV.

Usage:
    python3 scripts/upload_to_gcs.py              # upload raw + clean
    python3 scripts/upload_to_gcs.py --raw-only
    python3 scripts/upload_to_gcs.py --clean-only
"""

import argparse
import io
import sys
from pathlib import Path

import pandas as pd
from google.cloud import storage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codemaps.ncst.shared import apply_dtypes
from scripts.sources import GCS_BUCKET, NCST_CLEAN, RAW_NCST_FILES


def _upload(client: storage.Client, df: pd.DataFrame, gcs_path: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    bucket = client.bucket(GCS_BUCKET)
    bucket.blob(gcs_path).upload_from_file(buf, content_type="application/octet-stream")
    print(f"  ✓ gs://{GCS_BUCKET}/{gcs_path}  ({len(df):,} rows)")


def upload_raw(client: storage.Client) -> None:
    print("Uploading raw NCST files ...")
    for raw in RAW_NCST_FILES:
        if not raw.local_path.exists():
            print(f"  WARNING: {raw.local_path} not found — skipping.")
            continue
        print(f"  Reading {raw.file} ...")
        df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
        _upload(client, df, raw.gcs_path)


def upload_clean(client: storage.Client) -> None:
    print(f"Uploading clean {NCST_CLEAN.name} ...")
    if not NCST_CLEAN.local_path.exists():
        print(f"  ERROR: {NCST_CLEAN.local_path} not found. Run clean_ncst.py first.")
        sys.exit(1)
    df = apply_dtypes(pd.read_csv(NCST_CLEAN.local_path, low_memory=False))
    _upload(client, df, NCST_CLEAN.gcs_path)


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