# udise

UDISE+ school data → BigQuery.

**Two unrelated UDISE+ products live in this folder.** Do not confuse them:

| | Grain | Status |
|---|---|---|
| **Report 4000** (dashboard cross-tab) | state × management × category × class × gender, AY 2024-25 | **ingested** → `udise_fact_enrolment`, 42,270 rows |
| **DSP microdata** (Data Sharing Portal) | **one row per school**, 5 editions 2020-21 → 2025-26 | **ingested** → 4 tables, see [DSP](#dsp-microdata-school-level) below |

The DSP release is the one carrying **BPL and EWS enrolment per school**, which is
the income/poverty dimension AISHE has no equivalent for. ~1.7 GB of zips in
`raw/dsp/` (gitignored); registered in `sources.py` as `DSP_YEARS` / `DSP_GROUPS`.

The next section describes Report 4000; DSP is documented [further down](#dsp-microdata-school-level).

School enrolment by state × school-management × school-category × location ×
class × gender, AY 2024-25. The source is a wide dashboard cross-tab; this
reshapes it to one long-form fact, then stages parquet → GCS → BQ.

**Source:** UDISE+ Dashboard *Report 4000 — Enrolment by Location, School
Category and School Management for Each Class & Level of Education*, AY 2024-25,
exported from [dashboard.udiseplus.gov.in](https://dashboard.udiseplus.gov.in/).
The dashboard generates the report on demand and has **no static download URL**,
so — like PLFS — there is **no `fetch.py`**; the raw xlsx staged on GCS is the
regenerable source of record.

## Pipeline at a glance

```
UDISE+ dashboard (Report 4000)              (manual export — no static URL)
       ▼
raw/udise_2024-25_enrolment.xlsx            (local; gitignored)
       │ scripts/clean_udise.py             (wide cross-tab → long fact)
       ▼
clean/enrolment.parquet                     (local; gitignored)
       │ scripts/upload_to_gcs.py           (raw xlsx + clean parquet → GCS)
       ▼
gs://avantifellows-external-data/udise/raw/<xlsx>          (traceability)
gs://avantifellows-external-data/udise/clean/enrolment.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.udise_fact_enrolment   (asia-south1)
```

## Table produced

**`udise_fact_enrolment`** — 42,270 rows. Grain:
`(academic_year, state, school_management, school_category, urban_rural, class_level, gender)` → `enrolment`.

Schema: [`schemas/udise_fact_enrolment.yaml`](schemas/udise_fact_enrolment.yaml).

**Validation:** `SUM(enrolment)` = **246,932,680**, matching the all-India total
the dashboard reports.

## Reshape notes (read before analysing)

- **Only leaf detail rows are kept.** The export is hierarchical — it mixes
  detail rows with subtotal rows (`urban_rural="Total"` = Rural+Urban, blank-
  urban_rural state subtotals, a blank-Location all-India grand total). The
  cleaner keeps only `urban_rural ∈ {Rural, Urban}` rows with state + management
  + category present, so the fact never double-counts. Totals are derivable by
  summing.
- **Gender is Girls/Boys only** — the source reports no per-class total or third
  gender; the wide "Overall" column (a row total) is dropped as derivable.
- **`class_level`** spans `Balvatika-1/2/3` (pre-primary) and `Class-1` … `Class-12`.

## Running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
gcloud auth application-default login            # for upload + load

# 1. drop the dashboard export into raw/ as udise_2024-25_enrolment.xlsx
# 2. reshape → clean/enrolment.parquet
.venv/bin/python scripts/clean_udise.py
# 3. stage raw + clean to GCS
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py
# 4. load to BigQuery (post-approval)
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## Refreshing for a new academic year

1. Export the same Report 4000 for the new AY from the UDISE+ dashboard, save as
   `raw/udise_<AY>_enrolment.xlsx`, and point `SOURCE_XLSX` / `ACADEMIC_YEAR` in
   `scripts/sources.py` at it.
2. `clean_udise.py` → `upload_to_gcs.py` → `load_bq.py`. The fact keys on
   `academic_year`, so new years append cleanly.


---

# DSP microdata (school level)

The Data Sharing Portal release: **one row per school**, five academic years
(2020-21, 2022-23, 2023-24, 2024-25, 2025-26 — 2021-22 is not held). Read
[`schemas/README.md`](schemas/README.md) before querying it; it has the five
gotchas that otherwise produce confident wrong numbers.

**Why we have it.** It is the only school-level source we hold with a poverty and
social-composition breakdown — **BPL** (`item_group=3, item_id=13`) and **EWS**
(`item_group=10, item_id=32`) enrolment per school, per class, per gender, alongside
social category, religion, disability and repeaters. AISHE has no household-income
variable in any edition. This is what sizes the low-income student population Avanti
serves, in numbers the government itself publishes.

**What is committed vs where the data lives.** Git holds the pipeline, the schema
YAMLs, the codemaps and the observed layouts (`schemas/dsp_layouts.json`). No data:
the zips and every intermediate are gitignored and live in GCS and BigQuery.

## Pipeline at a glance

```
UDISE+ Data Sharing Portal                  (manual download — no static URL)
       ▼
raw/dsp/<year>/<group>_All State_<year>.zip           (local; gitignored, ~1.7 GB)
       │ scripts/dsp_stage.py --raw
       ▼
gs://…/udise/raw/dsp/<year>/<zip>                     (source of record, audit copy)

raw/dsp/<year>/<group>/*.zip
       │ scripts/dsp_stage.py        (zip member → gzip, streamed; never via pandas)
       ▼
gs://…/udise/staging/dsp/<year>/<group>/*.csv.gz      (regenerable; delete after load)
       │ bq load, one table per (year, file group), columns straight from the header
       ▼
avantifellows.udise_dsp_staging.<group>_<year>        (transient, 14-day expiry)
       │ scripts/dsp_build_bq.py     (harmonise 4 layouts, melt wide→long, decode codes)
       ▼
avantifellows.external_data_sources.udise_dim_school_dsp
avantifellows.external_data_sources.udise_fact_enrolment_dsp
avantifellows.external_data_sources.udise_fact_teacher_dsp
avantifellows.external_data_sources.udise_fact_facility_dsp
```

## Tables produced

| Table | Grain | Rows |
|---|---|---|
| `udise_dim_school_dsp` | school × academic year | 7,385,291 |
| `udise_fact_enrolment_dsp` | school × item × class × gender | 504,108,627 |
| `udise_fact_teacher_dsp` | school × academic year | 7,385,291 |
| `udise_fact_facility_dsp` | school × academic year | 7,385,291 |

The three school-level facts all key on `(academic_year, pseudocode)` and join to
the dim. `safety` (2025-26 only) is folded into the facility fact rather than given
its own table — same grain, same subject.

The clean layer is **BigQuery-native rather than a parquet in GCS**, which is the
convention everywhere else in this repo. The melt turns ~12 GB of CSV into hundreds
of millions of rows; that cannot round-trip through a laptop. The generated SQL is
deterministic and printable (`--print-sql`), so the tables stay fully regenerable and
auditable — which is the property the parquet convention exists to protect.

## Four layouts, not one

The five editions are not one schema. `dsp_stage.py` reads each CSV's own header, so
no per-year config is needed, and records what it saw in `schemas/dsp_layouts.json`.

| Edition | Enrolment | Profile 1 | Profile 2 | Quirks |
|---|---|---|---|---|
| 2020-21 | 28 col, text `item_desc` | 53 col | 63 col | key spelt `psuedocode`; each enrolment file **sharded into 6 state CSVs**; extra `NationalStreamEnrolment.csv` |
| 2022-23 | 29 col, `item_group`+`item_id` | 38 | 17 | — |
| 2023-24 | 29 col | 38 | 17 | — |
| 2024-25 | 29 col | 38 | 17 | — |
| 2025-26 | **42 col — adds `_t` (transgender) per class** | 49 | 17 | new `safety` file group |

Harmonising them is what `dsp_build_bq.py` does: a column a given edition does not
publish becomes a typed NULL, so all five UNION cleanly, and the coverage groups are
documented in [`schemas/udise_dim_school_dsp.yaml`](schemas/udise_dim_school_dsp.yaml).

## Running

```bash
gcloud auth login                                     # bq + gcloud storage
python3 scripts/dsp_stage.py --raw                    # zips → GCS raw/ (once per edition)
python3 scripts/dsp_stage.py                          # gz → GCS staging → BQ staging
python3 scripts/dsp_build_bq.py --print-sql           # inspect the SQL first
python3 scripts/dsp_build_bq.py                       # build both tables, then validate
python3 scripts/dsp_build_bq.py --drop-staging        # once the numbers check out
```

`--gzip-only` runs the slow, credential-free half on its own; `--load-only` picks up
from already-gzipped files. Both are re-runnable — an existing `.csv.gz` is reused
rather than re-extracted.

## Adding a new edition

1. Download the file groups from the portal into `raw/dsp/<year>/`, named exactly as
   the portal produces them (`<group>_All State_<year>.zip`).
2. Add the year to `DSP_YEARS` in `scripts/sources.py`. If the edition predates the
   `100_*.csv` naming or shards its files, add it to `DSP_MEMBERS_2020_21`-style
   registry; otherwise nothing else is needed.
3. Re-run the pipeline above. New columns stage on their own — check the
   `schemas/dsp_layouts.json` diff, and add any genuinely new column to `DIM_FIELDS`
   in `dsp_build_bq.py` if it belongs in the dim.
