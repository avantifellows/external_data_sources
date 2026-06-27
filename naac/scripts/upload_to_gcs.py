"""
Upload NAAC files to GCS — both raw xlsx and clean parquets.

  raw/   → gs://avantifellows-external-data/naac/raw/   (source xlsx)
  clean/ → gs://avantifellows-external-data/naac/clean/ (parquets for BQ load)

Pre-req for clean upload: run build_clean.py first to produce the parquets.

Usage:
  python3 scripts/upload_to_gcs.py                          # upload raw + all clean parquets
  python3 scripts/upload_to_gcs.py --table naac_fact_colleges  # raw + one clean parquet
  python3 scripts/upload_to_gcs.py --raw-only               # raw xlsx only
  python3 scripts/upload_to_gcs.py --clean-only             # clean parquets only
  python3 scripts/upload_to_gcs.py --dry-run                # show what would happen
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, RAW, TABLES, XLSX_FILE, Table


def _upload_file(local: Path, gcs_path: str, client, dry_run: bool) -> None:
    if not local.exists():
        raise SystemExit(f"file not found: {local}")
    msg = f"{local.name} → gs://{GCS_BUCKET}/{gcs_path}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_path)
    blob.upload_from_filename(str(local), content_type="application/octet-stream")
    print(f"  uploaded {msg}")


def _upload_raw(client, dry_run: bool) -> None:
    xlsx = RAW / XLSX_FILE
    _upload_file(xlsx, f"{GCS_PREFIX}/raw/{XLSX_FILE}", client, dry_run)


def _upload_clean(table: Table, client, dry_run: bool) -> None:
    if not table.local_path.exists():
        raise SystemExit(
            f"clean parquet not found: {table.local_path}\n"
            "Run build_clean.py first."
        )
    _upload_file(table.local_path, f"{GCS_PREFIX}/clean/{table.parquet}", client, dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--table", default=None, help="Upload only this clean BQ table (implies --clean-only)")
    ap.add_argument("--raw-only", action="store_true", help="Upload raw xlsx only")
    ap.add_argument("--clean-only", action="store_true", help="Upload clean parquets only")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't upload")
    args = ap.parse_args()

    do_raw   = not args.clean_only
    do_clean = not args.raw_only

    chosen = TABLES
    if args.table:
        chosen = [t for t in TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")
        do_raw = False  # --table implies clean only

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    print(f"NAAC → gs://{GCS_BUCKET}/{GCS_PREFIX}/   ({'dry-run' if args.dry_run else 'upload'})")

    if do_raw:
        print("  [raw]")
        _upload_raw(client, args.dry_run)

    if do_clean:
        print("  [clean]")
        for t in chosen:
            _upload_clean(t, client, args.dry_run)

    print("✓ done.")


if __name__ == "__main__":
    main()
