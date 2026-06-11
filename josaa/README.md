# josaa/

JoSAA (Joint Seat Allocation Authority) engineering seat-allotment cutoffs —
opening + closing ranks for every IIT/NIT/IIIT/GFTI seat bucket, every
counselling round, 2016 → latest. ~523k rows.

New here? Read [`schemas/README.md`](schemas/README.md) — "JoSAA in 60
seconds" — before querying. Domain orientation for editing the pipeline is
in [`CLAUDE.md`](CLAUDE.md).

## Pipeline shape

This is a **light parse** source: the raw is already tabular (per-round CSVs
from the JoSAA portal), so the pipeline just unions, normalizes, and types.

```
josaa/raw/<year>_R<round>.csv         (62 files, gitignored; scraper output)
       │  scripts/build_clean.py       union + snake_case + parse prep ranks + type
       ▼
josaa/clean/josaa_fact_cutoffs.parquet (gitignored)
       │  scripts/upload_to_gcs.py     stage raw + clean to GCS
       ▼
gs://avantifellows-external-data/josaa/{raw,clean}/
       │  scripts/load_bq.py           load_table_from_uri, PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.josaa_fact_cutoffs   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py)** —
bucket, prefix, BQ destination, column renames, table registry.

## Upstream / provenance

The raw per-(year, round) CSVs are produced by the **JoSAA scraper in the
College DB repo** (`josaa-ranks/scripts/01_scrape_archive.py` +
`02_scrape_current.py`), which hits the JoSAA portal's public OpRank pages.
That scraper is the upstream; this source consumes its output. We do **not**
duplicate the scraper here — when JoSAA publishes a new cycle, run the
College DB scraper, then land its `extracted_data/raw/*.csv` into `josaa/raw/`.

> Raw → clean → BQ here strips JoSAA down to the neutral published fact.
> Avanti's enrichment (salary tier, `college_type`, canonical college ids,
> NIRF salary) stays in College DB — it is opinion, not source data.

## Commands

```bash
# Local Python env
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# 1. Land the scraper output (filenames must match <year>_R<round>.csv):
#    cp "../../College DB/josaa-ranks/extracted_data/raw/"*.csv raw/

# 2. Build the clean parquet
.venv/bin/python scripts/build_clean.py --dry-run     # summary only
.venv/bin/python scripts/build_clean.py               # writes clean/

# 3. Stage to GCS
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py --raw       # clean + raw provenance

# 4. Load GCS → BQ
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

One-time prerequisites (shared across sources; run once):

```bash
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/<year>_R<round>.csv` | No | Scraper output landing zone. Authoritative copy in GCS. |
| `clean/*.parquet` | No | Built by `build_clean.py`. Authoritative copy in GCS. |
| `scripts/sources.py` | Yes | Bucket, prefix, BQ destination, renames, table registry. |
| `scripts/build_clean.py` | Yes | raw CSVs → clean parquet (the auditable recipe). |
| `scripts/upload_to_gcs.py` | Yes | Stage raw + clean to GCS. |
| `scripts/load_bq.py` | Yes | GCS → BQ, WRITE_TRUNCATE. |
| `schemas/*.yaml` | Yes | Per-table teaching docs. |
| `schemas/README.md` | Yes | "JoSAA in 60 seconds" primer. |
| `codemaps/*.csv` | Yes | quota + seat_type lookups. |

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `josaa_fact_cutoffs` | (institute, program, quota, seat_type, gender, year, round) | ~523k |
