#!/usr/bin/env python3
"""Load the clean parquet into BigQuery. WRITE_TRUNCATE: full-table replace."""
import sys
from pathlib import Path
from google.cloud import bigquery

sys.path.insert(0, str(Path(__file__).parent))
import sources as S

c = bigquery.Client(project=S.BQ_PROJECT)
job = c.load_table_from_uri(
    S.GCS_CLEAN_URI, S.BQ_TABLE_ID,
    job_config=bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition="WRITE_TRUNCATE"),
    location=S.BQ_LOCATION)
job.result()
t = c.get_table(S.BQ_TABLE_ID)
print(f"loaded {t.num_rows:,} rows -> {S.BQ_TABLE_ID}")
