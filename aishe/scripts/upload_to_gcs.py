#!/usr/bin/env python3
"""
Upload AISHE data to GCS.

Uploads (mirrors the jnv/ convention):
  - Raw:   each source sheet the parser consumes → parquet
           gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet
           (faithful cell-grid dump, header=None — for traceability only;
            not loaded to BQ)
  - Clean: each parsed table → parquet
           gs://avantifellows-external-data/aishe/clean/<table>.parquet
           (these are what load_bq.py loads)

Run clean_aishe.py first to produce clean/*.parquet before uploading clean.

Usage:
  python3 scripts/upload_to_gcs.py                 # upload raw + clean
  python3 scripts/upload_to_gcs.py --raw-only
  python3 scripts/upload_to_gcs.py --clean-only
  python3 scripts/upload_to_gcs.py --dry-run       # show plan only
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, RAW_SHEETS, TABLES, RawSheet, Table


def _resolve_sheet(rs: RawSheet) -> str:
    """Find the actual sheet name (AISHE sheet names vary by trailing space)."""
    if not rs.workbook.exists():
        raise SystemExit(f"missing raw workbook: {rs.workbook}")
    want = rs.stem
    for name in pd.ExcelFile(rs.workbook).sheet_names:
        if name.replace(" ", "").lower() == want:
            return name
    raise SystemExit(f"sheet {rs.sheet!r} not found in {rs.workbook.name}")


def upload_raw(client, dry_run: bool) -> None:
    print("Raw → gs://{}/aishe/raw/ ...".format(GCS_BUCKET))
    for rs in RAW_SHEETS:
        actual = _resolve_sheet(rs)
        df = pd.read_excel(rs.workbook, sheet_name=actual, header=None, dtype=str)
        msg = f"{rs.year}/{actual} ({len(df):,}x{len(df.columns)}) → {rs.gcs_uri}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        client.bucket(GCS_BUCKET).blob(rs.gcs_path).upload_from_file(
            buf, content_type="application/octet-stream"
        )
        print(f"  ✓ {msg}")


def upload_clean(client, dry_run: bool) -> None:
    print("Clean → gs://{}/aishe/clean/ ...".format(GCS_BUCKET))
    for t in TABLES:
        if not t.local_path.exists():
            raise SystemExit(f"missing local parquet: {t.local_path}\nRun scripts/clean_aishe.py first.")
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
    group.add_argument("--raw-only", action="store_true", help="Upload only the raw sheets")
    group.add_argument("--clean-only", action="store_true", help="Upload only the clean tables")
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
