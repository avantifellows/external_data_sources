# jnv — JNV JEE Mains Results Pipeline

JEE Mains results for Jawahar Navodaya Vidyalaya (JNV) students, 2021–2026.
Produces one BigQuery table: `avantifellows.external_data_sources.jnv_fact_jee_mains_results`.

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions, and pitfalls.

## Quick start

```bash
# 1. Set up local Python env (from inside jnv/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/jee_mains/ (filenames must match sources.py → RAW_FILES)

# 3. Transform → clean CSV
.venv/bin/python scripts/clean_jee_mains.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `jnv_fact_jee_mains_results` | (test_year, application_no) | ~55k |

## Adding a new year

1. Create `codemaps/mains/yYYYY.py` with a `CODEMAP` dict (copy nearest year as template).
2. Add one import line to `codemaps/mains/__init__.py` and append to `ALL_CODEMAPS`.
3. Add the raw Excel file entry to `scripts/sources.py` → `RAW_FILES`.
4. Re-run steps 3–5 above.

## GCS layout

```
gs://avantifellows-external-data/
  jnv/raw/jee_mains/<stem>.parquet     ← one per raw Excel file
  jnv/clean/jnv_fact_jee_mains_results.parquet
```
