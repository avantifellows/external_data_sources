# aishe

AISHE HE Directory data ingestion → BigQuery.

The [AISHE HE Directory](https://dashboard.aishe.gov.in/hedirectory/#/hedirectory)
is the Ministry of Education's live public registry of all higher-education
institutions in India — colleges, universities, standalone institutes, R&D
bodies, and PM Vidyalaxmi-eligible institutions. This pipeline converts the
five dashboard tab exports (Excel) into five BigQuery tables.

**Source:** Ministry of Education, Government of India —
https://dashboard.aishe.gov.in/hedirectory/#/hedirectory

## Pipeline at a glance

```
aishe/raw/*.xlsx               (manual download; gitignored)
       │ scripts/build_clean.py
       ▼
aishe/clean/*.parquet          (gitignored)
       │ scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/aishe/clean/*.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.aishe_fact_*   (asia-south1, 5 tables)
```

## Tables produced

| Table | ~Rows | Description |
|---|---:|---|
| `aishe_fact_colleges` | 53,500 | Affiliated/constituent colleges with state, district, type, management, and parent university |
| `aishe_fact_universities` | 1,400 | All degree-awarding universities (central, state, deemed, private) |
| `aishe_fact_standalone` | 16,700 | Standalone institutions — polytechnics, nursing, teacher-training, etc. |
| `aishe_fact_rd` | 280 | R&D institutes (ISRO, CSIR, ICAR, ICMR, etc.) with administrative ministry |
| `aishe_fact_pm_vidyalaxmi` | 1,050 | Institutions eligible under the PM Vidyalaxmi scholarship scheme |

All tables include an **`institution_types`** column — a comma-separated list
of matched types from a 17-type vocabulary (Engineering, Polytechnic, Medical,
Law, Agriculture, Ayurveda, …) derived from keyword matching on institution
names. NULL where no type could be inferred.

Schemas: [`schemas/aishe_directory.yaml`](schemas/aishe_directory.yaml)
Domain primer: [`schemas/README.md`](schemas/README.md)

## First-time setup

```bash
# GCS bucket and BQ dataset (skip if already created for other sources)
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources

# Python env (from inside aishe/)
python3 -m venv .venv
.venv/bin/pip install pandas openpyxl pyarrow rapidfuzz google-cloud-bigquery google-cloud-storage

# Authenticate
gcloud auth application-default login
```

## Running the pipeline

### Step 1 — Download the raw Excel files

Go to https://dashboard.aishe.gov.in/hedirectory/#/hedirectory, open each
tab, and click **Export**. Save the files into `aishe/raw/` using these
exact filenames (as they come from the dashboard):

```
raw/College-ALL COLLEGE (1).xlsx
raw/University-ALL UNIVERSITIES (1).xlsx
raw/Standalone-ALL STANDALONE.xlsx
raw/R & D Institutes.xlsx
raw/vidya_lakshmiAll.xlsx
```

### Step 2 — Build clean parquets

```bash
.venv/bin/python scripts/build_clean.py             # all five
.venv/bin/python scripts/build_clean.py --dry-run   # preview stats, no write
```

### Step 3 — Upload to GCS

```bash
.venv/bin/python scripts/upload_to_gcs.py
```

### Step 4 — Load to BigQuery

```bash
.venv/bin/python scripts/load_bq.py
```

Each step accepts `--table <bq_table_name>` to operate on a single table
and `--dry-run` to preview without side effects.

## Refreshing data

The AISHE dashboard is updated continuously. To refresh:

1. Re-download the Excel files from the dashboard into `raw/` (overwrite).
2. Re-run `build_clean.py` → `upload_to_gcs.py` → `load_bq.py`.

`WRITE_TRUNCATE` makes BQ loads idempotent — no manual cleanup needed.
