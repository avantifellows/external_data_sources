#!/usr/bin/env python3
"""Stage apeapcet/ data to GCS: raw pulls (already canonical there) + the clean parquet."""
import sys
from pathlib import Path
from google.cloud import storage

sys.path.insert(0, str(Path(__file__).parent))
import sources as S

b = storage.Client().bucket(S.GCS_BUCKET)
ups = [(S.CLEAN / S.PARQUET, f"{S.GCS_PREFIX}/clean/{S.PARQUET}")]
for f in S.UPLOAD_FILES:
    p = S.RAW / f
    if p.exists():
        ups.append((p, f"{S.GCS_PREFIX}/raw/{f}"))
for src, dst in ups:
    b.blob(dst).upload_from_filename(src)
    print(f"  {src.name} -> gs://{S.GCS_BUCKET}/{dst}")
