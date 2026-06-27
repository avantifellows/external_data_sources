#!/usr/bin/env python3
"""
Load pb_scert merit list from GCS into BigQuery.

Reads:
    gs://avantifellows-external-data/pb_scert/clean/pb_scert_fact_admission_merit_list.parquet

Writes (WRITE_TRUNCATE):
    avantifellows.external_data_sources.pb_scert_fact_soe_rsms_admission_merit_list

Run upload_to_gcs.py first.

Usage:
    python3 scripts/load_bq.py
"""

import sys
from pathlib import Path

from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.sources import BQ_LOCATION, BQ_PROJECT, MERIT_LIST_CLEAN


def main() -> None:
    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    print(f"Loading {MERIT_LIST_CLEAN.gcs_uri}")
    print(f"  → {MERIT_LIST_CLEAN.bq_table_id}")
    job = client.load_table_from_uri(
        MERIT_LIST_CLEAN.gcs_uri,
        MERIT_LIST_CLEAN.bq_table_id,
        job_config=job_config,
        location=BQ_LOCATION,
    )
    job.result()
    bq_table = client.get_table(MERIT_LIST_CLEAN.bq_table_id)
    print(f"  ✓ {bq_table.num_rows:,} rows loaded into {MERIT_LIST_CLEAN.bq_table_id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
