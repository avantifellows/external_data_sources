"""
Load AISHE parquet files from GCS into BigQuery.

Each parquet listed in sources.py is loaded via load_table_from_uri with
WRITE_TRUNCATE — fully replaces the destination table on every run. Idempotent.

Pre-reqs (one-time):
  bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
  (Parquet files must already be in gs://avantifellows-external-data/aishe/
   — see scripts/upload_to_gcs.py.)

Usage:
  python3 scripts/load_bq.py                                  # load all tables
  python3 scripts/load_bq.py --table aishe_fact_higher_ed
  python3 scripts/load_bq.py --dry-run                        # show plan only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_LOCATION, BQ_PROJECT, TABLES, Table


def _load(table: Table, client, dry_run: bool) -> None:
    msg = f"{table.gcs_uri} → {table.bq_table_id}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return

    from google.cloud import bigquery

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_uri(
        table.gcs_uri, table.bq_table_id, job_config=job_config, location=BQ_LOCATION
    )
    job.result()
    out = client.get_table(table.bq_table_id)
    print(f"  loaded {out.num_rows:>10,} rows → {table.bq_table_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=None, help="Load only this BQ table name")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't touch BQ")
    args = ap.parse_args()

    chosen = TABLES
    if args.table:
        chosen = [t for t in TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")

    client = None
    if not args.dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print(f"AISHE → {BQ_PROJECT}.external_data_sources.*   ({'dry-run' if args.dry_run else 'load'})")
    for t in chosen:
        _load(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
