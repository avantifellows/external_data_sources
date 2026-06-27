# dakshana — NCST Results Pipeline

Ingestion pipeline for the Navodaya CoE Selection Test (NCST) results.
NCST is conducted jointly by Dakshana Foundation, ENF, and Avanti for JNV students.

Produces one BigQuery table:
- `avantifellows.external_data_sources.dakshana_fact_ncst_results` (2022–2025)

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions, and run commands.

## Quick start

```bash
# 1. Set up local Python env (from inside dakshana/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/ (filenames must match sources.py → RAW_NCST_FILES)

# 3. Transform raw Excel → clean CSV
.venv/bin/python scripts/clean_ncst.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `dakshana_fact_ncst_results` | (test_year, roll_no) | ~37k |
