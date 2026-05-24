#!/usr/bin/env python3
"""
Load AICTE clean parquet from GCS into BigQuery.

Each table listed in sources.py is loaded via load_table_from_uri with
WRITE_TRUNCATE — fully replaces the destination table on every run. Idempotent.
Run upload_to_gcs.py first.

Usage:
  python3 scripts/load_bq.py
  python3 scripts/load_bq.py --dry-run
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
    job = client.load_table_from_uri(table.gcs_uri, table.bq_table_id, job_config=job_config, location=BQ_LOCATION)
    job.result()
    out = client.get_table(table.bq_table_id)
    print(f"  loaded {out.num_rows:>8,} rows → {table.bq_table_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print(f"aicte → {BQ_PROJECT}.external_data_sources.*   ({'dry-run' if args.dry_run else 'load'})")
    for t in TABLES:
        _load(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
