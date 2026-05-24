# nas

NAS 2021 (National Achievement Survey) state proficiency → BigQuery.

Student-achievement performance and proficiency for grades 3 / 5 / 8 / 10, at the
**state** level (the level NAS publishes), broken out by school management and by
location. Each cell is kept per state; the student-weighted **national rollup** is
added as `state='All India'`. Then stages parquet → GCS → BQ.

**Source:** NAS 2021, NCERT. Upstream is the **community CSV mirror**
[`gsidhu/NAS-2021-data`](https://github.com/gsidhu/NAS-2021-data) — a tidy CSV
form of NCERT's published NAS 2021 results. `scripts/fetch.py` shallow-clones
that repo into `raw/`, so the source CSVs land at `raw/NAS-2021-data/csv_data/`.

## Pipeline at a glance

```
gsidhu/NAS-2021-data (community CSV mirror of NCERT NAS 2021)
       │ scripts/fetch.py                  (git clone --depth 1 → raw/)
       ▼
raw/NAS-2021-data/csv_data/                (local; gitignored)
       │ scripts/clean_nas.py              (state rows + 'All India' weighted rollup)
       ▼
clean/state_proficiency.parquet         (local; gitignored)
       │ scripts/upload_to_gcs.py          (raw CSVs + clean parquet → GCS)
       ▼
gs://avantifellows-external-data/nas/raw/csv_data/<...>          (traceability)
gs://avantifellows-external-data/nas/clean/state_proficiency.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.nas_fact_state_proficiency   (asia-south1)
```

## Table produced

**`nas_fact_state_proficiency`** — 3,510 rows (90 per state × 39, incl. the
`All India` rollup). Grain: `(state, grade, subject, dimension, category)` →
`pct_correct_mean, pct_proficient_advanced, pct_basic_below_basic`. Use
`state='All India'` for the national figure; filter a real state name otherwise.

Schema: [`schemas/nas_fact_state_proficiency.yaml`](schemas/nas_fact_state_proficiency.yaml).

## Aggregation notes (read before analysing)

- **State → national, student-weighted.** NAS reports percent-correct and
  proficiency bands at the **state** level only. The national figure is a mean
  across states weighted by `total_student × (state's share of students in that
  management/location bucket) / 100`. The share columns
  (`govt_school`, `private_school`, `rural_location`, …) come from
  `NAS_participation_state.csv`.
- **Two proficiency tails only.** NAS publishes "% Proficient and Advance" (top
  tail) and "% Basic and Below Basic" (bottom tail). The four-band split is not
  in this data set, so the fact carries only the two tails plus the
  percent-correct mean.
- **Dimensions:** `management` (State Govt, Govt Aided, Private Recognised,
  Central Govt) and `location` (Rural, Urban).
- **Subjects vary by grade:** grade 3/5 → language, math, evs; grade 8 →
  language, math, sci, sst; grade 10 → eng, mil, math, sci, sst.

## Running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
gcloud auth application-default login            # for upload + load

# 1. clone the community CSV mirror into raw/
.venv/bin/python scripts/fetch.py
# 2. aggregate state → national → clean/state_proficiency.parquet
.venv/bin/python scripts/clean_nas.py
# 3. stage raw CSVs + clean parquet to GCS
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py
# 4. load to BigQuery (post-approval)
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```
