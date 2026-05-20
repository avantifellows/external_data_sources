#!/usr/bin/env python3
"""
Load JNV JEE Mains clean data from GCS into BigQuery.

Reads:
    gs://avantifellows-external-data/jnv/clean/jnv_fact_jee_mains_results.parquet

Writes (WRITE_TRUNCATE):
    avantifellows.external_data_sources.jnv_fact_jee_mains_results

Run upload_to_gcs.py first to ensure the GCS file is up to date.

Usage:
    python3 scripts/load_bq.py
"""

from google.cloud import bigquery

from sources import BQ_LOCATION, BQ_PROJECT, JEE_MAINS_CLEAN


def main() -> None:
    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    print(f"Loading {JEE_MAINS_CLEAN.gcs_uri}")
    print(f"  → {JEE_MAINS_CLEAN.bq_table_id}")

    job = client.load_table_from_uri(
        JEE_MAINS_CLEAN.gcs_uri,
        JEE_MAINS_CLEAN.bq_table_id,
        job_config=job_config,
        location=BQ_LOCATION,
    )
    job.result()

    table = client.get_table(JEE_MAINS_CLEAN.bq_table_id)
    print(f"  ✓ {table.num_rows:,} rows loaded into {JEE_MAINS_CLEAN.bq_table_id}")


if __name__ == "__main__":
    main()
