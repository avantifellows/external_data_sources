"""
Stage Dakshana files to GCS (gs://avantifellows-external-data/dakshana/).

Two layers (raw kept for audit, clean is what BQ loads):
  --raw     stage the original source artifacts          raw/<...>   -> gs://.../dakshana/raw/<...>
  (default) stage each table's clean artifact as parquet clean/<...> -> gs://.../dakshana/clean/<...>

Both tables flow through here despite different shapes (see sources.py):
  - dakshana_fact_ncst_results      clean = ncst_clean.csv  (CSV → dtyped → parquet);
                                    raw  = per-year Excel sheets (→ parquet).
  - dakshana_fact_reported_results  clean = parquet (as-is); raw = CSVs (copied as-is).

Run clean_ncst.py / build_reported_results.py first to produce the clean artifacts.

Usage:
  python3 scripts/upload_to_gcs.py --raw                            # stage original sources
  python3 scripts/upload_to_gcs.py                                  # stage all clean tables
  python3 scripts/upload_to_gcs.py --table dakshana_fact_ncst_results
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


def _read_clean(table: Table) -> pd.DataFrame:
    if not table.local_path.exists():
        raise SystemExit(f"missing clean file: {table.local_path}  (run its build step first)")
    df = (pd.read_parquet(table.local_path) if table.local_path.suffix == ".parquet"
          else pd.read_csv(table.local_path, low_memory=False))
    if table.post_read:
        df = table.post_read(df)
    if table.column_renames:
        df = df.rename(columns=table.column_renames)
    return df


def _upload_df(client, df: pd.DataFrame, dest: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    buf.seek(0)
    client.bucket(GCS_BUCKET).blob(dest).upload_from_file(buf, content_type="application/octet-stream")


def _upload_raw(client, dry_run: bool) -> None:
    for rf in RAW_FILES:
        src = rf.local_path
        if not src.exists():
            print(f"  WARNING: missing raw file {src} — skipping.")
            continue
        dest = rf.gcs_path
        if rf.sheet is not None:  # Excel sheet → parquet
            df = pd.read_excel(src, sheet_name=rf.sheet, dtype=str)
            msg = f"{rf.local_rel} [{rf.sheet}] ({len(df):,} rows) → gs://{GCS_BUCKET}/{dest}"
            if dry_run:
                print(f"  [dry-run] {msg}")
                continue
            _upload_df(client, df, dest)
        else:                     # copy file as-is
            msg = f"{rf.local_rel} ({src.stat().st_size:,} B) → gs://{GCS_BUCKET}/{dest}"
            if dry_run:
                print(f"  [dry-run] {msg}")
                continue
            client.bucket(GCS_BUCKET).blob(dest).upload_from_filename(str(src))
        print(f"  uploaded {msg}")


def _upload_clean(table: Table, client, dry_run: bool) -> None:
    df = _read_clean(table)
    msg = f"{table.parquet} ({len(df):,} rows, {len(df.columns)} cols) → {table.gcs_uri}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    _upload_df(client, df, f"{GCS_PREFIX}/clean/{table.parquet}")
    print(f"  uploaded {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", action="store_true", help="stage original sources to raw/ instead of clean tables")
    ap.add_argument("--table", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    if args.raw:
        print(f"Dakshana raw → gs://{GCS_BUCKET}/dakshana/raw/   ({'dry-run' if args.dry_run else 'upload'})")
        _upload_raw(client, args.dry_run)
        print("done.")
        return

    chosen = [t for t in TABLES if t.bq_name == args.table] if args.table else TABLES
    if args.table and not chosen:
        raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")
    print(f"Dakshana clean → gs://{GCS_BUCKET}/dakshana/clean/   ({'dry-run' if args.dry_run else 'upload'})")
    for t in chosen:
        _upload_clean(t, client, args.dry_run)
    print("done.")


if __name__ == "__main__":
    main()
