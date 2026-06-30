"""
Stage the JoSAA raw CSVs and clean parquet to GCS.

- raw/  → gs://avantifellows-external-data/josaa/raw/   (the scraper output,
          kept for provenance/regenerability)
- clean/→ gs://avantifellows-external-data/josaa/clean/ (the parquet BQ loads)

Run build_clean.py first so clean/ is current. Overwrites in place — a new
JoSAA cycle reuses the same object names.

Usage:
  python3 scripts/upload_to_gcs.py                 # upload clean (default)
  python3 scripts/upload_to_gcs.py --raw           # also upload raw/ CSVs
  python3 scripts/upload_to_gcs.py --dry-run       # list what would upload
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, GCS_PREFIX, RAW, TABLES


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
    ap.add_argument("--raw", action="store_true", help="Also upload raw/*.csv")
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

    print(f"JoSAA → gs://{GCS_BUCKET}/{GCS_PREFIX}/   ({'dry-run' if args.dry_run else 'upload'})")

    for f in clean_files:
        _upload_file(client, f, f"{GCS_PREFIX}/clean/{f.name}", args.dry_run)

    if args.raw:
        raw_files = sorted(RAW.glob("*_R*.csv"))
        if not raw_files:
            print(f"  (no raw CSVs in {RAW} to upload)")
        for f in raw_files:
            _upload_file(client, f, f"{GCS_PREFIX}/raw/{f.name}", args.dry_run)

    print("✓ done.")


if __name__ == "__main__":
    main()
