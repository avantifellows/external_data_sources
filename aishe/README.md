# aishe

AISHE (All India Survey on Higher Education, MoE) out-turn data → BigQuery.

Out-turn (graduates / qualifiers) from the AISHE Final Reports, as a **single
denormalized fact** sliceable by state×level, programme×social-category, and UG
discipline (incl. 2019-22 trend). The workbooks need real parsing (openpyxl), so
this is a heavier pipeline than `nirf/`, but it still stages parsed parquet
through GCS.

The table shape is driven by the analytical questions — see
[`analyses/README.md`](analyses/README.md).

**Source:** AISHE Final Report workbooks from
[aishe.gov.in](https://aishe.gov.in/) (Ministry of Education). One `.xlsx` per
academic year. Not redistributed in git — see *Raw data* below.

## Pipeline at a glance

```
raw/aishe_<year>_final_report.xlsx          (local; gitignored)
       │ scripts/build_programme_map.py  → codemaps/programme_to_discipline.csv  (committed)
       │ scripts/clean_aishe.py
       ▼
clean/outturn.parquet                       (local; gitignored)
       │ scripts/upload_to_gcs.py   (uploads raw sheets + clean table, both parquet)
       ▼
gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet     (traceability)
gs://avantifellows-external-data/aishe/clean/outturn.parquet          (loaded to BQ)
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.aishe_fact_outturn   (asia-south1)
```

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Table produced

**`aishe_fact_outturn`** — one wide out-turn fact (6,654 rows). Grain:
`(aishe_year, level, state, discipline, programme, social_category, gender)` →
`out_turn`. It unifies three AISHE published cuts; dimensions a cut doesn't break
out carry the sentinel `"All"`:

| Cut | Source | Set dimensions | Rows |
|---|---|---|---:|
| state × level (2021-22)             | Table 33  | level, state                  | 864 |
| programme × social category (2021-22)| Table 34a | programme, social_category    | 5,448 |
| UG discipline (2019-20 → 2021-22)   | Table 35  | level=`Under Graduate`, discipline | 342 |

**Query by filtering to one slice — never `SUM(out_turn)` across rows of
different grain.** Worked slices are in the schema and `analyses/README.md`.

Schema: [`schemas/aishe_fact_outturn.yaml`](schemas/aishe_fact_outturn.yaml).

**Validation:** 2021-22 UG out-turn (gender=Total) = **7,754,223** via both the
state slice and the discipline slice (Tables 33 and 35 reconcile exactly).

## Analyses (derived — not tables)

Per the [`analyses/`](analyses/) convention, derived cuts are reproducible
scripts on top of the fact, not extra BQ tables:

- [`analyses/rollup_discipline_social_category.py`](analyses/rollup_discipline_social_category.py)
  — rolls the programme×social slice up to discipline via the codemap.
- [`analyses/project_discipline_2025_26.py`](analyses/project_discipline_2025_26.py)
  — OLS projection of the UG-discipline trend to 2024-25 / 2025-26 (model estimate).

The programme→discipline **codemap stays a committed CSV**
(`codemaps/programme_to_discipline.csv`), the audit interface the rollup reads.

## GCS layout

```
gs://avantifellows-external-data/
  aishe/raw/<year>/<sheet>.parquet     ← faithful dump of each source sheet (traceability)
  aishe/clean/outturn.parquet          ← the fact; load_bq.py loads this
```

## Raw data

The Final Report `.xlsx` files are gitignored (`raw/*.xlsx`). Download from the
AISHE portal and drop into `raw/` with these names before running:

| File | Year |
|---|---|
| `raw/aishe_2019-20_final_report.xlsx` | 2019-20 |
| `raw/aishe_2020-21_final_report.xlsx` | 2020-21 |
| `raw/aishe_2021-22_final_report.xlsx` | 2021-22 |

Only 2021-22 is needed for the state and programme slices; all three feed the
UG-discipline trend.

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

# 2. parse the workbooks -> clean/outturn.parquet
.venv/bin/python scripts/clean_aishe.py

# 3. stage to GCS — uploads raw sheets + the clean fact (both parquet)
.venv/bin/python scripts/upload_to_gcs.py --dry-run   # preview
.venv/bin/python scripts/upload_to_gcs.py             # raw + clean
#   …or just one side: --raw-only / --clean-only

# 4. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run         # preview
.venv/bin/python scripts/load_bq.py

# (optional) derived analyses
.venv/bin/python analyses/rollup_discipline_social_category.py --save
.venv/bin/python analyses/project_discipline_2025_26.py --save
```

`load_bq.py` uses `WRITE_TRUNCATE`, so the load fully replaces the table. Only
the clean fact is loaded to BQ — the raw parquet on GCS is for traceability.

## Caveats

- **The discipline × social-category rollup is degree-name based.** Tables 34a
  (degree programme) and 35 (subject-based discipline) use incompatible
  classifications, so the rollup (in `analyses/`) cannot recover subject-based
  disciplines (Indian Language, Social Science, Foreign Language, …) — those
  students sit in B.A./M.A./B.Sc. and roll up to Arts/Science, which are
  over-counted. Reliable for disciplines served by named degrees (Engineering &
  Technology, Medical Science, Law, Management, Education, Commerce, IT &
  Computer, …). Use the discipline slice of the fact (Table 35, UG) for
  subject-based discipline numbers.
- **The 2025-26 projection is a model estimate** (OLS on 3 years), not
  AISHE-published data.
- **Social categories overlap** (All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS) —
  never sum across `social_category`.
