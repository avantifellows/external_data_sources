#!/usr/bin/env python3
"""
Load Dakshana NCST clean data from GCS into BigQuery.

Reads:
    gs://avantifellows-external-data/dakshana/clean/dakshana_fact_ncst_results.parquet

Writes (WRITE_TRUNCATE):
    avantifellows.external_data_sources.dakshana_fact_ncst_results

Run upload_to_gcs.py first to ensure the GCS file is up to date.

Usage:
    python3 scripts/load_bq.py
"""

import sys
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import BQ_LOCATION, BQ_PROJECT, NCST_CLEAN


def main() -> None:
    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    print(f"Loading {NCST_CLEAN.gcs_uri}")
    print(f"  → {NCST_CLEAN.bq_table_id}")
    job = client.load_table_from_uri(
        NCST_CLEAN.gcs_uri,
        NCST_CLEAN.bq_table_id,
        job_config=job_config,
        location=BQ_LOCATION,
    )
    job.result()
    bq_table = client.get_table(NCST_CLEAN.bq_table_id)
    print(f"  ✓ {bq_table.num_rows:,} rows loaded into {NCST_CLEAN.bq_table_id}")
    print("\nDone.")


if __name__ == "__main__":
    main()