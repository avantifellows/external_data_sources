#!/usr/bin/env python3
"""
Upload CUSB UG cut-off data to GCS.

  - Raw:       every announcement and rules document, as downloaded
               gs://avantifellows-external-data/cusbug/raw/<file>
  - Extracted: the reviewed transcription of scanned / per-category notices
               gs://avantifellows-external-data/cusbug/extracted/manual_transcriptions.csv
  - Clean:     gs://avantifellows-external-data/cusbug/clean/cusbug_fact_cutoffs.parquet

Usage:
  python3 scripts/upload_to_gcs.py [--raw-only | --clean-only] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, MANUAL, MANUAL_GCS, RAW_FILES, TABLES


def put(client, local: Path, path: str, ctype: str, dry: bool) -> None:
    if not local.exists():
        raise SystemExit(f"missing: {local}")
    msg = f"{local.name} ({local.stat().st_size / 1e6:.2f} MB) → gs://{GCS_BUCKET}/{path}"
    if dry:
        print(f"  [dry-run] {msg}")
        return
    client.bucket(GCS_BUCKET).blob(path).upload_from_filename(str(local), content_type=ctype)
    print(f"  ✓ {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-only", action="store_true")
    ap.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    client = None
    if not a.dry_run:
        from google.cloud import storage
        client = storage.Client()
    if not a.clean_only:
        for rf in RAW_FILES:
            put(client, rf.local_path, rf.gcs_path, "application/pdf", a.dry_run)
        put(client, MANUAL, MANUAL_GCS, "text/csv", a.dry_run)
    if not a.raw_only:
        for t in TABLES:
            put(client, t.local_path, t.gcs_path, "application/octet-stream", a.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
