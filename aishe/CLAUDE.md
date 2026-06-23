# CLAUDE.md — aishe/

Guidance for Claude Code when working inside the `aishe/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `aishe/` unless otherwise noted.

## What this folder is

A one-shot ingestion pipeline for the **AISHE HE Directory** — the Ministry
of Education's live public registry of all higher-education institutions in
India, published at https://dashboard.aishe.gov.in/hedirectory/#/hedirectory.

The directory has five tabs (Colleges, Universities, Standalone, R&D, PM
Vidyalaxmi), each exported as an Excel file. This pipeline reads those five
files, cleans them (rename + whitespace-trim only — no derived columns), and
loads them into BigQuery as five `aishe_fact_*` tables.

This is the **heavy-transform** pattern (like `plfs/`) — raw Excel files need
real parsing before they are BQ-loadable. The pipeline is not a production
service; it runs locally on demand when a new dashboard export is needed.

## Pipeline shape

```
dashboard.aishe.gov.in/hedirectory   (manual Excel export, one per tab)
        │
        ▼
aishe/raw/*.xlsx                     (gitignored — place here after download)
        │
        │  scripts/build_clean.py    (parse + normalise → parquet)
        ▼
aishe/clean/*.parquet                (gitignored — regenerable from raw)
        │
        │  scripts/upload_to_gcs.py  (upload to GCS)
        ▼
gs://avantifellows-external-data/aishe/clean/*.parquet
        │
        │  scripts/load_bq.py        (load_table_from_uri, WRITE_TRUNCATE)
        ▼
avantifellows.external_data_sources.aishe_fact_*   (5 tables, asia-south1)
```

Single source of truth for filenames, GCS URIs, and BQ destinations:
[`scripts/sources.py`](scripts/sources.py).

## Commands

```bash
# Local Python env
python3 -m venv .venv
.venv/bin/pip install pandas openpyxl pyarrow google-cloud-bigquery google-cloud-storage

# 1. Download the five Excel files from the dashboard and drop into raw/:
#    raw/College-ALL COLLEGE.xlsx
#    raw/University-ALL UNIVERSITIES.xlsx
#    raw/Standalone-ALL STANDALONE.xlsx
#    raw/R & D Institutes.xlsx
#    raw/vidya_lakshmiAll.xlsx

# 2. Build clean parquets (parse + normalise)
.venv/bin/python scripts/build_clean.py               # all five
.venv/bin/python scripts/build_clean.py --table aishe_fact_colleges  # one only
.venv/bin/python scripts/build_clean.py --dry-run     # validate + row counts, no write

# 3. Upload to GCS
.venv/bin/python scripts/upload_to_gcs.py
.venv/bin/python scripts/upload_to_gcs.py --dry-run

# 4. Load to BigQuery (post-approval only — see top-level CLAUDE.md)
.venv/bin/python scripts/load_bq.py
.venv/bin/python scripts/load_bq.py --dry-run
```

## BQ schema (what `load_bq.py` produces)

Five tables in `avantifellows.external_data_sources`. Authoritative column
docs in [`schemas/aishe_directory.yaml`](schemas/aishe_directory.yaml).

| Table | Rows | Source file |
|---|---:|---|
| `aishe_fact_colleges` | ~53,500 | College-ALL COLLEGE.xlsx |
| `aishe_fact_universities` | ~1,400 | University-ALL UNIVERSITIES.xlsx |
| `aishe_fact_standalone_institutions` | ~16,700 | Standalone-ALL STANDALONE.xlsx |
| `aishe_fact_research_institutions` | ~280 | R & D Institutes.xlsx |
| `aishe_fact_pm_vidyalaxmi_eligible_institutions` | ~1,050 | vidya_lakshmiAll.xlsx |

Every column is a raw passthrough from the source export — `build_clean.py`
only renames columns to snake_case and trims whitespace. No derived or
computed columns are added; any classification/enrichment is the
responsibility of downstream analysis.

## Excel parsing notes

Each raw Excel file has a 2-row header before the actual column headers:
- Row 0: title (e.g. "ALL COLLEGE")
- Row 1: export timestamp (e.g. "(As on Date:  12-6-2026  0:54:10)")
- Row 2: actual column headers

`build_clean.py` passes `header=2` to `pd.read_excel()` to skip these.

The Colleges and Standalone files have a typo in the source: `"Manegement"`
instead of `"Management"`. `sources.py` handles this in the rename map.

## Pitfalls

- **Don't commit raw/*.xlsx.** The `.gitignore` enforces this.
- **Don't commit clean/*.parquet.** Also gitignored; authoritative copy
  is in GCS.
- **Don't load to BQ without an explicit go.** Stage parquet to GCS first;
  load to BQ only post-approval / post-merge.
- **Refreshing:** when a newer dashboard export is available, drop the new
  Excel files into `raw/` and re-run the full pipeline. `WRITE_TRUNCATE`
  makes BQ loads idempotent.
- **PM Vidyalaxmi is a subset, not a new institution type.** Its
  `aishe_code` values also appear in `aishe_fact_colleges`,
  `aishe_fact_universities`, or `aishe_fact_standalone_institutions` (all three
  kinds are eligible). Use `aishe_code` to join for full attributes.
