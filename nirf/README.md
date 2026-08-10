# nirf

NIRF (National Institutional Ranking Framework) data ingestion → BigQuery.

Rankings, admissions/placements, and student-strength data for ~7,500
institutes across 9 disciplines, 2016–2025.

**⚠️ Read [Data provenance](#data-provenance) before using these tables for
analysis.** What we ingest is not raw NIRF data, and it has known coverage
limits that are not visible in the tables themselves.

## Pipeline at a glance

```
nirf/raw/*.parquet            (local; gitignored)
       │ scripts/build_clean.py     ← dedup + rebuild aggregate
       ▼
nirf/clean/*.parquet          (local; gitignored)
       │ scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/nirf/clean/*.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.nirf_fact_*    (asia-south1, 4 tables)
```

The single source of truth for filenames, GCS URIs, BQ destinations, table
grains, and column renames is [`scripts/sources.py`](scripts/sources.py).
`build_clean.py` is the only place data is transformed — `clean/`, the GCS
objects and the BQ tables are byte-identical.

## Tables produced

| Table | Rows | Grain | Built from |
|---|---:|---|---|
| `nirf_fact_rankings`  | 7,504   | (institute, year, category) | `raw/nirf_rankings.parquet` |
| `nirf_fact_master`    | 90,707  | (institute, year, category, type, academic_year, metric) | `raw/nirf_master.parquet`, deduped |
| `nirf_fact_strength`  | 186,012 | (institute, year, category, programme, metric) | `raw/nirf_strength.parquet`, deduped |
| `nirf_fact_aggregate` | 31,718  | (institute, year, category, academic_year, type) | **derived** — pivot of clean master + rankings |

Every table's grain is unique — `build_clean.py` enforces it and fails if not.
Schemas: [`schemas/*.yaml`](schemas/).

## Data provenance

**These are not raw NIRF files.** Three layers sit between NIRF and BigQuery:

```
NIRF publishes  ①  per-institute scorecard PDFs   ②  ranking lists (HTML: score, rank, 5 parameter scores)
                              │
Dataful.in      scrapes both into CSVs  ── a Factly Media & Research commercial product
                              │
dashboards      build_data.py transforms them into the parquets in raw/
                              │
                    nirf_*.parquet  →  this pipeline
```

`build_data.py` was **deleted** from the dashboards repo in Feb 2026 (commit
`819e7b2`) along with the source CSVs. It is recoverable with
`git show 819e7b2^:pages/nirf_dashboard/build_data.py`. It did more than
reformat, and its choices are baked into our tables:

- **`institute_name` is synthetic** — the *longest* name per `institute_id`
  across three files, not the name NIRF published. Our data says
  "Kalasalingam Academy of Research and **Higher** Education"; NIRF says
  "Kalasalingam Academy of Research and Education".
- **`nirf_rank` is recomputed by us**, not NIRF's published rank —
  `groupby([year, category])['overall_score'].rank(method='min')`. Spot-checks
  agree with NIRF (Kalasalingam 2025 → 33, Amrita → 23), but **165 rank values
  are shared by ≥2 institutes** under `method='min'` and NIRF may break ties
  differently.
- **NIRF's five parameter scores are discarded** (TLR, RPC, GO, OI,
  PERCEPTION). `build_data.py` keeps only `score_category == 'Overall Score'`.
- **`nirf_fact_aggregate` is our own construct**, not a NIRF artifact.

## Known limitations

Verified against NIRF's own scorecard PDFs in Aug 2026. **Values are accurate
where present** — 384/384 sampled `strength` cells matched the official
scorecards exactly, and geographic splits reconcile. The problems are coverage
and identity, not correctness.

| # | Limitation | Impact |
|---|---|---|
| 1 | **PG outcomes cover only 3 academic years** (2021-22 → 2023-24, 742 institutes). UG covers ten (2014-15 → 2023-24). Dataful did not extract PG into `master` until its 2025 refresh. | PG trend analysis is impossible. Any time series **pooling UG and PG is biased** — PG "appears" in 2021-22 as an extraction artifact, not a real change. NIRF publishes ~9 academic years of PG per institute; we hold 3. |
| 2 | **`institute_id` is NOT stable across years**, though `nirf_fact_rankings.yaml` used to claim it was. 2016 `NIRF-*`, 2017 `IR17-*`, 2018 `IR-1..7-*`, 2019+ `IR-*`. **492 of 1,178 institutes carry more than one id** (IIM Ahmedabad has four). | Joining on `institute_id` across years silently drops 2016–2018 or splits one institute into several. Resolve on normalised `institute_name` for longitudinal work. |
| 3 | **Completeness vs the source PDFs is unverified.** At least one confirmed loss: IR-O-U-0589's 2020 scorecard publishes 15 placement rows across five programmes; `master` holds one. Union across vintages recovers much of it (NIRF republishes each academic year in three consecutive editions), so the true loss rate is unknown. | Treat placement coverage per institute-vintage as partial. Don't assume a missing programme means the institute didn't offer it. |
| 4 | **93 institutes never appear in `master`** in any year, plus scattered single-year misses (e.g. Jadavpur University 2022, which has data in every other year). | `master` is not a complete cover of ranked institutes. Left-join from `rankings`, don't inner-join. |
| 5 | **Upstream is a dead end.** Dataful is a paid product and the exact dataset slug `build_data.py` used now returns "Record not found". | We cannot re-pull a corrected extract. Fixing anything upstream is not an option; fix it in `build_clean.py`. |

Duplicate rows — which inflated every measure in `nirf_fact_aggregate` — **are
fixed** by `build_clean.py`; see below.

