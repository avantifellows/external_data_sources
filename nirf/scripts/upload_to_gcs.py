"""
Upload local NIRF parquet files to GCS.

Reads each parquet listed in sources.py from nirf/raw/, applies any
column renames (so the staged file is BQ-friendly), and uploads to the
canonical GCS path. Overwrites in place — new NIRF publications use the
same filenames.

Usage:
  python3 scripts/upload_to_gcs.py                    # upload all four
  python3 scripts/upload_to_gcs.py --table nirf_fact_rankings   # one only
  python3 scripts/upload_to_gcs.py --dry-run          # show what would happen
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, TABLES, Table


def _load_normalized(table: Table) -> pd.DataFrame:
    df = pd.read_parquet(table.local_path)
    if table.column_renames:
        unknown = set(table.column_renames) - set(df.columns)
        if unknown:
            raise SystemExit(
                f"{table.parquet}: rename map references columns not in the parquet: {sorted(unknown)}"
            )
        df = df.rename(columns=table.column_renames)
    return df


def _upload(table: Table, client, dry_run: bool) -> None:
    if not table.local_path.exists():
        raise SystemExit(f"missing local parquet: {table.local_path}")

    df = _load_normalized(table)
    msg = f"{table.local_path.name} ({len(df):,} rows, {len(df.columns)} cols) → {table.gcs_uri}"

    if dry_run:
        print(f"  [dry-run] {msg}")
        return

    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)

    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(f"{GCS_PREFIX}/{table.parquet}")
    blob.upload_from_file(buf, content_type="application/octet-stream")
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

    print(f"NIRF → gs://{GCS_BUCKET}/{GCS_PREFIX}/   ({'dry-run' if args.dry_run else 'upload'})")
    for t in chosen:
        _upload(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
