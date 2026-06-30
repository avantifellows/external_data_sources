# pb_scert — Punjab SCERT SOE & RSMS Admission Merit List Pipeline

Ingestion pipeline for the Punjab SCERT SOE & RSMS Admission Test merit list.
Covers students who applied for Class 11 admission to Schools of Eminence (SOE)
and Meritorious Schools (RSMS) across three academic years: 2024-25, 2025-26, 2026-27.

Produces one BigQuery table:
- `avantifellows.external_data_sources.pb_scert_fact_soe_rsms_admission_merit_list` (~326k rows)

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions, and run commands.

## Quick start

```bash
# 1. Set up local Python env (from inside pb_scert/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel into raw/ (filename must match sources.py → RAW_MERIT_LIST_FILES)

# 3. Transform raw Excel → clean CSV
.venv/bin/python scripts/clean_merit_list.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `pb_scert_fact_soe_rsms_admission_merit_list` | (academic_year, exam_application_no) | ~326k |
