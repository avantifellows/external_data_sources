#!/usr/bin/env python3
"""Upload JEE (Advanced) JIC reports and the clean parquet to GCS.

  python3 scripts/upload_to_gcs.py [--raw-only | --clean-only] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, RAW_FILES, TABLES


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-only", action="store_true")
    ap.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    jobs = []
    if not a.clean_only:
        jobs += [(rf.local_path, rf.gcs_path, "application/pdf") for rf in RAW_FILES]
    if not a.raw_only:
        jobs += [(t.local_path, t.gcs_path, "application/octet-stream") for t in TABLES]
    bucket = None if a.dry_run else __import__("google.cloud.storage", fromlist=["Client"]).Client().bucket(GCS_BUCKET)
    for local, path, ctype in jobs:
        if not local.exists():
            raise SystemExit(f"missing: {local}")
        if bucket:
            bucket.blob(path).upload_from_filename(str(local), content_type=ctype)
        print(f"  {'[dry-run] ' if a.dry_run else '✓ '}{local.name} → gs://{GCS_BUCKET}/{path}")


if __name__ == "__main__":
    main()
