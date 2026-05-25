#!/usr/bin/env python3
"""
Upload JNV JEE and NEET data to GCS.

Uploads:
  - Raw mains:    each JEE Mains Excel → parquet
        gs://avantifellows-external-data/jnv/raw/jee_mains/<stem>.parquet
  - Raw advanced: each JEE Advanced Excel → parquet
        gs://avantifellows-external-data/jnv/raw/jee_advanced/<stem>.parquet
  - Raw NEET:     each NEET Excel → parquet
        gs://avantifellows-external-data/jnv/raw/neet/<stem>.parquet
  - Clean JEE:    jee_clean.csv → parquet
        gs://avantifellows-external-data/jnv/clean/jnv_fact_jee_results.parquet
  - Clean NEET:   neet_clean.csv → parquet
        gs://avantifellows-external-data/jnv/clean/jnv_fact_neet_results.parquet

Run clean_jee.py / clean_neet.py first to produce the clean CSVs.

Usage:
    python3 scripts/upload_to_gcs.py                    # upload all raw and clean
    python3 scripts/upload_to_gcs.py --raw-only
    python3 scripts/upload_to_gcs.py --clean-only
    python3 scripts/upload_to_gcs.py --jee-only         # JEE raw + clean
    python3 scripts/upload_to_gcs.py --neet-only        # NEET raw + clean
"""

import argparse
import io
import sys

import sys
from pathlib import Path

import pandas as pd
from google.cloud import storage

from sources import EI_ASSET_TEST_CLEAN, GCS_BUCKET, JEE_CLEAN, JNVST_CLEAN, NEET_CLEAN, RAW_ADV_FILES, RAW_EI_ASSET_TEST_FILES, RAW_JNVST_FILES, RAW_MAINS_FILES, RAW_NEET_FILES

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from codemaps.ei_asset_test.shared import apply_dtypes as apply_dtypes_ei_asset_test
from codemaps.jnvst.shared import apply_dtypes as apply_dtypes_jnvst
from codemaps.mains.shared import apply_dtypes as apply_dtypes_jee
from codemaps.neet.shared import apply_dtypes as apply_dtypes_neet


def _upload(client, df: pd.DataFrame, gcs_path: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    bucket = client.bucket(GCS_BUCKET)
    bucket.blob(gcs_path).upload_from_file(buf, content_type="application/octet-stream")
    print(f"  ✓ gs://{GCS_BUCKET}/{gcs_path}  ({len(df):,} rows)")


def _upload_raw_files(client: storage.Client, files, label: str) -> None:
    print(f"Uploading raw {label} files ...")
    for raw in files:
        print(f"  Reading {raw.file} ...")
        df = pd.read_excel(raw.local_path, sheet_name=raw.sheet, dtype=str)
        _upload(client, df, raw.gcs_path)


def _upload_clean_table(client: storage.Client, table, apply_dtypes=None, clean_script: str = "") -> None:
    print(f"Uploading clean {table.name} ...")
    if not table.local_path.exists():
        print(f"  ERROR: {table.local_path} not found. Run {clean_script or 'the clean script'} first.")
        sys.exit(1)
    df = pd.read_csv(table.local_path, low_memory=False, dtype=None if apply_dtypes else str)
    if apply_dtypes:
        df = apply_dtypes(df)
    _upload(client, df, table.gcs_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--raw-only",   action="store_true", help="Upload raw files only (JEE + NEET)")
    group.add_argument("--clean-only", action="store_true", help="Upload clean files only (JEE + NEET)")
    group.add_argument("--jee-only",   action="store_true", help="Upload JEE raw + clean")
    group.add_argument("--neet-only",  action="store_true", help="Upload NEET raw + clean")
    group.add_argument("--jnvst-only",         action="store_true", help="Upload JNVST raw + clean")
    group.add_argument("--ei-asset-test-only", action="store_true", help="Upload EI Asset Test raw + clean")
    args = parser.parse_args()

    client = storage.Client()

    if args.raw_only:
        _upload_raw_files(client, RAW_MAINS_FILES, "mains")
        _upload_raw_files(client, RAW_ADV_FILES, "advanced")
        _upload_raw_files(client, RAW_NEET_FILES, "NEET")
    elif args.clean_only:
        _upload_clean_table(client, JEE_CLEAN,   apply_dtypes_jee,  "clean_jee.py")
        _upload_clean_table(client, NEET_CLEAN,  apply_dtypes_neet, "clean_neet.py")
    elif args.jee_only:
        _upload_raw_files(client, RAW_MAINS_FILES, "mains")
        _upload_raw_files(client, RAW_ADV_FILES, "advanced")
        _upload_clean_table(client, JEE_CLEAN,  apply_dtypes_jee, "clean_jee.py")
    elif args.neet_only:
        _upload_raw_files(client, RAW_NEET_FILES, "NEET")
        _upload_clean_table(client, NEET_CLEAN, apply_dtypes_neet, "clean_neet.py")
    elif args.jnvst_only:
        _upload_raw_files(client, RAW_JNVST_FILES, "JNVST")
        _upload_clean_table(client, JNVST_CLEAN, apply_dtypes_jnvst, "clean_jnvst.py")
    elif args.ei_asset_test_only:
        _upload_raw_files(client, RAW_EI_ASSET_TEST_FILES, "EI Asset Test")
        _upload_clean_table(client, EI_ASSET_TEST_CLEAN, apply_dtypes_ei_asset_test, "clean_ei_asset_test.py")
    else:
        _upload_raw_files(client, RAW_MAINS_FILES, "mains")
        _upload_raw_files(client, RAW_ADV_FILES, "advanced")
        _upload_raw_files(client, RAW_NEET_FILES, "NEET")
        _upload_clean_table(client, JEE_CLEAN,  apply_dtypes_jee,  "clean_jee.py")
        _upload_clean_table(client, NEET_CLEAN, apply_dtypes_neet, "clean_neet.py")

    print("\nDone.")


if __name__ == "__main__":
    main()
