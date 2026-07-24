#!/usr/bin/env python3
"""
Upload all JNV data to GCS.

Default (no flags) uploads all six pipelines — raw Excel as parquet + clean CSV as parquet.

Uploads:
  - Raw mains:         jnv/raw/jee_mains/<stem>.parquet
  - Raw advanced:      jnv/raw/jee_advanced/<stem>.parquet
  - Raw NEET:          jnv/raw/neet/<stem>.parquet
  - Raw JNVST:         jnv/raw/jnvst/<stem>.parquet
  - Raw EI Asset Test: jnv/raw/ei_asset_test/<stem>.parquet
  - Raw 10th board:    jnv/raw/board_results_10th/<stem>.parquet
  - Raw 12th board:    jnv/raw/board_results_12th/<stem>.parquet
  - Clean JEE:         jnv/clean/jnv_fact_jee_results.parquet
  - Clean NEET:        jnv/clean/jnv_fact_neet_results.parquet
  - Clean JNVST:       jnv/clean/jnv_fact_selection_test_results.parquet
  - Clean EI Asset:    jnv/clean/jnv_fact_ei_asset_test_results.parquet
  - Clean 10th board:  jnv/clean/jnv_fact_board_results_10th.parquet
  - Clean 12th board:  jnv/clean/jnv_fact_board_results_12th.parquet
  - Mapping files:     jnv/mapping_files/<name>.xlsx  (as-is, no parquet conversion)

The mapping files (Poojita 12th&10th, All Years JNV 10th Score) are multi-sheet
crosswalks read directly by build_student_outcome_mapping.py. They are not in
the pipeline lists and are gitignored, so GCS is their only backup — uploaded
verbatim because the build reads several named sheets from each. They are NOT
part of the default or --raw-only run; upload them explicitly with
--mapping-files (they change rarely).

Run all clean scripts first to produce the clean CSVs before uploading.

Usage:
    python3 scripts/upload_to_gcs.py                         # all raw + clean
    python3 scripts/upload_to_gcs.py --raw-only              # all raw files
    python3 scripts/upload_to_gcs.py --clean-only            # all clean files
    python3 scripts/upload_to_gcs.py --jee-only
    python3 scripts/upload_to_gcs.py --neet-only
    python3 scripts/upload_to_gcs.py --jnvst-only
    python3 scripts/upload_to_gcs.py --ei-asset-test-only
    python3 scripts/upload_to_gcs.py --board-results-10th-only
    python3 scripts/upload_to_gcs.py --board-results-12th-only
    python3 scripts/upload_to_gcs.py --mapping-files         # crosswalk Excel files, as-is
"""

import argparse
import io
import sys

import sys
from pathlib import Path

import pandas as pd
from google.cloud import storage

from sources import BOARD_RESULTS_10TH_CLEAN, BOARD_RESULTS_10TH_RAW_BY_YEAR, BOARD_RESULTS_12TH_CLEAN, EI_ASSET_TEST_CLEAN, GCS_BUCKET, JEE_CLEAN, JNVST_CLEAN, MAPPING_FILES, NEET_CLEAN, RAW_ADV_FILES, RAW_BOARD_RESULTS_10TH_FILES, RAW_BOARD_RESULTS_12TH_FILES, RAW_EI_ASSET_TEST_FILES, RAW_JNVST_FILES, RAW_MAINS_FILES, RAW_NEET_FILES, board_results_10th_clean_for_year

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


