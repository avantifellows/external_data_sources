#!/usr/bin/env python3
"""
Load UBSE clean data from GCS into BigQuery.

Reads:
    gs://avantifellows-external-data/ubse/clean/ubse_fact_grade10_results.parquet
    gs://avantifellows-external-data/ubse/clean/ubse_fact_grade12_results.parquet

Writes (WRITE_TRUNCATE):
    avantifellows.external_data_sources.ubse_fact_grade10_results
    avantifellows.external_data_sources.ubse_fact_grade12_results

Run upload_to_gcs.py first.

Usage:
    python3 scripts/load_bq.py                # load both
    python3 scripts/load_bq.py --grade10-only
    python3 scripts/load_bq.py --grade12-only
"""

import argparse
import sys
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import BQ_LOCATION, BQ_PROJECT, GRADE10_CLEAN, GRADE12_CLEAN


def _load(client: bigquery.Client, table) -> None:
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    print(f"Loading {table.gcs_uri}")
    print(f"  → {table.bq_table_id}")
    job = client.load_table_from_uri(
        table.gcs_uri,
        table.bq_table_id,
        job_config=job_config,
        location=BQ_LOCATION,
    )
    job.result()
    bq_table = client.get_table(table.bq_table_id)
    print(f"  ✓ {bq_table.num_rows:,} rows loaded into {table.bq_table_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--grade10-only", action="store_true")
    group.add_argument("--grade12-only", action="store_true")
    args = parser.parse_args()

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    if args.grade10_only:
        _load(client, GRADE10_CLEAN)
    elif args.grade12_only:
        _load(client, GRADE12_CLEAN)
    else:
        _load(client, GRADE10_CLEAN)
        _load(client, GRADE12_CLEAN)

    print("\nDone.")


if __name__ == "__main__":
    main()
