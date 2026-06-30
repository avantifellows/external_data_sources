"""
Load clean Dakshana parquet files from GCS into BigQuery (external_data_sources, asia-south1).

Loads both Dakshana tables defined in sources.py — dakshana_fact_ncst_results and
dakshana_fact_reported_results — each with WRITE_TRUNCATE (idempotent), clustered on its filter columns.

Pre-reqs: dataset avantifellows.external_data_sources exists; clean parquet already staged on GCS
(scripts/upload_to_gcs.py). Do NOT run against production without an explicit go — stage + review first.

Usage:
  python3 scripts/load_bq.py --dry-run                              # show what would happen
  python3 scripts/load_bq.py --table dakshana_fact_reported_results
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_LOCATION, TABLES, Table


def _load(table: Table, client, dry_run: bool) -> None:
    msg = f"{table.gcs_uri} → {table.bq_table_id}  (cluster: {', '.join(table.clustering) or 'none'})"
    if dry_run:
        print(f"  [dry-run] {msg}")
        return
    from google.cloud import bigquery
    cfg = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        clustering_fields=list(table.clustering) or None,
    )
    job = client.load_table_from_uri(table.gcs_uri, table.bq_table_id, job_config=cfg, location=BQ_LOCATION)
    job.result()
    print(f"  loaded {client.get_table(table.bq_table_id).num_rows:>10,} rows → {table.bq_table_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    chosen = [t for t in TABLES if t.bq_name == args.table] if args.table else TABLES
    if args.table and not chosen:
        raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")
    client = None
    if not args.dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project="avantifellows")
    for t in chosen:
        _load(t, client, args.dry_run)
    print("done.")


if __name__ == "__main__":
    main()
