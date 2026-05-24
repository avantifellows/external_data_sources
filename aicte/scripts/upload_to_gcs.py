#!/usr/bin/env python3
"""
Upload AICTE data to GCS.

Uploads (mirrors the jnv/ / udise/ convention):
  - Raw:   the three panel CSVs pulled by fetch.py, as-is (they ARE the raw artifact)
           gs://avantifellows-external-data/aicte/raw/panel_*.csv   (traceability)
  - Clean: the unified wide fact → parquet
           gs://avantifellows-external-data/aicte/clean/intake.parquet

Run fetch.py then clean_aicte.py first to produce clean/intake.parquet.

Usage:
  python3 scripts/upload_to_gcs.py                 # raw + clean
  python3 scripts/upload_to_gcs.py --raw-only / --clean-only / --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, RAW_PANELS, TABLES


def _cp(client, local: Path, gcs_path: str, content_type: str, dry_run: bool) -> None:
    size_mb = local.stat().st_size / 1e6
    msg = f"{local.name} ({size_mb:.2f} MB) → gs://{GCS_BUCKET}/{gcs_path}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_filename(str(local), content_type=content_type)
    print(f"  ✓ {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--raw-only", action="store_true")
    group.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    if not args.clean_only:
        print(f"Raw → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/")
        for panel in RAW_PANELS:
            if not panel.exists():
                raise SystemExit(f"missing raw panel: {panel}\nRun scripts/fetch.py first.")
            _cp(client, panel, f"{GCS_PREFIX}/raw/{panel.name}", "text/csv", args.dry_run)

    if not args.raw_only:
        print(f"Clean → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/")
        for t in TABLES:
            if not t.local_path.exists():
                raise SystemExit(f"missing parquet: {t.local_path}\nRun scripts/clean_aicte.py first.")
            _cp(client, t.local_path, t.gcs_path, "application/octet-stream", args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
