"""Stage raw (pages + per-list PDF zips) , extracted CSVs and clean parquet."""
from __future__ import annotations
import sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN_PARQUET, EXTRACTED, GCS_BUCKET, GCS_PREFIX, LISTS, RAW

def main() -> None:
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_BUCKET)
    def up(path, dest):
        bucket.blob(dest).upload_from_filename(str(path))
        print(f"  {path.name} ({path.stat().st_size/1e6:.1f} MB) → gs://{GCS_BUCKET}/{dest}")
    tmp = RAW / "_zips"; tmp.mkdir(exist_ok=True)
    for n in LISTS:
        pdfs = sorted((RAW / "pdf" / f"list{n}").glob("*.pdf"))
        if not pdfs: continue
        z = tmp / f"clat_2026_ug_list{n}_pdfs.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in pdfs: zf.write(f, f.name)
        up(z, f"{GCS_PREFIX}/raw/{z.name}")
    for f in sorted((RAW / "pages").glob("*.html")):
        up(f, f"{GCS_PREFIX}/raw/pages/{f.name}")
    for f in sorted(EXTRACTED.glob("*.csv")):
        up(f, f"{GCS_PREFIX}/extracted/{f.name}")
    up(CLEAN_PARQUET, f"{GCS_PREFIX}/clean/{CLEAN_PARQUET.name}")

if __name__ == "__main__":
    main()
