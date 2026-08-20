"""
Upload the clean NIRF parquet files to GCS.

Reads each parquet listed in sources.py from nirf/clean/ — as written by
build_clean.py, already deduplicated and with BQ-friendly column names — and
uploads it byte-for-byte to the canonical GCS path. Overwrites in place; new
NIRF publications use the same filenames.

Nothing is transformed here. If a column name needs changing, change it in
build_clean.py so that clean/ == GCS == BQ stay identical.

Usage:
  python3 scripts/upload_to_gcs.py                    # upload all clean parquets
  python3 scripts/upload_to_gcs.py --table nirf_fact_rankings   # one only
  python3 scripts/upload_to_gcs.py --dcs-raw          # stage the raw DCS haul
  python3 scripts/upload_to_gcs.py --extracted        # stage parse_dcs.py CSVs
  python3 scripts/upload_to_gcs.py --dry-run          # show what would happen

--dcs-raw zips the first-party haul so ~1,700 tiny PDFs don't become ~1,700
GCS objects: one zip per (discipline, edition year) of DCS PDFs, one zip of
every saved ranking page, and the seed lists verbatim, all under
gs://avantifellows-external-data/nirf/raw/dcs/. Re-running overwrites in
place — the zips are deterministic snapshots of raw/dcs/.
"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (DCS_RAW, DCS_SEEDS, EXTRACTED, GCS_BUCKET, GCS_PREFIX,
                     TABLES, Table)


def _upload(table: Table, client, dry_run: bool) -> None:
    if not table.local_path.exists():
        raise SystemExit(
            f"missing clean parquet: {table.local_path}\n"
            f"Build it first:  python3 scripts/build_clean.py --table {table.bq_name}"
        )

    md = pq.ParquetFile(table.local_path).metadata
    msg = (f"{table.local_path.name} ({md.num_rows:,} rows, {md.num_columns} cols) "
           f"→ {table.gcs_uri}")

    if dry_run:
        print(f"  [dry-run] {msg}")
        return

    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(f"{GCS_PREFIX}/clean/{table.parquet}")
    blob.upload_from_filename(str(table.local_path), content_type="application/octet-stream")
    print(f"  uploaded {msg}")


def _upload_blob(client, gcs_path: str, local: Path, dry_run: bool) -> None:
    size = local.stat().st_size
    if dry_run:
        print(f"  [dry-run] {local.name} ({size/1e6:.1f} MB) → gs://{GCS_BUCKET}/{gcs_path}")
        return
    client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_filename(str(local))
    print(f"  uploaded {local.name} ({size/1e6:.1f} MB) → gs://{GCS_BUCKET}/{gcs_path}")


def upload_dcs_raw(client, dry_run: bool) -> None:
    tmp = DCS_RAW / "_zips"
    tmp.mkdir(exist_ok=True)
    # per (discipline, year) PDF bundles
    for disc_dir in sorted((DCS_RAW / "pdf").iterdir()):
        for year_dir in sorted(disc_dir.iterdir()):
            pdfs = sorted(year_dir.glob("*.pdf"))
            if not pdfs:
                continue
            z = tmp / f"dcs_pdfs_{disc_dir.name.lower()}_{year_dir.name}.zip"
            with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in pdfs:
                    zf.write(f, f.name)
            _upload_blob(client, f"{GCS_PREFIX}/raw/dcs/{z.name}", z, dry_run)
    # every saved ranking/band/participant page, one zip
    z = tmp / "ranking_pages.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted((DCS_RAW / "pages").rglob("*.html")):
            zf.write(f, f"{f.parent.name}/{f.name}")
    _upload_blob(client, f"{GCS_PREFIX}/raw/dcs/{z.name}", z, dry_run)
    # seed lists, verbatim (small, and their provenance matters)
    for f in sorted(DCS_SEEDS.glob("*.txt")):
        _upload_blob(client, f"{GCS_PREFIX}/raw/dcs/seeds/{f.name}", f, dry_run)


def upload_extracted(client, dry_run: bool) -> None:
    for f in sorted(EXTRACTED.glob("*.csv")):
        _upload_blob(client, f"{GCS_PREFIX}/extracted/{f.name}", f, dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=None, help="Upload only this BQ table name (e.g. nirf_fact_rankings)")
    ap.add_argument("--dry-run", action="store_true", help="Read + normalize locally; don't upload")
    ap.add_argument("--dcs-raw", action="store_true", help="Stage raw/dcs/ (zipped) instead of clean parquets")
    ap.add_argument("--extracted", action="store_true", help="Stage extracted/ CSVs instead of clean parquets")
    args = ap.parse_args()

    chosen = TABLES
    if args.table:
        chosen = [t for t in TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    if args.dcs_raw:
        print(f"NIRF raw DCS haul → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/dcs/")
        upload_dcs_raw(client, args.dry_run)
        print("✓ done.")
        return
    if args.extracted:
        print(f"NIRF extracted → gs://{GCS_BUCKET}/{GCS_PREFIX}/extracted/")
        upload_extracted(client, args.dry_run)
        print("✓ done.")
        return

    print(f"NIRF → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/   "
          f"({'dry-run' if args.dry_run else 'upload'})")
    for t in chosen:
        _upload(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
