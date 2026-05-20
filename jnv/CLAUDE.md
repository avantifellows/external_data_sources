# CLAUDE.md — jnv/

Guidance for Claude Code when working inside the `jnv/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `jnv/` unless otherwise noted.

## What this folder is

A transform + ingestion pipeline for JEE Mains results of JNV (Jawahar
Navodaya Vidyalaya) students — 2021 through 2026. Source data is raw
Excel files received from NTA / internal JNV tracking, one file per year.
The pipeline normalises all years into a single canonical schema aligned
with the production dbt model `fact_student_jee_main_results`.

This is the **heavy transform** template — contrast with
[`nirf/`](../nirf/CLAUDE.md) which is a thin pass-through. The clean step
does non-trivial work: column rename mappings, score/rank normalisation,
category and gender standardisation, 10th/12th board extraction, and
session-level score handling.

```
raw/jee_mains/*.xlsx          (local Excel files, gitignored)
       │
       │  scripts/clean_jee_mains.py    (codemaps-driven transform)
       ▼
clean/jee_mains_clean.csv
       │
       │  scripts/upload_to_gcs.py      (CSV/Excel → parquet → GCS)
       ▼
gs://avantifellows-external-data/
  jnv/raw/jee_mains/<stem>.parquet      (one per raw Excel)
  jnv/clean/jnv_fact_jee_mains_results.parquet
       │
       │  scripts/load_bq.py            (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.jnv_fact_jee_mains_results  (asia-south1)
```

**Single source of truth for pipeline config: [`scripts/sources.py`](scripts/sources.py).**
It declares the GCS bucket/prefix, BQ destination, the clean table
definition, and the list of raw Excel files + primary sheets.

**Single source of truth for schema: [`codemaps/mains/shared.py`](codemaps/mains/shared.py).**
It declares `CANONICAL_COLS`, `COLUMN_TYPES`, and all normalisation helpers.

## Commands

```bash
# One-time: set up local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Transform raw Excel → clean CSV
.venv/bin/python scripts/clean_jee_mains.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py
.venv/bin/python scripts/upload_to_gcs.py --raw-only    # just raw
.venv/bin/python scripts/upload_to_gcs.py --clean-only  # just clean

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

One-time GCP prerequisites:

```bash
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/jee_mains/*.xlsx` | No | Source Excel files per year. Gitignored. |
| `clean/jee_mains_clean.csv` | No | Output of `clean_jee_mains.py`. Gitignored. |
| `codemaps/mains/shared.py` | Yes | Canonical column list, column types, normalisation functions. |
| `codemaps/mains/y20XX.py` | Yes | Per-year column mapping config. One file per year/cohort. |
| `codemaps/mains/__init__.py` | Yes | Registry — `ALL_CODEMAPS` list. Add new years here. |
| `scripts/sources.py` | Yes | GCS bucket, BQ destination, raw file list, clean table definition. |
| `scripts/clean_jee_mains.py` | Yes | Generic transform engine. Reads `ALL_CODEMAPS`, produces clean CSV. |
| `scripts/upload_to_gcs.py` | Yes | Converts Excel + CSV → parquet, uploads to GCS. |
| `scripts/load_bq.py` | Yes | Loads clean parquet from GCS → BQ (WRITE_TRUNCATE). |
| `schemas/` | Yes | YAML column documentation for BQ tables. |

## BQ schema

One table in `avantifellows.external_data_sources`:

| Table | Grain | ~Rows |
|---|---|---:|
| `jnv_fact_jee_mains_results` | (test_year, application_no) | ~55k |

Key column groups (full list in [`codemaps/mains/shared.py`](codemaps/mains/shared.py)):

| Group | Columns |
|---|---|
| Core | `test_year`, `test_name`, `application_no`, `student_full_name`, `dob`, `student_gender`, `category` |
| Identifiers | `school_code`, `roll_no_s1`, `roll_no_s2` |
| Location | `student_state`, `district_12`, `place_of_school`, `jnv_name`, `jnv_region` |
| 12th board | `year_of_passing_12`, `board_12`, `marks_12_obtained`, `marks_12_total`, `marks_12_pct` |
| 10th board | `year_of_passing_10`, `board_10`, `marks_10_obtained`, `marks_10_total`, `marks_10_pct` |
| Final scores | `physics_score`, `chemistry_score`, `maths_score`, `total_score`, `max_score` |
| Session scores | `*_score_s1` (January), `*_score_s2` (April) — null for single-attempt years |
| Ranks | `all_india_rank`, `category_rank`, `all_india_pwd_rank`, `category_pwd_rank`, `obc_rank`, `sc_rank`, `st_rank`, `ews_rank` |
| Qualification | `jee_mains_qualified`, `jee_advanced_qualified`, `jee_prep_qualified`, `adv_prep_category_rank`, `jee_advanced_ineligibility_reason`, `jee_adv_ineligible` |

Column availability by year — null where the source file doesn't carry that data:

| Column group | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Final scores | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Session scores (S1/S2) | — | — | ✓ | — | — | ineligible only |
| Per-category ranks | ✓ | ✓ | ✓ | — | ✓ | — |
| Direct category_rank | — | — | — | ✓ | — | — |
| 10th board marks | — | — | — | ✓ | — | ✓ |
| 12th board marks | ✓ | ✓ | — | ✓ | — | ✓ |
| JNV metadata | partial | ✓ | — | ✓ | ✓ | — |
| Adv/prep qualification | — | — | — | — | ✓ | — |
| jee_adv_ineligible (NELIG_ADV / 2026 file) | ✓ | ✓ | ✓ | — | — | ✓ |

## Codemap architecture

The clean engine (`clean_jee_mains.py`) is fully config-driven — it
contains no year-specific logic. All year-specific knowledge lives in
`codemaps/mains/`.

**To add a new year:**
1. Create `codemaps/mains/yYYYY.py` with a `CODEMAP` dict:
   ```python
   CODEMAP = {
       "source":    {"file": "...", "sheet": "...", "header": 0},
       "constants": {"test_year": "YYYY", "test_name": "JEE Mains Overall",
                     "max_score": 300, "jee_adv_ineligible": None},
       "columns":   {"application_no": ["APPNO"], ...},
       # optional:
       "post_transform": my_fn,   # fn(raw_df, out_df) → out_df
   }
   ```
2. Add one import line to `codemaps/mains/__init__.py` and append to
   `ALL_CODEMAPS`.
3. Add the raw Excel file to `scripts/sources.py` → `RAW_FILES`.
4. Re-run the pipeline.

**Codemap keys:**
- `source` — file, sheet, and optional `header_fallback` (for files with a
  blank first row — see `y2026_ineligible.py`).
- `constants` — values written as-is to every row (test_year, max_score,
  eligible). A constant that also appears in `columns` will be ignored in
  favour of the constant.
- `columns` — maps canonical column name → list of candidate raw column
  names (first found wins, case-insensitive). Special key `_pwd_raw` feeds
  the category normaliser's PWD prefix logic.
- `post_transform` — optional `fn(raw_df, out_df) → out_df` hook for
  anything that can't be expressed as a simple column mapping (e.g. 2025's
  per-category PWD ranks → `category_pwd_rank`).

**Column types** (defined in `shared.py` → `COLUMN_TYPES`):

| Type | Transform applied |
|---|---|
| `constant` | Value from `constants` dict, no raw column read |
| `str` | Raw value passed through |
| `float` | `to_float()` — handles ABS, ---, NaN, empty |
| `gender` | `normalize_gender()` → Male / Female / Others |
| `category` | `normalize_category()` → Gen / Gen-EWS / OBC / SC / ST / PWD-* |
| `appeared` | `appeared()` → False if ABS or null, else True |
| `boolean` | `to_boolean()` → True for yes/1/true/eligible; None if missing |

## Design calls worth knowing before you change them

- **Engine has zero year-specific logic.** `clean_jee_mains.py` is a
  generic loop over `ALL_CODEMAPS`. If you find yourself adding an `if
  year == 2024` check there, put it in a `post_transform` in the codemap
  instead.
- **Schema aligned with `fact_student_jee_main_results`.** Column names,
  gender values (Male/Female/Others), and category values
  (Gen/Gen-EWS/OBC/SC/ST/PWD-*) intentionally mirror the production dbt
  fact table so analysts can join or compare without re-mapping.
- **2025 uses the All JNV Candidates file, not JEE Mains 2025.xlsx.**
  `JEE 2025 - All JNV Candidates.xlsx` (12,103 rows) is the full JNV
  cohort and supersedes `JEE Mains 2025.xlsx` (4,037 rows, a subset).
  The All JNV file also carries richer JNV metadata and adv/prep flags.
- **2026 is split across two files.** `y2026_eligible.py` covers candidates
  who passed Class 12 in 2025 or later (`jee_adv_ineligible = False`) — these
  are the standard 2026 cohort eligible for JEE Advanced. `y2026_ineligible.py`
  covers 2+ year droppers who passed Class 12 before 2024 (`jee_adv_ineligible =
  True`) — they can sit JEE Mains but are ineligible for JEE Advanced;
  `jee_advanced_ineligibility_reason` carries the NTA remark explaining why. Both
  share `test_year = "2026"` and are deduped together.
- **`category_rank` is derived in post-processing for all years except 2024.**
  2024 has a direct `Category Rank` column. For other years, `post_process`
  in the engine picks from `obc_rank` / `sc_rank` / `st_rank` / `ews_rank`
  based on the candidate's normalised category.
- **`marks_12_pct` and `marks_10_pct` are computed where missing.**
  `post_process` fills these from `obtained/total × 100` if the pct column
  is null but both mark columns are present.
- **WRITE_TRUNCATE on every load.** The BQ table is fully replaced each
  run. No incremental logic — the source files change as new years are
  added and historical files are occasionally corrected.

## Pitfalls

- **Don't commit raw Excel files.** The `.gitignore` covers `raw/` and
  `clean/`. Authoritative raw copies live in GCS under
  `gs://avantifellows-external-data/jnv/raw/jee_mains/`.
- **Run `clean_jee_mains.py` before `upload_to_gcs.py --clean-only`.**
  The upload script reads `clean/jee_mains_clean.csv`; it will exit with
  an error if that file doesn't exist.
- **Column names in raw files are case-sensitive and vary by year.**
  Always add new raw column name candidates to the codemap's `columns`
  list rather than assuming the exact capitalisation. The engine matches
  case-insensitively.
- **2026 ineligible file has a malformed header row.** The engine retries
  with `header=1` if the first read yields mostly Unnamed columns — this
  is driven by `header_fallback: 1` in `y2026_ineligible.py`. Don't
  remove it.
- **Session scores (`*_score_s1`, `*_score_s2`) are null for most years.**
  Filter with `WHERE total_score_s1 IS NOT NULL` before session-level
  analysis. Only 2023 and the 2026 ineligible cohort have them.
- **`total_score` for JEE Mains is a percentile (0–100), not raw marks.**
  `max_score = 300` is retained for reference but should not be used as a
  denominator for the overall score.
- **`test_year` is a STRING, not INT.** This matches the production
  `fact_student_jee_main_results` column type. Cast explicitly in SQL if
  needed: `CAST(test_year AS INT64)`.
