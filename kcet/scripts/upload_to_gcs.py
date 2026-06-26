"""
Upload KCET clean parquet to GCS.

gs://avantifellows-external-data/kcet/clean/kcet_fact_cutoffs.parquet

Run build_clean.py first. Overwrites in place.

Usage:
  python3 scripts/upload_to_gcs.py --dry-run
  python3 scripts/upload_to_gcs.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, TABLES


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't upload.")
    args = ap.parse_args()

    for t in TABLES:
        if not t.local_path.exists():
            raise SystemExit(
                f"Missing parquet: {t.local_path}\nRun build_clean.py first."
            )

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    print(f"KCET → gs://{GCS_BUCKET}/{GCS_PREFIX}/   ({'dry-run' if args.dry_run else 'upload'})")
    for t in TABLES:
        obj = f"{GCS_PREFIX}/clean/{t.parquet}"
        msg = f"{t.local_path}  →  gs://{GCS_BUCKET}/{obj}"
        if args.dry_run:
            print(f"  [dry-run] {msg}")
        else:
            client.bucket(GCS_BUCKET).blob(obj).upload_from_filename(str(t.local_path))
            print(f"  uploaded {msg}")

    print("✓ done.")


if __name__ == "__main__":
    main()
