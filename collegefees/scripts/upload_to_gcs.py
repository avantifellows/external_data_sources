"""Stage the raw sheet + clean parquet to GCS. Byte-for-byte, no transforms."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN_PARQUET, GCS_BUCKET, GCS_PREFIX, RAW_CSV

def main() -> None:
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_BUCKET)
    for local, kind in [(RAW_CSV, "raw"), (CLEAN_PARQUET, "clean")]:
        if not local.exists():
            raise SystemExit(f"missing {local}")
        blob = bucket.blob(f"{GCS_PREFIX}/{kind}/{local.name}")
        blob.upload_from_filename(str(local))
        print(f"  uploaded {local.name} ({local.stat().st_size/1e6:.1f} MB) → "
              f"gs://{GCS_BUCKET}/{GCS_PREFIX}/{kind}/{local.name}")

if __name__ == "__main__":
    main()
