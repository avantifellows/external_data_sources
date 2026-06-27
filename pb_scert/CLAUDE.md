# CLAUDE.md — pb_scert/

Guidance for Claude Code when working inside the `pb_scert/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `pb_scert/` unless otherwise noted.

## What this folder is

A transform + ingestion pipeline for the Punjab SCERT (School Education
Department, Punjab) SOE & RSMS Admission Test merit list. Students apply
for Class 11 admission to Schools of Eminence (SOE) and Meritorious Schools
(RSMS). The source file covers three academic years: 2024-25, 2025-26, and
2026-27, with ~325k total student records.

```
raw/SOE & RSMS Admission Test Merit List_ 2024-26 (3 years).xlsx
       │  (sheet: Student List)
       │
       │  scripts/clean_merit_list.py
       ▼
clean/merit_list_clean.csv
       │
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/
  pb_scert/raw/soe_&_rsms_admission_test_merit_list__2024-26_(3_years).parquet
  pb_scert/clean/pb_scert_fact_soe_rsms_admission_merit_list.parquet
       │
       │  scripts/load_bq.py
       ▼
avantifellows.external_data_sources.pb_scert_fact_soe_rsms_admission_merit_list  (asia-south1)
```

## Commands

```bash
# One-time: set up local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Transform raw Excel → clean CSV
.venv/bin/python scripts/clean_merit_list.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py            # raw + clean
.venv/bin/python scripts/upload_to_gcs.py --raw-only
.venv/bin/python scripts/upload_to_gcs.py --clean-only

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/*.xlsx` | No | Source Excel files. Gitignored. |
| `clean/merit_list_clean.csv` | No | Output of `clean_merit_list.py`. Gitignored. |
| `scripts/sources.py` | Yes | GCS bucket, BQ destination, raw file list, table definition. |
| `scripts/clean_merit_list.py` | Yes | Column renames, normalisation → clean CSV. |
| `scripts/upload_to_gcs.py` | Yes | Uploads raw Excel + clean CSV as parquet to GCS. |
| `scripts/load_bq.py` | Yes | Loads clean parquet from GCS → BQ (WRITE_TRUNCATE). |
| `schemas/` | Yes | YAML column documentation for the BQ table. |

## BQ schema

One table in `avantifellows.external_data_sources`:

| Table | Grain | ~Rows |
|---|---|---:|
| `pb_scert_fact_soe_rsms_admission_merit_list` | (academic_year, exam_application_no) | ~326k |

## Key column groups

| Group | Columns |
|---|---|
| Identity | `academic_year`, `exam_application_no`, `g10_board_roll_no` |
| Student | `student_name`, `date_of_birth`, `gender`, `category` |
| School | `g10_school_udise_code`, `g10_school_name`, `g10_school_board` |
| Scores | `reasoning_marks`, `subject_marks`, `total_marks_150` |
| Outcome | `qualification_status`, `applied_for`, `class` |

## Normalised value mappings

| Column | Raw | Canonical |
|---|---|---|
| gender | FEMALE / MALE / TRANSGENDER* | Female / Male / Others |
| category | GENERAL / SC / ST / OBC / BC / EWS | General / SC / ST / OBC / OBC / EWS |
| qualification_status | QUALIFIED / NOT QUALIFIED / PROVISIONALLY QUALIFIED / ABSENT / CANCELLED | Qualified / Not Qualified / Provisionally Qualified / Absent / Cancelled |
| applied_for | BOTH / SCHOOL OF EMINENCE / MERITORIOUS | Both / School of Eminence / Meritorious |

Note: Punjab uses "BC" as a category which maps to the standard "OBC" category.

## Design calls

- **MIS ID / E-Punjab ID dropped.** All values are zero — no usable information.
- **All marks kept as strings.** Marks fields may contain non-numeric values
  in future releases. Cast to INT64 in SQL if needed.
- **`academic_year` is the year field** (not `exam_year`), reflecting that this
  data is organised by admission cycle rather than exam sitting date.
- **WRITE_TRUNCATE on every load.** Table is fully replaced each run.

## Adding a new year

1. If the new year is in the same Excel file, no source change needed — re-run the pipeline.
2. If Punjab publishes a new Excel for additional years, add a `RawFile(...)` entry
   to `RAW_MERIT_LIST_FILES` in `scripts/sources.py` and concatenate in `clean_merit_list.py`.
3. Re-run the full pipeline (clean → upload → load).

## Pitfalls

- **Don't commit the raw Excel file.** The `.gitignore` covers `raw/` and `clean/`.
- **Run `clean_merit_list.py` before `upload_to_gcs.py --clean-only`.** The upload
  script reads the local clean CSV; it will error if it doesn't exist.
- **`g10_board_roll_no` has ~44 null rows.** Source records these as `\N`.
  The clean script replaces them with None.
