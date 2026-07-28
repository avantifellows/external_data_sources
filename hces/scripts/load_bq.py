#!/usr/bin/env python3
"""
Load the HCES household master from GCS into BigQuery.

Reads:
    gs://avantifellows-external-data/hces/clean/hces_fact_household_master.parquet
Writes (WRITE_TRUNCATE, clustered on state_code, sector_code):
    avantifellows.external_data_sources.hces_fact_household_master

Run upload_to_gcs.py --clean-only first so the GCS parquet is current.

Usage:
    python3 scripts/load_bq.py            # load
    python3 scripts/load_bq.py --dry-run  # print what would load, don't load
"""

import argparse

from google.cloud import bigquery

from sources import BQ_LOCATION, BQ_PROJECT, HOUSEHOLD_MASTER


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t = HOUSEHOLD_MASTER
    print(f"Load {t.gcs_uri}")
    print(f"  -> {t.bq_table_id}  (WRITE_TRUNCATE, cluster: state_code, sector_code)")
    if args.dry_run:
        print("  dry-run: nothing loaded.")
        return

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        clustering_fields=["state_code", "sector_code"],
    )
    job = client.load_table_from_uri(
        t.gcs_uri, t.bq_table_id, job_config=job_config, location=BQ_LOCATION
    )
    job.result()
    bq_table = client.get_table(t.bq_table_id)
    print(f"  ✓ {bq_table.num_rows:,} rows loaded into {t.bq_table_id}")


if __name__ == "__main__":
    main()
