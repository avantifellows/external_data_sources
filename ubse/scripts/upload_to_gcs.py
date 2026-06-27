#!/usr/bin/env python3
"""
Upload UBSE Grade 10 and Grade 12 data to GCS.

Uploads:
  - Raw Excel files as parquet:
      gs://avantifellows-external-data/ubse/raw/grade10/<stem>.parquet
      gs://avantifellows-external-data/ubse/raw/grade12/<stem>.parquet
  - Clean CSVs as parquet:
      gs://avantifellows-external-data/ubse/clean/ubse_fact_grade10_results.parquet
      gs://avantifellows-external-data/ubse/clean/ubse_fact_grade12_results.parquet

Run clean_grade10.py and clean_grade12.py first.

Usage:
    python3 scripts/upload_to_gcs.py                   # raw + clean for both grades
    python3 scripts/upload_to_gcs.py --raw-only
    python3 scripts/upload_to_gcs.py --clean-only
    python3 scripts/upload_to_gcs.py --grade10-only
    python3 scripts/upload_to_gcs.py --grade12-only
"""

import argparse
import io
import sys
from pathlib import Path

import pandas as pd
from google.cloud import storage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import (
    GCS_BUCKET, GRADE10_CLEAN, GRADE12_CLEAN,
    RAW_GRADE10_FILES, RAW_GRADE12_FILES,
)


def _upload(client: storage.Client, df: pd.DataFrame, gcs_path: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_file(
        buf, content_type="application/octet-stream"
    )
    print(f"  ✓ gs://{GCS_BUCKET}/{gcs_path}  ({len(df):,} rows)")


def _upload_raw(client: storage.Client, files, label: str) -> None:
    print(f"Uploading raw {label} files ...")
    for raw in files:
        if not raw.local_path.exists():
            print(f"  WARNING: {raw.local_path} not found — skipping.")
            continue
        print(f"  Reading {raw.file} ...")
        df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
        _upload(client, df, raw.gcs_path)


def _upload_clean(client: storage.Client, table, clean_script: str) -> None:
    print(f"Uploading clean {table.name} ...")
    if not table.local_path.exists():
        print(f"  ERROR: {table.local_path} not found. Run {clean_script} first.")
        sys.exit(1)
    df = pd.read_csv(table.local_path, low_memory=False, dtype=str)
    _upload(client, df, table.gcs_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--raw-only",     action="store_true")
    group.add_argument("--clean-only",   action="store_true")
    group.add_argument("--grade10-only", action="store_true")
    group.add_argument("--grade12-only", action="store_true")
    args = parser.parse_args()

    client = storage.Client()

    if args.raw_only:
        _upload_raw(client, RAW_GRADE10_FILES, "Grade 10")
        _upload_raw(client, RAW_GRADE12_FILES, "Grade 12")
    elif args.clean_only:
        _upload_clean(client, GRADE10_CLEAN, "clean_grade10.py")
        _upload_clean(client, GRADE12_CLEAN, "clean_grade12.py")
    elif args.grade10_only:
        _upload_raw(client, RAW_GRADE10_FILES, "Grade 10")
        _upload_clean(client, GRADE10_CLEAN, "clean_grade10.py")
    elif args.grade12_only:
        _upload_raw(client, RAW_GRADE12_FILES, "Grade 12")
        _upload_clean(client, GRADE12_CLEAN, "clean_grade12.py")
    else:
        _upload_raw(client, RAW_GRADE10_FILES, "Grade 10")
        _upload_raw(client, RAW_GRADE12_FILES, "Grade 12")
        _upload_clean(client, GRADE10_CLEAN, "clean_grade10.py")
        _upload_clean(client, GRADE12_CLEAN, "clean_grade12.py")

    print("\nDone.")


if __name__ == "__main__":
    main()
