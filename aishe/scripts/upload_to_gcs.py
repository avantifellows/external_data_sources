"""
Upload clean AISHE parquet files to GCS.

Reads each parquet from aishe/clean/ (produced by build_clean.py) and
uploads to gs://avantifellows-external-data/aishe/clean/. Overwrites in
place — re-running after a new dashboard export replaces the old files.

Run build_clean.py first to produce the clean parquets.

Usage:
  python3 scripts/upload_to_gcs.py                              # upload all five
  python3 scripts/upload_to_gcs.py --table aishe_fact_colleges  # one only
  python3 scripts/upload_to_gcs.py --dry-run                    # validate locally, no upload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, TABLE_BY_NAME, TABLES, Table


def _upload(table: Table, client, dry_run: bool) -> None:
    if not table.clean_path.exists():
        raise SystemExit(
            f"Missing clean parquet: {table.clean_path}\n"
            f"Run 'python3 scripts/build_clean.py --table {table.bq_name}' first."
        )

    size_mb = table.clean_path.stat().st_size / 1_048_576
    msg = f"{table.clean_path.name} ({size_mb:.1f} MB) → {table.gcs_uri}"

    if dry_run:
        print(f"  [dry-run] {msg}")
        return

    bucket = client.bucket(GCS_BUCKET)
    blob_path = f"{GCS_PREFIX}/clean/{table.parquet}"
    blob = bucket.blob(blob_path)
    blob.upload_from_filename(str(table.clean_path), content_type="application/octet-stream")
    print(f"  uploaded {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--table",
        default=None,
        help="Upload only this BQ table (e.g. aishe_fact_colleges).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate locally; don't upload to GCS.",
    )
    args = ap.parse_args()

    if args.table:
        if args.table not in TABLE_BY_NAME:
            raise SystemExit(
                f"Unknown table {args.table!r}. Known: {list(TABLE_BY_NAME)}"
            )
        chosen = [TABLE_BY_NAME[args.table]]
    else:
        chosen = TABLES

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    print(
        f"AISHE → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/   "
        f"({'dry-run' if args.dry_run else 'upload'})"
    )
    for t in chosen:
        _upload(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
