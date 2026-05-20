# CLAUDE.md — nirf/

Guidance for Claude Code when working inside the `nirf/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `nirf/` unless otherwise noted.

## What this folder is

A thin ingestion pipeline for NIRF (National Institutional Ranking Framework)
data — rankings + admissions/placements/strength metrics for ~7,500 institutes
across 9 disciplines, 2016 → 2025. Upstream publishes annually at
[nirfindia.org](https://www.nirfindia.org/); the parquet files we ingest were
pre-processed by [Dataful.in](https://dataful.in) and further normalized in
the dashboards repo (`pages/nirf_dashboard/build_data.py`, which lives
outside this folder).

This is the **light pass-through** template — contrast with
[`plfs/`](../plfs/CLAUDE.md) which owns a heavy local transform. Here the
parquet *is* the clean data, so the pipeline is just:

```
nirf/raw/*.parquet            (local landing zone, gitignored)
       │
       │  scripts/upload_to_gcs.py    (in-mem column rename → upload)
       ▼
gs://avantifellows-external-data/nirf/*.parquet
       │
       │  scripts/load_bq.py          (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.nirf_fact_*    (4 tables, asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).** It
declares the bucket, prefix, BQ destination, and the four-row `TABLES`
registry mapping each parquet → BQ table → column renames. Everything
downstream reads from there.

## Commands

```bash
# Local Python env
python3.13 -m venv .venv
.venv/bin/pip install -r ../requirements.txt

# Drop the parquet files into raw/ first (filenames must match sources.py):
#   raw/nirf_rankings.parquet
#   raw/nirf_aggregate.parquet
#   raw/nirf_strength.parquet
#   raw/nirf_master.parquet

# Stage to GCS (applies column renames for nirf_fact_aggregate)
.venv/bin/python scripts/upload_to_gcs.py
.venv/bin/python scripts/upload_to_gcs.py --table nirf_fact_rankings   # one only
.venv/bin/python scripts/upload_to_gcs.py --dry-run                    # validate locally

# Load GCS → BQ
.venv/bin/python scripts/load_bq.py
.venv/bin/python scripts/load_bq.py --table nirf_fact_rankings
.venv/bin/python scripts/load_bq.py --dry-run
```

One-time prerequisites (run by hand the first time):

```bash
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/*.parquet` | No | Local landing zone before upload. Authoritative copy lives in GCS. |
| `schemas/nirf_fact_*.yaml` | Yes | Per-table column documentation. |
| `scripts/sources.py` | Yes | Bucket, prefix, BQ destination, table registry, column renames. |
| `scripts/upload_to_gcs.py` | Yes | Reads `raw/`, renames columns, uploads to GCS. |
| `scripts/load_bq.py` | Yes | Reads from GCS, loads to BQ with WRITE_TRUNCATE. |
| `README.md` | Yes | Setup + first-time bring-up. |

## BQ schema (what `load_bq.py` produces)

Four tables in `avantifellows.external_data_sources`. Authoritative
column-level docs in [`schemas/*.yaml`](schemas/).

| Table | Rows | Grain |
|---|---:|---|
| `nirf_fact_rankings` | ~7.5k | (institute, year, category) |
| `nirf_fact_aggregate` | ~31.7k | (institute, year, category, academic_year, type) |
| `nirf_fact_strength` | ~198.7k | (institute, year, programme, category) |
| `nirf_fact_master` | ~97.2k | (institute, year, type, academic_year, category) |

## Design calls worth knowing before you change them

- **No transform step in this repo.** The parquet files were built in the
  dashboards repo by `build_data.py` (currently absent from disk; can be
  resurrected from `~/af/dashboards` git history if upstream changes need
  to be re-applied). Don't re-introduce a clean step here — if upstream
  format changes, fix it in dashboards' `build_data.py` and re-export.
- **Overwrite-in-place on new NIRF releases.** NIRF data is mostly
  additive (new year appends rows; historical years don't usually change).
  When NIRF 2026 publishes, replace `raw/*.parquet` with the new files
  using the same names and re-run upload + load. BQ's 7-day time travel
  covers short rollbacks. No snapshot directories.
- **Column renames live in `sources.py`, applied at upload.** Only
  `nirf_fact_aggregate` needs them today (spaces / `%` in column names
  break BQ identifiers). If a new column with an invalid identifier
  appears in any parquet, add a rename map for that table — don't fix
  it in the BQ load step (keeps GCS file == BQ table semantically).
- **`overall_score` and `nirf_rank` are nullable** on rankings + aggregate.
  Today every row has them populated (NIRF only publishes ranked
  institutes), but the schema is set up to accommodate unranked-submitter
  rows once those get scraped from individual college websites.
- **Denormalized everything.** `state`, `city`, `institute_name` appear on
  every fact row. No `nirf_dim_institute` yet. If institute counts grow
  10× (e.g. by adding unranked submitters from PDFs), revisit.

## Pitfalls

- **Don't commit `raw/*.parquet`.** The `.gitignore` enforces this.
  Authoritative copy lives in GCS.
- **Don't change the parquet filenames** in `raw/` without updating
  `sources.py`. The upload script uses the filename as the GCS object name.
- **Don't rely on `academic_year`.** It's nullable on both `aggregate`
  and `master`. Filter with `WHERE academic_year IS NOT NULL` before
  string operations.
- **`institute_name` has variations.** Use multi-keyword `LIKE` / `REGEXP`
  matches, not full-name equality. ("IIT Bombay" appears as "Indian
  Institute Of Technology, Bombay", "Indian Institute Of Technology -
  Bombay", etc. across years.)
- **District codes don't apply.** NIRF has state + city, no district code.
  Don't try to join with anyone else's `*_dim_geo` on district.
