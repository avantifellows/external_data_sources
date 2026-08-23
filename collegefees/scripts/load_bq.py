"""Load the clean parquet from GCS into BigQuery (WRITE_TRUNCATE, idempotent)."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_LOCATION, BQ_PROJECT, BQ_TABLE, GCS_CLEAN

def main() -> None:
    from google.cloud import bigquery
    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
    job = client.load_table_from_uri(
        GCS_CLEAN, BQ_TABLE,
        job_config=bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE),
        location=BQ_LOCATION)
    job.result()
    print(f"  loaded {client.get_table(BQ_TABLE).num_rows:,} rows → {BQ_TABLE}")

if __name__ == "__main__":
    main()
