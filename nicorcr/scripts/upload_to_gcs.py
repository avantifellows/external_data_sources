#!/usr/bin/env python3
"""
Upload NIC OR-CR data to GCS: raw report HTML (the raw artifact) and the
clean parquet.

Usage:
  python3 scripts/upload_to_gcs.py [--clean-only] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, RAW, REPORTS, TABLES


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from google.cloud import storage
    bucket = None if args.dry_run else storage.Client().bucket(GCS_BUCKET)
    files = [] if args.clean_only else [(RAW / r.raw_name, f"{GCS_PREFIX}/raw/{r.raw_name}", "text/html") for r in REPORTS]
    files += [(t.local_path, t.gcs_path, "application/octet-stream") for t in TABLES]
    for local, dest, ctype in files:
        if not local.exists():
            raise SystemExit(f"missing {local}")
        print(f"  {local.name} -> gs://{GCS_BUCKET}/{dest}")
        if bucket:
            bucket.blob(dest).upload_from_filename(str(local), content_type=ctype, timeout=900)
    print("✓ done.")


if __name__ == "__main__":
    main()
