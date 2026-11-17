#!/usr/bin/env python3
"""
Load the NDC clean parquet from GCS into BigQuery (WRITE_TRUNCATE):
  ndc_dim_dental_colleges, ndc_fact_dental_seats

Usage:
  python3 scripts/load_bq.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_DATASET, BQ_LOCATION, BQ_PROJECT, GCS_BUCKET, GCS_PREFIX

TABLES = ["ndc_dim_dental_colleges", "ndc_fact_dental_seats"]


def main() -> None:
    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
    cfg = bigquery.LoadJobConfig(source_format=bigquery.SourceFormat.PARQUET,
                                 write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE)
    for t in TABLES:
        uri = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{t}.parquet"
        dest = f"{BQ_PROJECT}.{BQ_DATASET}.{t}"
        client.load_table_from_uri(uri, dest, job_config=cfg, location=BQ_LOCATION).result()
        print(f"  loaded {client.get_table(dest).num_rows:>6,} rows → {dest}")


if __name__ == "__main__":
    main()
