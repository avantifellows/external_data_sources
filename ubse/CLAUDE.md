# CLAUDE.md — ubse/

Guidance for Claude Code when working inside the `ubse/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `ubse/` unless otherwise noted.

## What this folder is

A transform + ingestion pipeline for UBSE (Uttarakhand Board of School
Education) Grade 10 and Grade 12 board exam results. Source data is one
Excel file per grade per year.

This pipeline follows the same **wide → long** pattern as the JNV CBSE board
results pipelines (`jnv/scripts/clean_board_results_10th.py`): each wide
subject slot (SUB1–SUB6) is unpivoted into one row per student per subject.

```
raw/G10th _ UBSE Board data 2026.xlsx   (sheet: HS_NET)
raw/G12th _UBSE Board data - 2026.xlsx  (sheet: int_net)
       │
       │  scripts/clean_grade10.py
       │  scripts/clean_grade12.py
       ▼
clean/grade10_clean.csv
clean/grade12_clean.csv
       │
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/
  ubse/raw/grade10/<stem>.parquet
  ubse/raw/grade12/<stem>.parquet
  ubse/clean/ubse_fact_grade10_results.parquet
  ubse/clean/ubse_fact_grade12_results.parquet
       │
       │  scripts/load_bq.py
       ▼
avantifellows.external_data_sources.ubse_fact_grade10_results  (asia-south1)
avantifellows.external_data_sources.ubse_fact_grade12_results  (asia-south1)
```

## Commands

```bash
# One-time: set up local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Transform raw Excel → clean CSVs
.venv/bin/python scripts/clean_grade10.py
.venv/bin/python scripts/clean_grade12.py

# 2. Upload raw + clean to GCS
.venv/bin/python scripts/upload_to_gcs.py             # both grades
.venv/bin/python scripts/upload_to_gcs.py --grade10-only
.venv/bin/python scripts/upload_to_gcs.py --grade12-only
.venv/bin/python scripts/upload_to_gcs.py --raw-only
.venv/bin/python scripts/upload_to_gcs.py --clean-only

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py                   # both grades
.venv/bin/python scripts/load_bq.py --grade10-only
.venv/bin/python scripts/load_bq.py --grade12-only
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/*.xlsx` | No | Source Excel files per grade per year. Gitignored. |
| `clean/grade10_clean.csv` | No | Output of `clean_grade10.py`. Gitignored. |
| `clean/grade12_clean.csv` | No | Output of `clean_grade12.py`. Gitignored. |
| `scripts/sources.py` | Yes | GCS bucket, BQ destination, raw file list, table definitions. |
| `scripts/clean_grade10.py` | Yes | Wide → long transform for Grade 10. |
| `scripts/clean_grade12.py` | Yes | Wide → long transform for Grade 12. |
| `scripts/upload_to_gcs.py` | Yes | Uploads raw Excel + clean CSV as parquet to GCS. |
| `scripts/load_bq.py` | Yes | Loads clean parquet from GCS → BQ (WRITE_TRUNCATE). |
| `schemas/` | Yes | YAML column documentation for both BQ tables. |

## BQ schema

Two tables in `avantifellows.external_data_sources`:

| Table | Grain | ~Rows |
|---|---|---:|
| `ubse_fact_grade10_results` | (exam_year, roll_no, subject_slot) | ~620k |
| `ubse_fact_grade12_results` | (exam_year, roll_no, subject_slot) | ~440k |

Row counts are ~5.5 subjects per student × 112k students (Grade 10) and
~4.3 subjects per student × 103k students (Grade 12).

## Key column groups

| Group | Grade 10 | Grade 12 |
|---|---|---|
| Identity | `district_code`, `school_code`, `roll_no`, `registration_no` | Same |
| Student | `student_name`, `father_name`, `mother_name`, `date_of_birth` | No `date_of_birth` |
| Demographics | `gender`, `caste`, `school_type` | + `stream` |
| Subject | `subject_slot`, `subject_name`, `theory_marks`, `practical_marks`, `internal_marks`, `subject_total`, `subject_result`, `subject_grade` | Same (INTMKS before PRAMKS in source) |
| Overall | `total_marks_obtained`, `total_max_marks`, `result`, `division`, `grace_marks` | + `f1_total`, `f2_total` |

## Normalised value mappings

| Column | Raw | Canonical |
|---|---|---|
| gender | 1 / 2 / 3 | Male / Female / Others |
| caste | 1 / 2 / 3 / 4 | SC / ST / OBC / General |
| stream (G12) | A / B / C / F1 / F2 | Arts / Science / Commerce / Vocational (Year 1) / Vocational (Year 2) |
| school_type | A / B / C / D | Government / Government Aided / Private (Unaided) / Central Government |
| result | PASS / FAIL or FAILED / ABSENT / PADL / W-INCOMPLE / PASSED IN | Pass / Fail / Absent / Pass (ADL) / Withheld / Pass (Compartment) |

## Adding a new year

1. Add the new raw Excel file to `raw/`.
2. Add a `RawFile(...)` entry to `RAW_GRADE10_FILES` or `RAW_GRADE12_FILES`
   in `scripts/sources.py`.
3. If the new file has different column names, add a rename entry to
   `COLUMN_RENAMES` in the relevant clean script. Use a `YEAR_COLUMN_FIXES`
   dict (as in the JNV board scripts) if the fix is year-specific.
4. Re-run the full pipeline (clean → upload → load).

## Design calls

- **Long format.** Wide subject slots (SUB1–SUB6) are unpivoted into one row
  per student per subject. This matches the JNV CBSE board results pipeline
  and is robust to UBSE adding or rearranging subject slots in future years.
- **Grade 12 INTMKS/PRAMKS column order.** In the source file, Grade 12 has
  SUBnTHMKS, SUBnINTMKS, SUBnPRAMKS (internal before practical), while
  Grade 10 has the reverse. Both scripts read columns by name so this
  doesn't affect the output.
- **All marks columns kept as strings.** Marks fields like SUBnTOT contain
  zero-padded values (e.g. "063") and occasional non-numeric entries.
  Type coercion is left to downstream dbt models.
- **WRITE_TRUNCATE on every load.** Tables are fully replaced each run.
- **`exam_year` is a STRING.** Cast to INT64 in SQL if needed.

## Pitfalls

- **Don't commit raw Excel files.** The `.gitignore` covers `raw/` and
  `clean/`. Authoritative raw copies live in GCS.
- **Run clean scripts before `upload_to_gcs.py --clean-only`.** The upload
  script reads the local clean CSVs; it will error if they don't exist.
- **Grade 12 REGCD is the last column.** Unlike Grade 10 where REGCD is
  the 4th column, Grade 12 has it at the end. `COLUMN_RENAMES` handles
  this — no special treatment needed.
- **SUB6 is nearly empty in Grade 12.** Only ~344 vocational students use
  slot 6. The unpivot drops null-name rows, so this doesn't inflate counts.
- **`total_max_marks` is "0500", not 500.** It's zero-padded in the source.
  Cast to INT64 before arithmetic in SQL.