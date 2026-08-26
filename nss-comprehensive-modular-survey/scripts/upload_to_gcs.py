"""
Stage CMS-E files to gs://avantifellows-external-data/cmse/.

Two modes, both part of the normal flow:

  --raw     the three MoSPI unit-level CSVs + the six official documentation
            files, so the bucket carries everything needed to re-derive the
            tables from scratch without going back to microdata.gov.in
  (default) the clean parquet that BigQuery loads

Usage:
  python3 scripts/upload_to_gcs.py --raw
  python3 scripts/upload_to_gcs.py
  python3 scripts/upload_to_gcs.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources as S


def _upload(bucket, local: Path, gcs_path: str, dry_run: bool) -> None:
    if not local.exists():
        raise SystemExit(f"missing {local} — run clean_cmse.py first")
    size_mb = local.stat().st_size / 1e6
    target = f"gs://{S.GCS_BUCKET}/{gcs_path}"
    if dry_run:
        print(f"  [dry-run] {local.name:52s} {size_mb:7.1f} MB → {target}")
        return
    bucket.blob(gcs_path).upload_from_filename(str(local))
    print(f"  uploaded {local.name:52s} {size_mb:7.1f} MB → {target}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", action="store_true",
                    help="Upload the source CSVs and official docs instead of the clean parquet")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't touch GCS")
    args = ap.parse_args()

    bucket = None
    if not args.dry_run:
        from google.cloud import storage
        bucket = storage.Client(project=S.BQ_PROJECT).bucket(S.GCS_BUCKET)

    mode = "raw + docs" if args.raw else "clean parquet"
    print(f"CMS-E → gs://{S.GCS_BUCKET}/{S.GCS_PREFIX}/  ({mode}"
          f"{', dry-run' if args.dry_run else ''})")

    if args.raw:
        for rf in S.RAW_FILES:
            _upload(bucket, rf.local_path, rf.gcs_path, args.dry_run)
        for doc in S.DOC_FILES:
            _upload(bucket, S.DOCS / doc, f"{S.GCS_PREFIX}/raw/docs/{doc}", args.dry_run)
    else:
        for table in S.TABLES:
            _upload(bucket, table.local_path, table.gcs_path, args.dry_run)

    print("done.")


if __name__ == "__main__":
    main()
