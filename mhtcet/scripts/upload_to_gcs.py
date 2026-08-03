"""Upload auditable MHT-CET raw sources and deterministic clean Parquet to GCS."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (
    GCS_BUCKET, GCS_PREFIX, OPTIONAL_RAW_FILES, RAW, RAW_FILES, TABLES,
)


def _items(include_raw: bool, include_clean: bool) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    if include_raw:
        for name in RAW_FILES:
            path = RAW / name
            if not path.exists():
                raise SystemExit(f"Missing required raw source: {path}")
            items.append((path, f"{GCS_PREFIX}/raw/{name}"))
        for name in OPTIONAL_RAW_FILES:
            path = RAW / name
            if path.exists():
                items.append((path, f"{GCS_PREFIX}/raw/{name}"))
    if include_clean:
        for table in TABLES:
            if not table.local_path.exists():
                raise SystemExit(f"Missing clean parquet: {table.local_path}; run build_clean.py")
            items.append((table.local_path, f"{GCS_PREFIX}/clean/{table.parquet}"))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--raw-only", action="store_true")
    mode.add_argument("--clean-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    include_raw = not args.clean_only
    include_clean = not args.raw_only
    items = _items(include_raw, include_clean)

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client(project="avantifellows")

    for local_path, object_name in items:
        destination = f"gs://{GCS_BUCKET}/{object_name}"
        if args.dry_run:
            print(f"[dry-run] {local_path} -> {destination}")
        else:
            client.bucket(GCS_BUCKET).blob(object_name).upload_from_filename(str(local_path))
            print(f"Uploaded {local_path} -> {destination}")


if __name__ == "__main__":
    main()
