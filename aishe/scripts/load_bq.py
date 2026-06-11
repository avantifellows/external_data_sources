"""
Load clean AISHE parquet files from GCS into BigQuery.

Each parquet listed in sources.py is loaded via load_table_from_uri with
WRITE_TRUNCATE — fully replaces the destination table on every run.
Idempotent. Run upload_to_gcs.py first to stage the files.

Pre-reqs (one-time):
  bq --location=asia-south1 mk --dataset avantifellows:external_data_sources

Usage:
  python3 scripts/load_bq.py                              # load all five
  python3 scripts/load_bq.py --table aishe_fact_colleges  # one only
  python3 scripts/load_bq.py --dry-run                    # print plan, no BQ writes
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_DATASET, BQ_LOCATION, BQ_PROJECT, TABLE_BY_NAME, TABLES, Table


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
        table.gcs_uri,
        table.bq_table_id,
        job_config=job_config,
        location=BQ_LOCATION,
    )
    job.result()  # wait for completion; raises on failure
    out = client.get_table(table.bq_table_id)
    print(f"  loaded {out.num_rows:>10,} rows → {table.bq_table_id}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--table",
        default=None,
        help="Load only this BQ table (e.g. aishe_fact_colleges).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan; don't touch BigQuery.",
    )
    args = ap.parse_args()

    if args.table:
        if args.table not in TABLE_BY_NAME:
            raise SystemExit(
                f"Unknown table {args.table!r}. Known: {list(TABLE_BY_NAME)}"
            )
        chosen = [TABLE_BY_NAME[args.table]]
    else:
        chosen = TABLES

    client = None
    if not args.dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print(
        f"AISHE → {BQ_PROJECT}.{BQ_DATASET}.*   "
        f"({'dry-run' if args.dry_run else 'load'})"
    )
    for t in chosen:
        _load(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
