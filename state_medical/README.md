# state_medical/

State-quota MBBS/BDS admission cutoffs — the ~85% of govt medical seats
counselled by ~30 individual state authorities, harmonized across 32
states/UTs. The state-quota counterpart to [`mcc/`](../mcc/) (national AIQ).
~2.9k rows.

New here? Read [`schemas/README.md`](schemas/README.md) — "State medical
counselling in 60 seconds" — before querying. This is the trickiest source
(mixed rank spaces). Editing orientation: [`CLAUDE.md`](CLAUDE.md).

## Pipeline shape

Light parse / heavy provenance — `build_clean.py` projects the upstream
national file to neutral columns, derives `rank_space`, and drops Avanti
modeling columns.

```
state_medical/raw/national_closing_ranks_unified_AIR_2025.csv  (gitignored; College DB output)
       │  scripts/build_clean.py     project neutral cols, derive rank_space, drop estimates
       ▼
state_medical/clean/state_medical_fact_closing_ranks.parquet   (gitignored)
       │  scripts/upload_to_gcs.py    stage raw + clean to GCS
       ▼
gs://avantifellows-external-data/state_medical/{raw,clean}/
       │  scripts/load_bq.py          load_table_from_uri, PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.state_medical_fact_closing_ranks   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).**

## Upstream / provenance

Raw national file is produced by the **College DB medical-state-counselling
pipeline** — 35 per-state parsers (`scripts/`) + a national consolidation that
harmonizes 22 different per-state schemas. We reference, not duplicate, that
work. On refresh: run the College DB pipeline, copy its
`national_closing_ranks_unified_AIR_2025.csv` into `state_medical/raw/`,
rebuild + reload.

> **Neutral projection only.** The upstream file carries Avanti modeling — an
> estimated unified AIR, salary tiers, round multipliers, estimated-R3 ranks.
> `build_clean.py` drops all of those. This source ships only the published
> closing rank + its native rank-space provenance + quality flags. The
> comparable-AIR estimate for state-native states stays in College DB.

## Commands

```bash
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# 1. Land the national file:
#    cp "../../College DB/medical-state-counselling/extracted_data/national_closing_ranks_unified_AIR_2025.csv" raw/
# 2. Build
.venv/bin/python scripts/build_clean.py --dry-run
.venv/bin/python scripts/build_clean.py
# 3. Stage to GCS
.venv/bin/python scripts/upload_to_gcs.py --raw --dry-run
.venv/bin/python scripts/upload_to_gcs.py --raw
# 4. Load GCS → BQ
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `state_medical_fact_closing_ranks` | (state, college, program, category, round) | ~2.9k |
