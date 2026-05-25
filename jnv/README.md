# jnv — JNV Results Pipelines

JEE Mains/Advanced, NEET, JNVST selection test, and EI Asset Test results for
Jawahar Navodaya Vidyalaya (JNV) students.

Produces four BigQuery tables:
- `avantifellows.external_data_sources.jnv_fact_jee_results` (2021–2026)
- `avantifellows.external_data_sources.jnv_fact_neet_results` (2021–2025)
- `avantifellows.external_data_sources.jnv_fact_selection_test_results` (2018)
- `avantifellows.external_data_sources.jnv_fact_ei_asset_test_results`

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions, and pitfalls.

## Quick start — JEE

```bash
# 1. Set up local Python env (from inside jnv/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/jee_mains/ and raw/jee_advanced/

# 3. Transform → clean CSV
.venv/bin/python scripts/clean_jee.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --jee-only

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --jee-only
```

## Quick start — NEET

```bash
# 1. Set up local Python env (same venv as JEE)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/neet/ (filenames must match sources.py → RAW_NEET_FILES)

# 3. Transform → clean CSV
.venv/bin/python scripts/clean_neet.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --neet-only

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --neet-only
```

## Quick start — JNVST Selection Test

```bash
# 1. Drop raw Excel into raw/jnvst/ (filename must match sources.py → RAW_JNVST_FILES)

# 2. Clean → CSV (lowercase columns, rename to descriptive names, map area/gender values)
.venv/bin/python scripts/clean_jnvst.py

# 3. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --jnvst-only

# 4. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --jnvst-only
```

## Quick start — EI Asset Test

```bash
# 1. Drop raw Excel into raw/ei_asset_test/ (filename must match sources.py → RAW_EI_ASSET_TEST_FILES)

# 2. Clean → CSV (lowercase columns, rename firstname/lastname/subjectno)
.venv/bin/python scripts/clean_ei_asset_test.py

# 3. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --ei-asset-test-only

# 4. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --ei-asset-test-only
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `jnv_fact_jee_results` | (test_year, application_no) | ~64k |
| `jnv_fact_neet_results` | (test_year, application_no) | ~114k |
| `jnv_fact_selection_test_results` | (district_rank, roll_no) | ~46k |
| `jnv_fact_ei_asset_test_results` | (id) | ~1.6k |

## Adding a new JEE year

1. Create `codemaps/mains/yYYYY.py` with a `CODEMAP` dict (copy nearest year as template).
2. Add one import line to `codemaps/mains/__init__.py` and append to `ALL_CODEMAPS`.
3. Add the raw Excel file entry to `scripts/sources.py` → `RAW_MAINS_FILES`.
4. Re-run steps 3–5 above.

## Adding a new NEET year

1. Create `codemaps/neet/yYYYY.py` with a `CODEMAP` dict (copy nearest year as template).
2. Add one import line to `codemaps/neet/__init__.py` and append to `ALL_NEET_CODEMAPS`.
3. Add the raw Excel file entry to `scripts/sources.py` → `RAW_NEET_FILES`.
4. Re-run steps 3–5 above.

## GCS layout

```
gs://avantifellows-external-data/
  jnv/raw/jee_mains/<stem>.parquet            ← one per raw JEE Mains Excel
  jnv/raw/jee_advanced/<stem>.parquet         ← one per raw JEE Advanced Excel
  jnv/raw/neet/<stem>.parquet                 ← one per raw NEET Excel
  jnv/raw/jnvst/<stem>.parquet                ← raw JNVST Excel
  jnv/raw/ei_asset_test/<stem>.parquet        ← raw EI Asset Test Excel
  jnv/clean/jnv_fact_jee_results.parquet
  jnv/clean/jnv_fact_neet_results.parquet
  jnv/clean/jnv_fact_selection_test_results.parquet
  jnv/clean/jnv_fact_ei_asset_test_results.parquet
```
