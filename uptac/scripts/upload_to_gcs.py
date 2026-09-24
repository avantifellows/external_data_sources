#!/usr/bin/env python3
"""
Upload UPTAC data to GCS.

  - Raw:   raw/pages/*.html zipped into one dated archive (the pages ARE the
           raw artifact) -> gs://avantifellows-external-data/uptac/raw/
  - Clean: clean/uptac_fact_cutoffs.parquet -> gs://…/uptac/clean/

Usage:
  python3 scripts/upload_to_gcs.py                 # raw + clean
  python3 scripts/upload_to_gcs.py --clean-only
  python3 scripts/upload_to_gcs.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, PAGES, RAW, TABLES


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from google.cloud import storage
    bucket = None if args.dry_run else storage.Client().bucket(GCS_BUCKET)

    if not args.clean_only:
        pages = sorted(PAGES.glob("page_*.html"))
        if not pages:
            raise SystemExit("no raw pages — run fetch_pages.py")
        z = RAW / f"uptac_orcr_pages_{datetime.date.today().isoformat()}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in pages:
                zf.write(f, f.name)
        dest = f"{GCS_PREFIX}/raw/{z.name}"
        print(f"  {z.name} ({len(pages)} pages, {z.stat().st_size/1e6:.1f} MB) -> gs://{GCS_BUCKET}/{dest}")
        if bucket:
            bucket.blob(dest).upload_from_filename(str(z), content_type="application/zip", timeout=900)
    for t in TABLES:
        if not t.local_path.exists():
            raise SystemExit(f"missing {t.local_path}; run build_clean.py")
        print(f"  {t.parquet} -> {t.gcs_uri}")
        if bucket:
            bucket.blob(t.gcs_path).upload_from_filename(str(t.local_path), timeout=900)
    print("✓ done.")


if __name__ == "__main__":
    main()
