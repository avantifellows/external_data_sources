#!/usr/bin/env python3
"""
Upload the NEET-2026 matrix data to GCS.

Three tiers, mirroring the nmc/ convention:
  raw/        the ~30 official source documents — state cutoff PDFs, allotment lists,
              merit lists — plus mizoram-zmch-2025-admitted/ (10 page images: ZMCH
              publishes its NMC admitted-student return as scans, not a table).
              Traceability only; never loaded to BQ. This is the tier that makes the
              pipeline reproducible by someone other than its author.
  extracted/  what the parsers produced from those documents (per-college allotments,
              closings, and the Odisha state-rank<->AIR bridge). Intermediate, kept so a
              reviewer can diff a parse against its source PDF without re-running OCR.
  clean/      the deliverable parquet, loaded to BQ by load_bq.py.

Run build_parquet.py first to produce clean/neet_marks_matrix_2026.parquet.

Usage:
  python3 scripts/upload_to_gcs.py              # all three tiers
  python3 scripts/upload_to_gcs.py --clean-only
  python3 scripts/upload_to_gcs.py --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, EXTRACTED, GCS_BUCKET, GCS_PREFIX, RAW, TABLES

from google.cloud import storage


def _upload(bucket, local: Path, remote: str, dry: bool) -> int:
    mb = local.stat().st_size / 1024 / 1024
    if dry:
        print(f"  [dry-run] {local.name} ({mb:.2f} MB) → gs://{GCS_BUCKET}/{remote}")
        return 0
    bucket.blob(remote).upload_from_filename(str(local))
    print(f"  ✓ {local.name} ({mb:.2f} MB) → gs://{GCS_BUCKET}/{remote}")
    return 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bucket = storage.Client(project="avantifellows").bucket(GCS_BUCKET)
    n = 0

    if not args.clean_only:
        print(f"Raw → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/ ...")
        for f in sorted(RAW.rglob("*")):
            if f.is_file() and not f.name.startswith("."):
                rel = f.relative_to(RAW).as_posix()
                n += _upload(bucket, f, f"{GCS_PREFIX}/raw/{rel}", args.dry_run)

        print(f"Extracted → gs://{GCS_BUCKET}/{GCS_PREFIX}/extracted/ ...")
        for f in sorted(EXTRACTED.glob("*.csv")):
            n += _upload(bucket, f, f"{GCS_PREFIX}/extracted/{f.name}", args.dry_run)

    print(f"Clean → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/ ...")
    for t in TABLES:
        if not t.local_path.exists():
            sys.exit(f"missing {t.local_path} — run build_parquet.py first")
        n += _upload(bucket, t.local_path, t.gcs_path, args.dry_run)

    print(f"✓ done. {n} file(s) uploaded." if not args.dry_run else "✓ dry-run complete.")


if __name__ == "__main__":
    main()
