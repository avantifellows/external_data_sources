"""
Stage the state-medical raw CSV and clean parquet to GCS.

- raw/  → gs://avantifellows-external-data/state_medical/raw/   (provenance)
- clean/→ gs://avantifellows-external-data/state_medical/clean/ (the parquet BQ loads)

Run build_clean.py first. Overwrites in place.

Usage:
  python3 scripts/upload_to_gcs.py                 # upload clean (default)
  python3 scripts/upload_to_gcs.py --raw           # also upload raw/ CSV
  python3 scripts/upload_to_gcs.py --dry-run       # list what would upload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, RAW, RAW_FILE, TABLES


def _upload_file(client, local: Path, object_name: str, dry_run: bool) -> None:
    msg = f"{local}  →  gs://{GCS_BUCKET}/{object_name}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    client.bucket(GCS_BUCKET).blob(object_name).upload_from_filename(str(local))
    print(f"  uploaded {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--raw", action="store_true", help="Also upload raw/ CSV")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't upload")
    args = ap.parse_args()

    clean_files = [t.local_path for t in TABLES]
    for f in clean_files:
        if not f.exists():
            raise SystemExit(f"missing clean parquet: {f} — run build_clean.py first")

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    print(f"state_medical → gs://{GCS_BUCKET}/{GCS_PREFIX}/   ({'dry-run' if args.dry_run else 'upload'})")

    for f in clean_files:
        _upload_file(client, f, f"{GCS_PREFIX}/clean/{f.name}", args.dry_run)

    if args.raw:
        raw_csv = RAW / RAW_FILE
        if raw_csv.exists():
            _upload_file(client, raw_csv, f"{GCS_PREFIX}/raw/{RAW_FILE}", args.dry_run)
        else:
            print(f"  (no raw CSV at {raw_csv} to upload)")

    print("✓ done.")


if __name__ == "__main__":
    main()
