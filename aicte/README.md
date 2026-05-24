# aicte

AICTE technical-education intake panels → BigQuery.

Approved intake, enrolment, passouts, placements, and institution counts for
the six AICTE technical streams (Engineering & Technology, Management, MCA,
Pharmacy, Architecture, Hotel Management), AY 2012-13 → 2022-23. Pulled from the
AICTE dashboard JSON API at three cuts (national, by state, by institution-type)
and unified into one wide fact, then parquet → GCS → BQ.

**Source:** AICTE technical-education dashboard JSON API,
[facilities.aicte-india.org](https://facilities.aicte-india.org/dashboard/).
A single endpoint returns 11-year arrays of intake/enrolment/passed/placed/
institution-count per filter, plus girls/boys/faculty scalars for a selected
focal year. Not redistributed in git — see *Raw data* below.

## Pipeline at a glance

```
AICTE dashboard JSON API                     (facilities.aicte-india.org)
       │ scripts/fetch.py                     (~440 throttled requests, 3 cuts)
       ▼
raw/panel_national.csv                       (program × level × year)
raw/panel_state.csv                          (state × program × level × year)
raw/panel_inst_type.csv                      (institution_type × program × level × year)
       │                                       (all local; gitignored)
       │ scripts/clean_aicte.py               (unify 3 cuts → one wide fact, "All" sentinel)
       ▼
clean/intake.parquet                         (local; gitignored)
       │ scripts/upload_to_gcs.py             (raw panels + clean parquet → GCS)
       ▼
gs://avantifellows-external-data/aicte/raw/panel_*.csv      (traceability)
gs://avantifellows-external-data/aicte/clean/intake.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.aicte_fact_intake       (asia-south1)
```

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Table produced

**`aicte_fact_intake`** — one wide fact, **4,664 rows**. Grain:
`(cut, year, program, level, state, institution_type)` → `approved_intake`,
`enrolled`, `passed`, `placed`, `institutions`, `girls`, `boys`, `faculties`.

It unifies three published cuts on one grain. Each row is tagged with `cut`;
dimensions a cut doesn't break out carry an `"All"` sentinel. **Filter on `cut`
— never SUM across cuts (they overlap):**

| `cut` | Set dimensions | `state` | `institution_type` | `faculties` | Rows |
|---|---|---|---|---|---:|
| `national`  | year, program, level | `"All"` | `"All"` | populated | 88 |
| `state`     | + state | state name | `"All"` | NULL | 3,168 |
| `inst_type` | + institution_type | `"All"` | inst-type | NULL | 1,408 |

The national totals are `cut='national'` (88 = 8 program×level cuts × 11 years).

Schema: [`schemas/aicte_fact_intake.yaml`](schemas/aicte_fact_intake.yaml).

**Validation:** `cut='national'`, Engineering and Technology / UG / 2021-22
`approved_intake` = **1,253,337**.

## GCS layout

```
gs://avantifellows-external-data/
  aicte/raw/panel_*.csv                ← the 3 pulled panels, as-is (traceability)
  aicte/clean/intake.parquet           ← the fact; load_bq.py loads this
```

## Raw data

The three panel CSVs are gitignored (`raw/*.csv`) and **pulled from the AICTE
API** by `scripts/fetch.py` — no manual download. The pull is network-bound
(~440 throttled requests across the three cuts):

| File | Cut | Requests |
|---|---|---:|
| `panel_national.csv`  | program × level × year       | 88 |
| `panel_state.csv`     | state × program × level      | 288 |
| `panel_inst_type.csv` | institution_type × program × level | 128 |

The state and institution-type panels query the API at focal year 2021-22
(latest reliable year for the girls/boys scalar; 2022-23 enrolment is incomplete
in the live dashboard), so those cuts carry gender only for AY 2021-22.

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for upload + load
```

## Running

```bash
# 0. pull the 3 panels from the AICTE API → raw/  (regenerable; ~440 requests)
.venv/bin/python scripts/fetch.py                 # --panel national|state|inst_type for one

# 1. unify the 3 cuts → clean/intake.parquet
.venv/bin/python scripts/clean_aicte.py

# 2. stage to GCS — uploads raw panels + the clean fact
.venv/bin/python scripts/upload_to_gcs.py --dry-run   # preview
.venv/bin/python scripts/upload_to_gcs.py             # raw + clean
#   …or just one side: --raw-only / --clean-only

# 3. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run         # preview
.venv/bin/python scripts/load_bq.py
```

`load_bq.py` uses `WRITE_TRUNCATE`, so the load fully replaces the table. Only
the clean fact is loaded to BQ — the raw panels on GCS are for traceability.

## Caveats — read before analysing

- **The three cuts overlap — filter to one slice before aggregating.** A
  national row, its state breakdown, and its institution-type breakdown all
  cover the same students. Never `SUM` across the `"All"`-sentinel rows and the
  broken-out rows; pick one cut (`state="All" AND institution_type="All"` for
  national, or one breakdown) first.
- **Gender (`girls`/`boys`) is focal-year-only off the national cut.** The API
  returns the gender scalar only for the selected year, so on the state and
  institution-type rows it's populated only for AY 2021-22; NULL elsewhere. The
  national cut queries each year, so it has gender for every year.
- **`faculties` is national-only.** Reported by the API only at the national
  level → NULL on every state and institution-type row.
- **Blanks are NULL, not zero.** Missing source cells become NULL (nullable
  Int64). Don't treat absence as 0.
- **2022-23 enrolment is incomplete** in the live dashboard at pull time; treat
  the final year cautiously.

## Refreshing for a new AICTE release

1. Add the new year to `YEAR_LABEL` (and bump the array length) in
   `scripts/fetch.py`; bump the focal year if a newer reliable gender year
   exists.
2. `fetch.py` → `clean_aicte.py` → `upload_to_gcs.py` → `load_bq.py`. Loads are
   `WRITE_TRUNCATE`, so the table fully replaces on each run.
