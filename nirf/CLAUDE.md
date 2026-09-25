# CLAUDE.md — nirf/

Guidance for Claude Code when working inside the `nirf/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `nirf/` unless otherwise noted.

## What this folder is

An ingestion pipeline for NIRF (National Institutional Ranking Framework)
data — rankings + admissions/placements/strength metrics for ~7,500 institutes
across 9 disciplines, 2016 → 2025. Upstream publishes annually at
[nirfindia.org](https://www.nirfindia.org/).

Two provenances coexist here (see README → Data provenance):

- **First-party (Engineering, Medical, University, College, Law)**: `fetch_dcs.py` downloads NIRF's own
  ranking/band pages and per-institute DCS PDFs (2019–2025 editions);
  `parse_dcs.py` turns them into `extracted/*.csv`. These feed the five
  `nirf_*dcs*`/`nirf_dim_participants` tables AND replace the Dataful rows
  inside `nirf_fact_rankings` for those five categories
  (`record_source = 'nirfindia.org'`).
- **Dataful vintage (everything else)**: `raw/*.parquet` is Dataful.in's
  scrape of NIRF's PDFs, further transformed by a `build_data.py` that no
  longer exists. Read **[README.md → Data provenance](README.md#data-provenance)**
  and **[Known limitations](README.md#known-limitations)** before answering
  any analytical question with those tables — several limits (PG coverage,
  `institute_id` instability) are invisible in the data itself.

DCS-table gotchas that bite queries:

- Filter `NOT superseded` on `nirf_fact_dcs_placements`/`_intake` unless you
  specifically want every edition's restatement of the same academic year.
- Medical MBBS rows legitimately have `students_placed = 0` and
  `median_salary = 0` — graduates proceed to internship, not "placement".
- Band institutes exist in `nirf_fact_rankings` with NULL `institute_id`,
  NULL score, and `rank_band` like `'101-150'` — grain there is (name, city).
- College PDFs exist only for the ranked top 100 per edition; band colleges
  (101–300) have ranking rows but no DCS rows. College ids end in the AISHE
  code (`IR-C-C-6355` = Miranda House, C-6355).
- Law ranks only a short top list (15–40 per edition) with no band
  pages; its placements are `program_level = 'UG-5Y'` (the integrated LLB).
- A NIRF page typo that breaks a grain goes in `KNOWN_SOURCE_TYPOS`
  (`build_clean.py`), dropped by exact match and printed. Never relax the
  conflict check instead.
- 2016 Engineering `institute_id`s are the official `IR17-*` codes, which do
  NOT match Dataful-era 2016 ids (`NIRF-ENGG-*`) other tables may carry.

```
nirf/raw/*.parquet            (local landing zone, gitignored)
       │
       │  scripts/build_clean.py      (dedup + rebuild aggregate + renames)
       ▼
nirf/clean/*.parquet          (gitignored)
       │
       │  scripts/upload_to_gcs.py    (byte-for-byte upload)
       ▼
gs://avantifellows-external-data/nirf/clean/*.parquet
       │
       │  scripts/load_bq.py          (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.nirf_*    (9 tables, asia-south1)
```

First-party inputs run `fetch_dcs.py` → `raw/dcs/` → `parse_dcs.py` →
`extracted/*.csv` before `build_clean.py`; the raw haul is staged to GCS as
zips via `upload_to_gcs.py --dcs-raw` (and `--extracted` for the CSVs).

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).** It
declares the bucket, prefix, BQ destination, and the nine-row `TABLES`
registry mapping each parquet → BQ table → **grain** → column renames.
Everything downstream reads from there; `build_clean.py` deduplicates on the
declared grain, so fixing a wrong grain there fixes the dedup too.

## Commands

```bash
# Local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Fetch the raw parquets into raw/ (gitignored; authoritative copies in GCS).
# nirf/raw/nirf_aggregate.parquet exists too but is NOT an input — build_clean.py
# rebuilds it; that object is only the pre-deduplication historical record.
gcloud storage cp 'gs://avantifellows-external-data/nirf/raw/nirf_rankings.parquet' raw/
gcloud storage cp 'gs://avantifellows-external-data/nirf/raw/nirf_master.parquet'   raw/
gcloud storage cp 'gs://avantifellows-external-data/nirf/raw/nirf_strength.parquet' raw/

# Build clean/ — dedups, rebuilds aggregate, applies renames.
# Read the output: it reports dedup counts and prints every summed conflict.
.venv/bin/python scripts/build_clean.py
.venv/bin/python scripts/build_clean.py --table nirf_fact_master        # one only
.venv/bin/python scripts/build_clean.py --dry-run                      # write nothing

# Stage clean/ to GCS
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
| `raw/*.parquet` | No | Local landing zone. Authoritative copy lives in GCS. |
| `clean/*.parquet` | No | Output of `build_clean.py` — the exact bytes that reach GCS + BQ. |
| `schemas/nirf_fact_*.yaml` | Yes | Per-table column documentation + known limitations. |
| `scripts/sources.py` | Yes | Bucket, prefix, BQ destination, table registry, grains, renames. |
| `scripts/fetch_dcs.py` | Yes | First-party fetch: ranking/band/ALL pages + DCS PDFs (CDN probe, rate-limit canary). |
| `scripts/parse_dcs.py` | Yes | `raw/dcs/` → `extracted/*.csv`. |
| `raw/dcs/`, `extracted/` | No | First-party haul + parsed CSVs; staged to GCS via `--dcs-raw` / `--extracted`. |
| `scripts/build_clean.py` | Yes | **The only transform.** Dedups, rebuilds aggregate, renames. |
| `scripts/upload_to_gcs.py` | Yes | Uploads `clean/` byte-for-byte to GCS. No transform. |
| `scripts/load_bq.py` | Yes | Reads from GCS, loads to BQ with WRITE_TRUNCATE. |
| `requirements.txt` | Yes | Python deps. |
| `README.md` | Yes | Provenance, known limitations, setup, run instructions. |

## BQ schema (what `load_bq.py` produces)

Nine tables in `avantifellows.external_data_sources`. Authoritative
column-level docs in [`schemas/*.yaml`](schemas/) and the data-assistant
repo's `docs/schemas/external/nirf_*.yaml`.

| Table | Rows | Grain |
|---|---:|---|
| `nirf_fact_rankings` | 10,707 | (institute, year, category); band rows (name, city) |
| `nirf_fact_master` | 90,707 | (institute, year, category, type, academic_year, metric) |
| `nirf_fact_strength` | 186,012 | (institute, year, category, programme, metric) |
| `nirf_fact_aggregate` | 31,717 | (institute, year, category, academic_year, type) |
| `nirf_fact_dcs_placements` | 26,670 | (edition, discipline, institute, program level, graduating AY) |
| `nirf_fact_dcs_intake` | 28,100 | (edition, discipline, institute, program level, AY) |
| `nirf_fact_dcs_strength` | 8,394 | (edition, discipline, institute, program level) |
| `nirf_fact_dcs_institution` | 3,119 | (edition, discipline, institute) |
| `nirf_dim_participants` | 31,672 | (year, discipline, name, city) |

Every grain is unique — `build_clean.py` enforces it and fails otherwise.

## Design calls worth knowing before you change them

- **`build_clean.py` is the only transform.** It exists because the upstream
  ships duplicate rows and the old aggregate summed them. Don't move
  logic into `upload_to_gcs.py` or the BQ load — keeping the transform in one
  place is what makes `clean/` == GCS == BQ, and therefore auditable.
  (The predecessor lived in dashboards' `build_data.py`, deleted Feb 2026 in
  commit `819e7b2`; recover it with
  `git show 819e7b2^:pages/nirf_dashboard/build_data.py` if you need to know
  what the old numbers were built from.)
- **Never aggregate when pivoting master.** The `aggfunc='sum'` in the old
  build is precisely what doubled counts and median salary. `build_clean.py`
  asserts the master grain is unique *before* pivoting and uses `max`. If that
  assertion ever fires, fix the dedup — don't relax the assertion.
- **Dedup conflicts are table-specific, not a global rule.** `strength` may be
  summed (pure counts); `master` may not (it mixes `value in Rupees`). The
  `SUMMABLE` set in `build_clean.py` encodes this. Adding a table there without
  checking its `unit` column would reintroduce the median-salary bug.
- **`nirf_fact_aggregate` is derived, not ingested.** It has no `raw/` input.
  If you need a metric it lacks, pivot clean `master` — don't hand-edit the
  aggregate.
- **Overwrite-in-place on new NIRF releases.** BQ's 7-day time travel covers
  short rollbacks. No snapshot directories. ⚠️ But there is no supported path to
  refresh `raw/` — see README → Refreshing.
- **`overall_score` and `nirf_rank` are nullable** on rankings + aggregate.
  First-party band rows (101–150 etc.) have both NULL, with `rank_band` set.
- **Denormalized everything.** `state`, `city`, `institute_name` appear on
  every fact row. No `nirf_dim_institute` yet. If institute counts grow
  10× (e.g. by adding unranked submitters from PDFs), revisit.

## Pitfalls

- **Don't commit `raw/*.parquet` or `clean/*.parquet`.** The `.gitignore`
  enforces this. Authoritative copies live in GCS.
- **Don't change the parquet filenames** without updating `sources.py`. The
  same filename is used in `raw/`, `clean/`, and as the GCS object name.
- **⚠️ Don't join on `institute_id` across years.** It is **not** stable:
  2016 `NIRF-*`, 2017 `IR17-*`, 2018 `IR-1..7-*`, 2019+ `IR-*`. 492 of 1,178
  institutes carry more than one id (IIM Ahmedabad has four). Longitudinal work
  needs name-based resolution. The schema used to claim the id was stable — it
  isn't.
- **⚠️ Don't compare UG and PG over time.** `master` holds PG outcomes for only
  three academic years (2021-22 → 2023-24) vs ten for UG. PG "appearing" in
  2021-22 is an extraction artifact. See README → Known limitations.
- **⚠️ Don't inner-join `master` to `rankings`.** 93 institutes never appear in
  `master`, plus scattered single-year gaps. Left-join from `rankings`.
- **Don't `SELECT DISTINCT` or `MAX()` your way around duplicates.** The clean
  tables have no duplicates. If you are reading the *old* BQ data or `raw/`,
  note that a blind `MAX()` deletes a real 73-student programme at
  `IR-O-U-0383` (2020) — those two rows are both in NIRF's scorecard.
- **Don't rely on `academic_year`.** It's nullable on both `aggregate`
  and `master`. Filter with `WHERE academic_year IS NOT NULL` before
  string operations.
- **`institute_name` has variations, and ours is synthetic** — the longest name
  per id across three source files, not what NIRF published. Use multi-keyword
  `LIKE` / `REGEXP`, not full-name equality.
- **On Dataful rows `nirf_rank` is recomputed by us**, not NIRF's published rank
  (first-party rows carry NIRF's own, verbatim in `rank_raw`). It agrees on
  spot-checks, but 165 rank values are shared by ≥2 institutes because ties use
  `method='min'`.
- **District codes don't apply.** NIRF has state + city, no district code.
  Don't try to join with anyone else's `*_dim_geo` on district.