### The escape hatch

NIRF's own scorecards are fetchable and parseable, and would fix every item
above by construction. Verified Aug 2026:

- Ranking lists: `Rankings/<year>/<Category>Ranking.html` — **2016–2025 all 200**.
- Scorecards: `nirfpdfcdn/<year>/pdf/<Category>/<institute_id>.pdf` — **2018–2025
  all 200** (2016–2017 predate the CDN; `master`/`strength` have no rows before
  2019 anyway, so nothing is lost).
- `pdfplumber` parses 2019/2022/2025 cleanly. **2018 is a different legacy
  schema** and needs a second extractor. Some categories omit sections (a 2025
  College scorecard has no PhD block), so sections must be optional.
- ~6,700 PDFs for 2018–2025, ~10 KB each ≈ 70 MB. No `robots.txt`.
- NIRF 2026 is **not yet published** — submission closed Mar 2026, the site's
  ranking nav stops at 2025 — so building this before it lands is cheap timing.

`nmc/` (single PDF) and `moe/` (multi-PDF, two extractors) are the reference
implementations. Not built; tracked separately from the deduplication fix.

## What `build_clean.py` fixes

The upstream repeats rows 2–3× for some institutes, and the old aggregate
pivoted `master` with `aggfunc='sum'` — so duplicated rows were **added**,
doubling counts and, nonsensically, median salary.

| Table | Before | After | Removed |
|---|---:|---:|---|
| `nirf_fact_master` | 97,166 | 90,707 | 6,459 (5,049 byte-identical + 1,410 differing only on `city`) |
| `nirf_fact_strength` | 198,660 | 186,012 | 12,648 (9,624 byte-identical + 3,000 `city`-only), plus 24 grain keys summed |
| `nirf_fact_aggregate` | 31,718 | 31,718 | row count unchanged; **1,790 rows had inflated measures** |

`percentage_placed` and `admission_rate` changed on **zero** rows — they are
ratios of two equally-inflated numbers, so the factor always cancelled. Only
counts and `median_salary` were ever wrong.

**Deduplication policy**, applied per table by `build_clean.py`:

- **Byte-identical rows** → collapsed. Not present in NIRF's scorecards, so
  they are purely an ingestion artifact.
- **Same grain, same value, differing on a descriptive column** (`city` has two
  spellings for some institutes) → collapsed, first kept.
- **Same grain, conflicting value** → depends on the table:
  - `nirf_fact_strength` → **summed**, and every collapsed key is printed on
    each run. NIRF's `programme` is a *duration bucket*, not a programme name,
    so an institute with two different 2-year PG programmes legitimately files
    two rows under `PG [2 Year Program(s)]` — Punjabi University's 2020
    scorecard does exactly that (`Total students` 3,307 **and** 73). Every
    strength metric is an additive count (198,660/198,660 rows are
    `value in Absolute Number`), so summing yields the bucket total and drops
    nobody. Today: 48 rows / 24 grain keys, all `IR-O-U-0383`, 2020.
    ⚠️ A blind `DISTINCT` or `MAX()` here would silently delete a real
    73-student programme.
  - `nirf_fact_master` → **hard error**. Master mixes units (14,711 rows are
    `value in Rupees`) and a summed median is meaningless. There are no such
    conflicts today; if one appears it needs a human decision.

## First-time setup (one-time)

```bash
# GCS bucket (asia-south1 to colocate with the BQ dataset)
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1

# BQ dataset
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources

# Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Auth (if you haven't already)
gcloud auth application-default login
```

## Running

1. **Put the raw parquets in `raw/`.** They are gitignored; the authoritative
   copies live in GCS under `nirf/raw/`:

   ```bash
   gcloud storage cp 'gs://avantifellows-external-data/nirf/raw/nirf_rankings.parquet' raw/
   gcloud storage cp 'gs://avantifellows-external-data/nirf/raw/nirf_master.parquet'   raw/
   gcloud storage cp 'gs://avantifellows-external-data/nirf/raw/nirf_strength.parquet' raw/
   ```

   `nirf/raw/nirf_aggregate.parquet` also exists in GCS but is **not** an input —
   `build_clean.py` rebuilds `nirf_fact_aggregate` from the clean master. It's
   kept only as the historical record of what BQ held before the duplication was
   fixed.

2. **Build the clean parquets:**

   ```bash
   .venv/bin/python scripts/build_clean.py              # all four
   .venv/bin/python scripts/build_clean.py --dry-run    # build in-mem, write nothing
   ```

   Read the output. It reports how many rows were deduplicated and prints every
   conflicting key it summed.

3. **Upload to GCS, then load to BQ:**

   ```bash
   .venv/bin/python scripts/upload_to_gcs.py
   .venv/bin/python scripts/load_bq.py
   ```

All three scripts accept `--table <bq_name>` for a single table and `--dry-run`
to preview without side effects.

## Refreshing when NIRF publishes new data

`WRITE_TRUNCATE` makes the BQ load atomic per-table; partial failures don't
leave half-loaded tables, and the old data is recoverable for 7 days via BQ
time travel.

Because `build_data.py` and the Dataful CSVs are both gone (see
[Data provenance](#data-provenance)), there is **no supported path to refresh
`raw/` from upstream**. For NIRF 2026 the realistic options are to build the
scorecard fetcher + parser described in [The escape hatch](#the-escape-hatch),
or to re-acquire the CSVs from Dataful (paid, and the old dataset slug is dead).
Either way it is a decision, not a re-run — don't assume step 1 above can be
repeated for a new year.
