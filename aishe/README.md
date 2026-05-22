# aishe

AISHE (All India Survey on Higher Education, MoE) student data → BigQuery.

**Enrolment + graduates (out-turn)** from the AISHE Final Reports, as a **single
denormalized fact** sliceable by state×level, programme×social-category, and UG
discipline (incl. the 2019-22 trend). The workbooks need real parsing (openpyxl),
so this is a heavier pipeline than `nirf/`, but it still stages parsed parquet
through GCS.

**Source:** AISHE Final Report workbooks from
[aishe.gov.in](https://aishe.gov.in/) (Ministry of Education). One `.xlsx` per
academic year. Not redistributed in git — see *Raw data* below.

## Pipeline at a glance

```
he.nic.in AISHE Final Reports               (canonical source URLs in sources.py)
       │ scripts/fetch.py
       ▼
raw/aishe_<year>_final_report.xlsx          (local; gitignored)
       │ scripts/build_programme_map.py  → codemaps/programme_to_discipline.csv  (committed)
       │ scripts/clean_aishe.py
       ▼
clean/higher_ed.parquet                     (local; gitignored)
       │ scripts/upload_to_gcs.py   (uploads raw sheets + clean table, both parquet)
       ▼
gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet     (traceability)
gs://avantifellows-external-data/aishe/clean/higher_ed.parquet        (loaded to BQ)
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.aishe_fact_higher_ed   (asia-south1)
```

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Table produced

**`aishe_fact_higher_ed`** — one wide fact (6,999 rows). Grain:
`(cut, aishe_year, metric, level, state, discipline, programme, social_category, gender)`
→ `value`. Each row carries a `cut` (which published cross-tab it came from) and a
`metric` (`enrolment` = students currently studying, or `graduates` = out-turn /
qualifiers that year). Dimensions a cut doesn't break out carry the sentinel `"All"`:

| `cut` | Source | Metric(s) | Set dimensions | Rows |
|---|---|---|---|---:|
| `state_level`      | Table 33     | graduates             | level, state                       | 864 |
| `programme_social` | Table 34a    | graduates             | programme, social_category         | 5,448 |
| `ug_discipline`    | Tables 12+35 | enrolment + graduates | level=`Under Graduate`, discipline | 687 |

**The cuts overlap (different views of the same students) — always filter to one
`cut`, and never `SUM(value)` across cuts.**

Schema: [`schemas/aishe_fact_higher_ed.yaml`](schemas/aishe_fact_higher_ed.yaml).

**Validation:** 2021-22 UG graduates (`metric='graduates'`, `gender='Total'`) =
**7,754,223** via both the `state_level` cut and the `ug_discipline` cut (Tables 33
and 35 reconcile exactly).

## Analysis (not in this repo)

Exploratory analysis — the discipline × social-category rollup, the 2025-26
projection, and the discipline → wage-bucket grouping for the cross-source RoI /
wage-curve work — runs locally; the analysis *intents* are documented in
`bq-assistant/docs/analyses/external_data_sources.yaml`. Only the
programme→discipline **codemap stays a committed CSV**
(`codemaps/programme_to_discipline.csv`), the audit interface those rollups read.

## GCS layout

```
gs://avantifellows-external-data/
  aishe/raw/<year>/<sheet>.parquet     ← faithful dump of each source sheet (traceability)
  aishe/clean/higher_ed.parquet        ← the fact; load_bq.py loads this
```

## Raw data

The Final Report `.xlsx` files are gitignored (`raw/*.xlsx`) and **fetched from
source** by `scripts/fetch.py` (canonical URLs in `scripts/sources.py` →
`REPORT_URLS`, on he.nic.in) — no manual download:

| File | Year |
|---|---|
| `raw/aishe_2019-20_final_report.xlsx` | 2019-20 |
| `raw/aishe_2020-21_final_report.xlsx` | 2020-21 |
| `raw/aishe_2021-22_final_report.xlsx` | 2021-22 |

Only 2021-22 is needed for the state and programme cuts; all three feed the
UG-discipline enrolment + graduates trend.

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for upload + load
```

## Running

```bash
# 0. fetch the raw workbooks from source → raw/  (regenerable; no manual download)
.venv/bin/python scripts/fetch.py            # --force to re-download, --year YYYY-YY for one

# 1. (rarely) rebuild the programme->discipline codemap from the 2021-22 workbook
.venv/bin/python scripts/build_programme_map.py

# 2. parse the workbooks -> clean/higher_ed.parquet
.venv/bin/python scripts/clean_aishe.py

# 3. stage to GCS — uploads raw sheets + the clean fact (both parquet)
.venv/bin/python scripts/upload_to_gcs.py --dry-run   # preview
.venv/bin/python scripts/upload_to_gcs.py             # raw + clean
#   …or just one side: --raw-only / --clean-only

# 4. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run         # preview
.venv/bin/python scripts/load_bq.py
```

`load_bq.py` uses `WRITE_TRUNCATE`, so the load fully replaces the table. Only
the clean fact is loaded to BQ — the raw parquet on GCS is for traceability.

## Caveats

- **`enrolment` exists only on the `ug_discipline` cut** (UG, by subject
  discipline, Table 12). The state and programme cuts are graduates only.
- **The cuts overlap** — each is a different view of the same students. Filter to
  one `cut`; never `SUM(value)` across cuts.
- **Social categories overlap** (All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS) —
  never sum across `social_category` either.
- **discipline (subject) ≠ programme (degree).** Table 34a is degree-based
  (B.A., MBBS, …); Tables 12/35 are subject-based (Arts, Engineering & Tech, …).
  They use incompatible classifications and can't be cross-walked exactly — use
  the `ug_discipline` cut for subject-based numbers.
