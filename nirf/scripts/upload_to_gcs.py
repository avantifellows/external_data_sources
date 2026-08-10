"""
Upload the clean NIRF parquet files to GCS.

Reads each parquet listed in sources.py from nirf/clean/ — as written by
build_clean.py, already deduplicated and with BQ-friendly column names — and
uploads it byte-for-byte to the canonical GCS path. Overwrites in place; new
NIRF publications use the same filenames.

Nothing is transformed here. If a column name needs changing, change it in
build_clean.py so that clean/ == GCS == BQ stay identical.

Usage:
  python3 scripts/upload_to_gcs.py                    # upload all four
  python3 scripts/upload_to_gcs.py --table nirf_fact_rankings   # one only
  python3 scripts/upload_to_gcs.py --dry-run          # show what would happen
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, TABLES, Table


def _upload(table: Table, client, dry_run: bool) -> None:
    if not table.local_path.exists():
        raise SystemExit(
            f"missing clean parquet: {table.local_path}\n"
            f"Build it first:  python3 scripts/build_clean.py --table {table.bq_name}"
        )

    md = pq.ParquetFile(table.local_path).metadata
    msg = (f"{table.local_path.name} ({md.num_rows:,} rows, {md.num_columns} cols) "
           f"→ {table.gcs_uri}")

    if dry_run:
        print(f"  [dry-run] {msg}")
        return

    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(f"{GCS_PREFIX}/clean/{table.parquet}")
    blob.upload_from_filename(str(table.local_path), content_type="application/octet-stream")
    print(f"  uploaded {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=None, help="Upload only this BQ table name (e.g. nirf_fact_rankings)")
    ap.add_argument("--dry-run", action="store_true", help="Read + normalize locally; don't upload")
    args = ap.parse_args()

    chosen = TABLES
    if args.table:
        chosen = [t for t in TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    print(f"NIRF → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/   "
          f"({'dry-run' if args.dry_run else 'upload'})")
    for t in chosen:
        _upload(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
