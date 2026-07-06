"""
Upload AISHE files to GCS.

Uploads:
  - aishe/clean/*.parquet  → gs://avantifellows-external-data/aishe/clean/
  - aishe/raw/*.xlsx       → gs://avantifellows-external-data/aishe/raw/

Overwrites in place — re-running after a new dashboard export replaces the
old files. Run build_clean.py first to produce the clean parquets.

Usage:
  python3 scripts/upload_hedirectory_to_gcs.py                               # upload all
  python3 scripts/upload_hedirectory_to_gcs.py --table aishe_dim_colleges    # one table only
  python3 scripts/upload_hedirectory_to_gcs.py --dry-run                     # validate locally, no upload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources_hedirectory import GCS_BUCKET, GCS_PREFIX, RAW, TABLE_BY_NAME, TABLES, Table


def _upload_clean(table: Table, bucket, dry_run: bool) -> None:
    if not table.clean_path.exists():
        raise SystemExit(
            f"Missing clean parquet: {table.clean_path}\n"
            f"Run 'python3 scripts/build_hedirectory.py --table {table.bq_name}' first."
        )

    size_mb = table.clean_path.stat().st_size / 1_048_576
    gcs_uri = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{table.parquet}"
    msg = f"{table.clean_path.name} ({size_mb:.1f} MB) → {gcs_uri}"

    if dry_run:
        print(f"  [dry-run] {msg}")
        return

    blob = bucket.blob(f"{GCS_PREFIX}/clean/{table.parquet}")
    blob.upload_from_filename(str(table.clean_path), content_type="application/octet-stream")
    print(f"  uploaded {msg}")


def _upload_raw(bucket, dry_run: bool) -> None:
    raw_files = sorted(RAW.glob("*.xlsx")) + sorted(RAW.glob("*.xls"))
    if not raw_files:
        print("  (no raw files found in aishe/raw/)")
        return
    for f in raw_files:
        size_kb = f.stat().st_size // 1024
        gcs_uri = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/{f.name}"
        msg = f"{f.name} ({size_kb} KB) → {gcs_uri}"
        if dry_run:
            print(f"  [dry-run] {msg}")
        else:
            blob = bucket.blob(f"{GCS_PREFIX}/raw/{f.name}")
            blob.upload_from_filename(str(f))
            print(f"  uploaded {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--table",
        default=None,
        help="Upload only this BQ table's parquet (e.g. aishe_dim_colleges). Raw files are always uploaded.",
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

    bucket = None
    if not args.dry_run:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_BUCKET)

    mode = "dry-run" if args.dry_run else "upload"
    print(f"AISHE → gs://{GCS_BUCKET}/{GCS_PREFIX}/   ({mode})")

    print(f"  [clean parquets]")
    for t in chosen:
        _upload_clean(t, bucket, args.dry_run)

    print(f"  [raw Excel files]")
    _upload_raw(bucket, args.dry_run)

    print("✓ done.")


if __name__ == "__main__":
    main()
