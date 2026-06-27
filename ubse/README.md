# ubse — UBSE Board Results Pipeline

Ingestion pipeline for Uttarakhand Board of School Education (UBSE) Grade 10
and Grade 12 board exam results. Long format — one row per student per subject.

Produces two BigQuery tables:
- `avantifellows.external_data_sources.ubse_fact_grade10_results` (2026+)
- `avantifellows.external_data_sources.ubse_fact_grade12_results` (2026+)

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions, and run commands.

## Quick start

```bash
# 1. Set up local Python env (from inside ubse/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/ (filenames must match sources.py)

# 3. Transform raw Excel → clean CSVs
.venv/bin/python scripts/clean_grade10.py
.venv/bin/python scripts/clean_grade12.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `ubse_fact_grade10_results` | (exam_year, roll_no, subject_slot) | ~620k |
| `ubse_fact_grade12_results` | (exam_year, roll_no, subject_slot) | ~440k |