def _upload_mapping_files(client: storage.Client, files) -> None:
    """Upload identity-crosswalk Excel files verbatim (no parquet conversion).

    These are multi-sheet workbooks read directly by
    build_student_outcome_mapping.py, so they must be preserved as-is.
    """
    print("Uploading mapping files (as-is, no conversion) ...")
    bucket = client.bucket(GCS_BUCKET)
    for m in files:
        if not m.local_path.exists():
            print(f"  ERROR: {m.local_path} not found.")
            sys.exit(1)
        print(f"  Reading {m.local_path.name} ...")
        bucket.blob(m.gcs_path).upload_from_filename(
            str(m.local_path),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        size_mb = m.local_path.stat().st_size / 1e6
        print(f"  ✓ gs://{GCS_BUCKET}/{m.gcs_path}  ({size_mb:.1f} MB)")


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
    group.add_argument("--raw-only",   action="store_true", help="Upload all raw files")
    group.add_argument("--clean-only", action="store_true", help="Upload all clean files")
    group.add_argument("--jee-only",   action="store_true", help="Upload JEE raw + clean")
    group.add_argument("--neet-only",  action="store_true", help="Upload NEET raw + clean")
    group.add_argument("--jnvst-only",         action="store_true", help="Upload JNVST raw + clean")
    group.add_argument("--ei-asset-test-only",       action="store_true", help="Upload EI Asset Test raw + clean")
    group.add_argument("--board-results-10th-only",  action="store_true", help="Upload 10th board results raw + clean")
    group.add_argument("--board-results-12th-only",  action="store_true", help="Upload 12th board results raw + clean")
    group.add_argument("--mapping-files",  action="store_true", help="Upload identity-crosswalk Excel files as-is (Poojita, All Years JNV 10th Score)")
    parser.add_argument("--year", type=int, default=None,
                        help="With --board-results-10th-only: upload only this exam year's "
                             "raw + per-year clean parquet (for the incremental append load).")
    args = parser.parse_args()

    if args.year is not None and not args.board_results_10th_only:
        parser.error("--year is only supported with --board-results-10th-only")

    client = storage.Client()

    if args.raw_only:
        _upload_raw_files(client, RAW_MAINS_FILES, "mains")
        _upload_raw_files(client, RAW_ADV_FILES, "advanced")
        _upload_raw_files(client, RAW_NEET_FILES, "NEET")
        _upload_raw_files(client, RAW_JNVST_FILES, "JNVST")
        _upload_raw_files(client, RAW_EI_ASSET_TEST_FILES, "EI Asset Test")
        _upload_raw_files(client, RAW_BOARD_RESULTS_10TH_FILES, "10th board results")
        _upload_raw_files(client, RAW_BOARD_RESULTS_12TH_FILES, "12th board results")
    elif args.clean_only:
        _upload_clean_table(client, JEE_CLEAN,               apply_dtypes_jee,            "clean_jee.py")
        _upload_clean_table(client, NEET_CLEAN,              apply_dtypes_neet,           "clean_neet.py")
        _upload_clean_table(client, JNVST_CLEAN,             apply_dtypes_jnvst,          "clean_jnvst.py")
        _upload_clean_table(client, EI_ASSET_TEST_CLEAN,     apply_dtypes_ei_asset_test,  "clean_ei_asset_test.py")
        _upload_clean_table(client, BOARD_RESULTS_10TH_CLEAN, None,                       "clean_board_results_10th.py")
        _upload_clean_table(client, BOARD_RESULTS_12TH_CLEAN, None,                       "clean_board_results_12th.py")
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
    elif args.board_results_10th_only:
        if args.year is not None:
            raw = BOARD_RESULTS_10TH_RAW_BY_YEAR.get(args.year)
            if raw is None:
                print(f"  ERROR: no raw 10th-board file registered for year {args.year}.")
                sys.exit(1)
            _upload_raw_files(client, [raw], f"10th board results {args.year}")
            _upload_clean_table(client, board_results_10th_clean_for_year(args.year), None,
                                f"clean_board_results_10th.py --year {args.year}")
        else:
            _upload_raw_files(client, RAW_BOARD_RESULTS_10TH_FILES, "10th board results")
            _upload_clean_table(client, BOARD_RESULTS_10TH_CLEAN, None, "clean_board_results_10th.py")
    elif args.board_results_12th_only:
        _upload_raw_files(client, RAW_BOARD_RESULTS_12TH_FILES, "12th board results")
        _upload_clean_table(client, BOARD_RESULTS_12TH_CLEAN, None, "clean_board_results_12th.py")
    elif args.mapping_files:
        _upload_mapping_files(client, MAPPING_FILES)
    else:
        _upload_raw_files(client, RAW_MAINS_FILES, "mains")
        _upload_raw_files(client, RAW_ADV_FILES, "advanced")
        _upload_raw_files(client, RAW_NEET_FILES, "NEET")
        _upload_raw_files(client, RAW_JNVST_FILES, "JNVST")
        _upload_raw_files(client, RAW_EI_ASSET_TEST_FILES, "EI Asset Test")
        _upload_raw_files(client, RAW_BOARD_RESULTS_10TH_FILES, "10th board results")
        _upload_raw_files(client, RAW_BOARD_RESULTS_12TH_FILES, "12th board results")
        _upload_clean_table(client, JEE_CLEAN,               apply_dtypes_jee,            "clean_jee.py")
        _upload_clean_table(client, NEET_CLEAN,              apply_dtypes_neet,           "clean_neet.py")
        _upload_clean_table(client, JNVST_CLEAN,             apply_dtypes_jnvst,          "clean_jnvst.py")
        _upload_clean_table(client, EI_ASSET_TEST_CLEAN,     apply_dtypes_ei_asset_test,  "clean_ei_asset_test.py")
        _upload_clean_table(client, BOARD_RESULTS_10TH_CLEAN, None,                       "clean_board_results_10th.py")
        _upload_clean_table(client, BOARD_RESULTS_12TH_CLEAN, None,                       "clean_board_results_12th.py")

    print("\nDone.")


if __name__ == "__main__":
    main()
