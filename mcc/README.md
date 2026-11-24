# mcc/

MCC (Medical Counselling Committee) All India Quota cutoffs — national-level
MBBS/BDS/Nursing closing NEET ranks per seat bucket. The medical counterpart
to [`josaa/`](../josaa/); the national counterpart to [`state_medical/`](../state_medical/)
(state-quota seats). ~3.1k rows.

New here? Read [`schemas/README.md`](schemas/README.md) — "MCC / AIQ in 60
seconds" — before querying. Editing orientation: [`CLAUDE.md`](CLAUDE.md).

## Pipeline shape

Light parse — `build_clean.py` splits the combined category label into
`(category, is_pwd)`, types ranks, stamps the cycle year/round.

```
mcc/raw/closing_ranks_aiq_r1_2025.csv   (gitignored; College DB output)
       │  scripts/build_clean.py         split category/is_pwd, type, stamp year/round
       ▼
mcc/clean/mcc_fact_closing_ranks.parquet (gitignored)
       │  scripts/upload_to_gcs.py        stage raw + clean to GCS
       ▼
gs://avantifellows-external-data/mcc/{raw,clean}/
       │  scripts/load_bq.py              load_table_from_uri, PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.mcc_fact_closing_ranks   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py)** —
includes the cycle constants (`CYCLE_YEAR`, `CYCLE_ROUND`).

## Upstream / provenance

Raw CSV is produced by the **College DB medical-national-ranks pipeline**
(`scripts/run_all.py`), which parses MCC's ~1,100-page R1 allotment PDF. We
reference, not duplicate, that parser. On a new round/cycle: run the College DB
pipeline, copy the new `closing_ranks_aiq_*.csv` into `mcc/raw/`, update the
cycle constants in `sources.py` if needed, rebuild + reload.

> **mcc ≠ nmc.** This source is MCC *counselling* (who got a seat at what
> rank). A separate `nmc/` source covers NMC *regulator* data (seat matrix /
> college registry). Keep them distinct.

## Commands

```bash
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# 1. Land the AIQ R1 file:
#    cp "../../College DB/medical-national-ranks/extracted_data/closing_ranks_aiq_r1_2025.csv" raw/
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
| `mcc_fact_closing_ranks` | (institute, course, quota, category, is_pwd, year, round) | ~3.1k |
