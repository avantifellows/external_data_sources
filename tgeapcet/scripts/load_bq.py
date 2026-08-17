"""
Load TG-EAPCET clean parquet from GCS into BigQuery (WRITE_TRUNCATE).

Pre-reqs:
  - parquet staged at gs://avantifellows-external-data/tgeapcet/clean/
    (run build_clean.py + upload_to_gcs.py first)
  - dataset avantifellows.external_data_sources exists (asia-south1)

Usage:
  python3 scripts/load_bq.py --dry-run
  python3 scripts/load_bq.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_LOCATION, BQ_PROJECT, TABLES, Table


def _load(table: Table, client, dry_run: bool) -> None:
    msg = f"{table.gcs_uri}  →  {table.bq_table_id}"
    if dry_run:
        clust = f"  cluster={table.clustering_fields}" if table.clustering_fields else ""
        print(f"  [dry-run] {msg}{clust}")
        return

    from google.cloud import bigquery

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        clustering_fields=table.clustering_fields or None,
    )
    job = client.load_table_from_uri(
        table.gcs_uri, table.bq_table_id, job_config=job_config, location=BQ_LOCATION
    )
    job.result()
    out = client.get_table(table.bq_table_id)
    print(f"  loaded {out.num_rows:>10,} rows → {table.bq_table_id}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't touch BQ.")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print(f"TG-EAPCET → {BQ_PROJECT}.external_data_sources.*   ({'dry-run' if args.dry_run else 'load'})")
    for t in TABLES:
        _load(t, client, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
