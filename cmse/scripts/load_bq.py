"""
Load the CMS-E clean parquet from GCS into BigQuery.

Idempotent: every table is WRITE_TRUNCATE, so re-running replaces rather than
appends. Fact tables are clustered on the cuts this source exists to serve —
state and gender first.

Parquet must already be staged: run upload_to_gcs.py first.

Usage:
  python3 scripts/load_bq.py
  python3 scripts/load_bq.py --table cmse_fact_student
  python3 scripts/load_bq.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sources as S


def _load(table: S.Table, client, dry_run: bool) -> None:
    msg = f"{table.gcs_uri} → {table.bq_table_id}"
    if dry_run:
        print(f"  [dry-run] {msg}")
        print(f"            clustering: {', '.join(table.clustering_fields)}")
        return

    from google.cloud import bigquery

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        clustering_fields=list(table.clustering_fields),
    )
    job = client.load_table_from_uri(
        table.gcs_uri, table.bq_table_id, job_config=job_config, location=S.BQ_LOCATION
    )
    job.result()
    out = client.get_table(table.bq_table_id)
    print(f"  loaded {out.num_rows:>9,} rows x {len(out.schema):>3} cols → {table.bq_table_id}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--table", default=None, help="Load only this BQ table")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't touch BQ")
    args = ap.parse_args()

    chosen = S.TABLES
    if args.table:
        chosen = [t for t in S.TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(
                f"unknown table {args.table!r}; known: {[t.bq_name for t in S.TABLES]}"
            )

    client = None
    if not args.dry_run:
        from google.cloud import bigquery
        client = bigquery.Client(project=S.BQ_PROJECT, location=S.BQ_LOCATION)

    print(f"CMS-E → {S.BQ_PROJECT}.{S.BQ_DATASET}.*  "
          f"({'dry-run' if args.dry_run else 'load'})")
    for t in chosen:
        _load(t, client, args.dry_run)
    print("done.")


if __name__ == "__main__":
    main()
