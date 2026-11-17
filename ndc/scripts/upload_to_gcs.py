#!/usr/bin/env python3
"""
Stage NDC to GCS: the newest raw fetch (list.html, details/*.html, index.json)
under gs://avantifellows-external-data/ndc/raw/<date>/, and the clean parquet
under .../ndc/clean/. Needs a key that can write the bucket (the gcs-handler
one; the BigQuery-only key gets a 403).

Usage:
  python3 scripts/upload_to_gcs.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, GCS_PREFIX, latest_raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    day = latest_raw()
    files = [(p, f"{GCS_PREFIX}/raw/{day.name}/{p.relative_to(day)}") for p in sorted(day.rglob("*")) if p.is_file()]
    files += [(p, f"{GCS_PREFIX}/clean/{p.name}") for p in sorted(CLEAN.glob("*.parquet"))]
    if args.dry_run:
        for p, g in files[:5] + files[-3:]:
            print(f"  [dry-run] {p.name} → gs://{GCS_BUCKET}/{g}")
        print(f"  … {len(files)} files")
        return
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_BUCKET)
    for p, g in files:
        ctype = ("text/html" if p.suffix == ".html" else "application/json" if p.suffix == ".json"
                 else "application/octet-stream")
        bucket.blob(g).upload_from_filename(str(p), content_type=ctype)
    print(f"✓ {len(files)} files → gs://{GCS_BUCKET}/{GCS_PREFIX}/")


if __name__ == "__main__":
    main()
