# nirf

NIRF (National Institutional Ranking Framework) data ingestion → BigQuery.

Rankings, admissions/placements, and student-strength data for ~7,500
institutes across 9 disciplines, 2016–2025. Light pass-through pipeline:
already-clean parquet files → GCS → BigQuery. No local transform.

**Source:** [nirfindia.org](https://www.nirfindia.org/) via
[Dataful.in](https://dataful.in). The parquet files we ingest were
pre-processed in the dashboards repo (`pages/nirf_dashboard/build_data.py`),
which is outside this repo's scope.

## Pipeline at a glance

```
nirf/raw/*.parquet            (local; gitignored)
       │ scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/nirf/*.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.nirf_fact_*    (asia-south1, 4 tables)
```

The single source of truth for filenames, GCS URIs, BQ destinations, and
column renames is [`scripts/sources.py`](scripts/sources.py).

## Tables produced

| Table | Rows | Grain |
|---|---:|---|
| `nirf_fact_rankings`  | ~7.5k    | (institute, year, category) |
| `nirf_fact_aggregate` | ~31.7k   | (institute, year, category, academic_year, type) |
| `nirf_fact_strength`  | ~198.7k  | (institute, year, programme, category) |
| `nirf_fact_master`    | ~97.2k   | (institute, year, type, academic_year, category) |

Schemas: [`schemas/*.yaml`](schemas/).

## First-time setup (one-time)

```bash
# GCS bucket (asia-south1 to colocate with the BQ dataset)
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1

# BQ dataset
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources

# Python env
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# Auth (if you haven't already)
gcloud auth application-default login
```

## Running

1. **Drop the parquet files into `raw/`**, using the canonical filenames:
   - `raw/nirf_rankings.parquet`
   - `raw/nirf_aggregate.parquet`
   - `raw/nirf_strength.parquet`
   - `raw/nirf_master.parquet`

2. **Upload to GCS** (also applies column renames for `nirf_fact_aggregate`):

   ```bash
   .venv/bin/python scripts/upload_to_gcs.py             # all four
   .venv/bin/python scripts/upload_to_gcs.py --dry-run   # validate locally
   ```

3. **Load to BQ:**

   ```bash
   .venv/bin/python scripts/load_bq.py
   ```

Both scripts accept `--table <bq_name>` to operate on a single table and
`--dry-run` to preview without side effects.

## Refreshing when NIRF publishes new data

NIRF publishes annually (usually mid-year). The pipeline is set up for
**overwrite-in-place** refreshes:

1. Rebuild the parquet files in dashboards' `build_data.py` against the
   new source CSVs from Dataful.in.
2. Copy the rebuilt parquets into `raw/` (overwriting the old ones).
3. Re-run `upload_to_gcs.py` → `load_bq.py`.

`WRITE_TRUNCATE` makes the BQ load atomic per-table; partial failures
don't leave half-loaded tables. The old data is recoverable for 7 days
via BQ's time travel if a refresh introduces a regression.
