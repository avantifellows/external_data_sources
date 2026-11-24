# state_cet/

State Common Entrance Test admission cutoffs — govt engineering/allied seat
closing ranks (& marks) across 10 states, harmonized into one fact. The
state-quota counterpart to [`josaa/`](../josaa/) (national pool). ~7.8k rows.

New here? Read [`schemas/README.md`](schemas/README.md) — "State CETs in 60
seconds" — before querying. Editing orientation: [`CLAUDE.md`](CLAUDE.md).

## Pipeline shape

Light parse — the upstream consolidated CSV is already analyst-clean, so
`build_clean.py` only types columns + tidies college_name newlines.

```
state_cet/raw/ALL_STATES_consolidated_5cat_govt.csv   (gitignored; College DB output)
       │  scripts/build_clean.py       type ranks/marks, flatten newlines
       ▼
state_cet/clean/state_cet_fact_closing_ranks.parquet  (gitignored)
       │  scripts/upload_to_gcs.py     stage raw + clean to GCS
       ▼
gs://avantifellows-external-data/state_cet/{raw,clean}/
       │  scripts/load_bq.py           load_table_from_uri, PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.state_cet_fact_closing_ranks   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).**

## Upstream / provenance

Raw consolidated CSV is produced by the **per-state scrapers +
`consolidate_all.py` in the College DB repo** (`state-cet-scrape/`), which
parse each state authority's official cutoff PDFs/pages. We reference, not
duplicate, those parsers. On refresh / new state: run the College DB pipeline,
copy `state-cet-scrape/extracted_data/ALL_STATES_consolidated_5cat_govt.csv`
into `state_cet/raw/`, rebuild + reload.

> **This source ships a curated product.** The consolidated file is already
> govt-scope-filtered, 5-cat-harmonized, and closing-rank=final-round. That
> curation is documented transparently in the schema — it is NOT untouched
> source. Raw state category labels, private colleges, and per-round detail
> stay in College DB by design.

## Commands

```bash
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# 1. Land the consolidated file:
#    cp "../../College DB/state-cet-scrape/extracted_data/ALL_STATES_consolidated_5cat_govt.csv" raw/
# 2. Build clean parquet
.venv/bin/python scripts/build_clean.py --dry-run
.venv/bin/python scripts/build_clean.py
# 3. Stage to GCS
.venv/bin/python scripts/upload_to_gcs.py --raw --dry-run
.venv/bin/python scripts/upload_to_gcs.py --raw
# 4. Load GCS → BQ
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/ALL_STATES_consolidated_5cat_govt.csv` | No | Landed College DB output. Authoritative copy in GCS. |
| `clean/*.parquet` | No | Built by `build_clean.py`. Authoritative copy in GCS. |
| `scripts/*.py` | Yes | sources.py · build_clean.py · upload_to_gcs.py · load_bq.py |
| `schemas/*.yaml` + `schemas/README.md` | Yes | Teaching docs + 60-sec primer. |

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `state_cet_fact_closing_ranks` | (state, cet_name, stream, year, college_code, branch_code, quota, category, gender) | ~7.8k |
