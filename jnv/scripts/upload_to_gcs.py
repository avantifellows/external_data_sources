"""
Stage JNV files to GCS (gs://avantifellows-external-data/jnv/).

Two layers, matching the skill's model (raw kept for audit, clean is what BQ loads):
  --raw     upload the original NTA exports        raw/<...>       -> gs://.../jnv/raw/<...>
  (default) upload each table's clean parquet      clean/<table>   -> gs://.../jnv/clean/<table>

Usage:
  python3 scripts/upload_to_gcs.py --raw                            # stage original NTA files
  python3 scripts/upload_to_gcs.py                                  # stage all clean tables
  python3 scripts/upload_to_gcs.py --table jnv_fact_jee_advanced_rank_list
  python3 scripts/upload_to_gcs.py --dry-run                        # show; don't upload
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import GCS_BUCKET, GCS_PREFIX, RAW_FILES, TABLES, Table

RAW_DIR = Path(__file__).resolve().parent.parent / "raw"


def _upload_raw(client, dry_run: bool) -> None:
    for local_rel, gcs_sub in RAW_FILES:
        src = RAW_DIR / local_rel
        if not src.exists():
            raise SystemExit(f"missing raw file: {src}")
        dest = f"{GCS_PREFIX}/raw/{gcs_sub}{src.name}"
        msg = f"{local_rel} ({src.stat().st_size:,} B) → gs://{GCS_BUCKET}/{dest}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        client.bucket(GCS_BUCKET).blob(dest).upload_from_filename(str(src))
        print(f"  uploaded {msg}")


def _upload(table: Table, client, dry_run: bool) -> None:
    if not table.local_path.exists():
        raise SystemExit(f"missing clean parquet: {table.local_path}  (run its build_*.py first)")
    df = pd.read_parquet(table.local_path)
    if table.column_renames:
        df = df.rename(columns=table.column_renames)
    msg = f"{table.parquet} ({len(df):,} rows, {len(df.columns)} cols) → {table.gcs_uri}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client.bucket(GCS_BUCKET).blob(f"{GCS_PREFIX}/clean/{table.parquet}").upload_from_file(
        buf, content_type="application/octet-stream")
    print(f"  uploaded {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", action="store_true", help="upload original NTA exports to raw/ instead of clean tables")
    ap.add_argument("--table", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()
    if args.raw:
        print(f"JNV raw → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/   ({'dry-run' if args.dry_run else 'upload'})")
        _upload_raw(client, args.dry_run)
        print("done.")
        return
    chosen = [t for t in TABLES if t.bq_name == args.table] if args.table else TABLES
    if args.table and not chosen:
        raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")
    print(f"JNV clean → gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/   ({'dry-run' if args.dry_run else 'upload'})")
    for t in chosen:
        _upload(t, client, args.dry_run)
    print("done.")


if __name__ == "__main__":
    main()
