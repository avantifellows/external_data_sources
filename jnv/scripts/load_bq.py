#!/usr/bin/env python3
"""
Load all JNV clean data from GCS into BigQuery.

Reads (all six tables by default):
    gs://avantifellows-external-data/jnv/clean/jnv_fact_jee_results.parquet
    gs://avantifellows-external-data/jnv/clean/jnv_fact_neet_results.parquet
    gs://avantifellows-external-data/jnv/clean/jnv_fact_selection_test_results.parquet
    gs://avantifellows-external-data/jnv/clean/jnv_fact_ei_asset_test_results.parquet
    gs://avantifellows-external-data/jnv/clean/jnv_fact_board_results_10th.parquet
    gs://avantifellows-external-data/jnv/clean/jnv_fact_board_results_12th.parquet

Writes (WRITE_TRUNCATE):
    avantifellows.external_data_sources.jnv_fact_jee_results
    avantifellows.external_data_sources.jnv_fact_neet_results
    avantifellows.external_data_sources.jnv_fact_selection_test_results
    avantifellows.external_data_sources.jnv_fact_ei_asset_test_results
    avantifellows.external_data_sources.jnv_fact_board_results_10th
    avantifellows.external_data_sources.jnv_fact_board_results_12th

Run upload_to_gcs.py first to ensure the GCS files are up to date.

Usage:
    python3 scripts/load_bq.py                      # load all six tables
    python3 scripts/load_bq.py --jee-only
    python3 scripts/load_bq.py --neet-only
    python3 scripts/load_bq.py --jnvst-only
    python3 scripts/load_bq.py --ei-asset-test-only
    python3 scripts/load_bq.py --board-results-10th-only
    python3 scripts/load_bq.py --board-results-12th-only
"""

import argparse

from google.cloud import bigquery

from sources import BOARD_RESULTS_10TH_CLEAN, BOARD_RESULTS_12TH_CLEAN, BQ_LOCATION, BQ_PROJECT, EI_ASSET_TEST_CLEAN, JEE_CLEAN, JNVST_CLEAN, NEET_CLEAN


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
    group.add_argument("--jee-only",   action="store_true")
    group.add_argument("--neet-only",  action="store_true")
    group.add_argument("--jnvst-only",         action="store_true")
    group.add_argument("--ei-asset-test-only",       action="store_true")
    group.add_argument("--board-results-10th-only",  action="store_true")
    group.add_argument("--board-results-12th-only",  action="store_true")
    args = parser.parse_args()

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    if args.jee_only:
        _load(client, JEE_CLEAN)
    elif args.neet_only:
        _load(client, NEET_CLEAN)
    elif args.jnvst_only:
        _load(client, JNVST_CLEAN)
    elif args.ei_asset_test_only:
        _load(client, EI_ASSET_TEST_CLEAN)
    elif args.board_results_10th_only:
        _load(client, BOARD_RESULTS_10TH_CLEAN)
    elif args.board_results_12th_only:
        _load(client, BOARD_RESULTS_12TH_CLEAN)
    else:
        _load(client, JEE_CLEAN)
        _load(client, NEET_CLEAN)
        _load(client, JNVST_CLEAN)
        _load(client, EI_ASSET_TEST_CLEAN)
        _load(client, BOARD_RESULTS_10TH_CLEAN)
        _load(client, BOARD_RESULTS_12TH_CLEAN)

    print("\nDone.")


if __name__ == "__main__":
    main()
