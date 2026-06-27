#!/usr/bin/env python3
"""
Upload pb_scert merit list data to GCS.

Uploads:
  - Raw Excel as parquet:
      gs://avantifellows-external-data/pb_scert/raw/<stem>.parquet
  - Clean CSV as parquet:
      gs://avantifellows-external-data/pb_scert/clean/pb_scert_fact_soe_rsms_admission_merit_list.parquet

Run clean_merit_list.py first.

Usage:
    python3 scripts/upload_to_gcs.py             # raw + clean
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
from scripts.sources import GCS_BUCKET, MERIT_LIST_CLEAN, RAW_MERIT_LIST_FILES


def _upload(client: storage.Client, df: pd.DataFrame, gcs_path: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_file(
        buf, content_type="application/octet-stream"
    )
    print(f"  ✓ gs://{GCS_BUCKET}/{gcs_path}  ({len(df):,} rows)")


def _upload_raw(client: storage.Client) -> None:
    print("Uploading raw files ...")
    for raw in RAW_MERIT_LIST_FILES:
        if not raw.local_path.exists():
            print(f"  WARNING: {raw.local_path} not found — skipping.")
            continue
        print(f"  Reading {raw.file} ...")
        df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
        _upload(client, df, raw.gcs_path)


def _upload_clean(client: storage.Client) -> None:
    print(f"Uploading clean {MERIT_LIST_CLEAN.name} ...")
    if not MERIT_LIST_CLEAN.local_path.exists():
        print(f"  ERROR: {MERIT_LIST_CLEAN.local_path} not found. Run clean_merit_list.py first.")
        sys.exit(1)
    df = pd.read_csv(MERIT_LIST_CLEAN.local_path, low_memory=False, dtype=str)
    _upload(client, df, MERIT_LIST_CLEAN.gcs_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--raw-only",   action="store_true")
    group.add_argument("--clean-only", action="store_true")
    args = parser.parse_args()

    client = storage.Client()

    if args.raw_only:
        _upload_raw(client)
    elif args.clean_only:
        _upload_clean(client)
    else:
        _upload_raw(client)
        _upload_clean(client)

    print("\nDone.")


if __name__ == "__main__":
    main()
