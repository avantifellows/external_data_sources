# aishe

AISHE (All India Survey on Higher Education, MoE) out-turn data → BigQuery.

Out-turn (graduates / qualifiers) cuts from the AISHE Final Reports: by state ×
level, by UG discipline, and by degree programme × social category, plus a
3-year UG-discipline panel (2019-20 → 2021-22) and a linear projection to
2025-26. The workbooks need real parsing (openpyxl), so this is a
heavier pipeline than `nirf/`, but it still stages parsed parquet through GCS.

**Source:** AISHE Final Report workbooks from
[aishe.gov.in](https://aishe.gov.in/) (Ministry of Education). One `.xlsx` per
academic year. Not redistributed in git — see *Raw data* below.

## Pipeline at a glance

```
raw/aishe_<year>_final_report.xlsx          (local; gitignored)
       │ scripts/build_programme_map.py  → codemaps/programme_to_discipline.csv  (committed)
       │ scripts/clean_aishe.py
       ▼
clean/*.parquet                             (local; gitignored)
       │ scripts/upload_to_gcs.py   (uploads raw sheets + clean tables, both as parquet)
       ▼
gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet     (traceability)
gs://avantifellows-external-data/aishe/clean/<table>.parquet          (loaded to BQ)
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.aishe_*   (asia-south1, 7 tables)
```

## GCS layout

```
gs://avantifellows-external-data/
  aishe/raw/<year>/<sheet>.parquet     ← faithful dump of each source sheet (traceability)
  aishe/clean/<table>.parquet          ← the 7 parsed tables; load_bq.py loads these
```

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Tables produced

| Table | Rows | Grain | Source |
|---|---:|---|---|
| `aishe_fact_outturn_state_level`               | 864   | (aishe_year, state, level, gender)              | Table 33 |
| `aishe_fact_outturn_ug_discipline`             | 120   | (aishe_year, discipline, gender)                | Table 35 |
| `aishe_fact_outturn_programme_social_category` | 5,448 | (aishe_year, programme, social_category, gender)| Table 34a (national) |
| `aishe_fact_outturn_discipline_social_category`| 624   | (aishe_year, discipline, social_category, gender)| derived (34a rollup) |
| `aishe_dim_programme_discipline_map`           | 227   | (programme)                                     | codemap |
| `aishe_fact_ug_discipline_panel`               | 687   | (aishe_year, metric, discipline, gender)        | Tables 12 + 35, 2019-22 |
| `aishe_fact_ug_discipline_extrapolated`        | 432   | (target_year, metric, discipline, gender)       | derived (projection) |

Schemas: [`schemas/*.yaml`](schemas/).

**Validation cross-checks** (asserted by the parser output):
- `outturn_state_level` UG total summed across states = **7,754,223**
- `outturn_ug_discipline` Total summed across disciplines = **7,754,223** (Tables 33 and 35 reconcile exactly)
- `outturn_programme_social_category` All-Categories Total = **10,738,573** (all-levels India total, matches Table 33)

## Raw data

The Final Report `.xlsx` files are gitignored (`raw/*.xlsx`). Download them from
the AISHE portal and drop them into `raw/` with these names before running:

| File | Year |
|---|---|
| `raw/aishe_2019-20_final_report.xlsx` | 2019-20 |
| `raw/aishe_2020-21_final_report.xlsx` | 2020-21 |
| `raw/aishe_2021-22_final_report.xlsx` | 2021-22 |

Only the 2021-22 workbook is needed for the single-year out-turn tables; all
three are needed for the panel + extrapolation.

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for upload + load
```

## Running

```bash
# 1. (rarely) rebuild the programme->discipline codemap from the 2021-22 workbook
.venv/bin/python scripts/build_programme_map.py

# 2. parse the workbooks -> clean/*.parquet
.venv/bin/python scripts/clean_aishe.py

# 3. stage to GCS — uploads raw sheets + clean tables (both parquet)
.venv/bin/python scripts/upload_to_gcs.py --dry-run   # preview
.venv/bin/python scripts/upload_to_gcs.py             # raw + clean
#   …or just one side: --raw-only / --clean-only

# 4. load the clean tables to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run         # preview
.venv/bin/python scripts/load_bq.py
```

`upload_to_gcs.py` takes `--raw-only` / `--clean-only` / `--dry-run`;
`load_bq.py` takes `--table <bq_name>` / `--dry-run` and uses `WRITE_TRUNCATE`,
so each load fully replaces its destination table. Only the clean tables are
loaded to BQ — the raw parquet on GCS is for traceability.

## Caveat — the discipline × social-category rollup

AISHE does **not** publish a discipline × social-category cut for out-turn.
`aishe_fact_outturn_discipline_social_category` is derived by rolling Table 34a
(programme × social category) up to discipline level via the
`aishe_dim_programme_discipline_map` codemap. **Table 34a (degree programme) and
Table 35 (subject-based discipline) use incompatible classifications**, so the
rollup maps by degree name and cannot recover subject-based disciplines.

- **Reliable** for disciplines served by named degrees: Engineering &
  Technology, Medical Science, Law, Management, Education, Commerce, IT &
  Computer, Agriculture, Veterinary, Fisheries, Fine Arts, etc.
- **Do not use** for Indian Language, Social Science, Foreign Language, and
  other subject-based disciplines — those students sit in B.A./M.A./B.Sc.
  programmes and roll up to Arts/Science. **Arts and Science are over-counted**
  in this rollup for the same reason. Use `aishe_fact_outturn_ug_discipline`
  (Table 35, UG only) for subject-based discipline numbers.

The `aishe_fact_ug_discipline_extrapolated` table is a **model estimate** (OLS
on 3 years), not AISHE-published data — use for directional planning only.
