# CLAUDE.md — jnv/

Guidance for Claude Code when working inside the `jnv/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `jnv/` unless otherwise noted.

## What this folder is

A transform + ingestion pipeline for JEE Mains, JEE Advanced, NEET, JNVST
selection test, and EI Asset Test results of JNV (Jawahar Navodaya Vidyalaya)
students. Source data is raw Excel files received from NTA / internal JNV
tracking, one file per year per exam.

- **JEE pipeline** — 2021 through 2026. Schema aligned with production dbt
  model `fact_student_jee_main_results`.
- **NEET pipeline** — 2021 through 2025. Schema aligned with production dbt
  model `fact_student_neet_results`.
- **JNVST pipeline** — 2018 selection test results. Raw load with minimal
  cleaning (column renames, area/gender value mapping).
- **EI Asset Test pipeline** — EI ASSET assessment scores by student and
  subject. Raw load with column renames only.

This is the **heavy transform** template — contrast with
[`nirf/`](../nirf/CLAUDE.md) which is a thin pass-through. The clean step
does non-trivial work: column rename mappings, score/rank normalisation,
category and gender standardisation, 10th/12th board extraction, session-level
score handling, and merging JEE Mains with JEE Advanced rank data.

**JEE pipeline:**
```
raw/jee_mains/*.xlsx          (local Excel files, gitignored)
raw/jee_advanced/*.xlsx       (local Excel files, gitignored)
       │
       │  scripts/clean_jee.py    (codemaps-driven transform + merge)
       ▼
clean/jee_clean.csv
       │
       │  scripts/upload_to_gcs.py --jee-only   (CSV/Excel → parquet → GCS)
       ▼
gs://avantifellows-external-data/
  jnv/raw/jee_mains/<stem>.parquet      (one per raw mains Excel)
  jnv/raw/jee_advanced/<stem>.parquet   (one per raw advanced Excel)
  jnv/clean/jnv_fact_jee_results.parquet
       │
       │  scripts/load_bq.py --jee-only  (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.jnv_fact_jee_results  (asia-south1)
```

**NEET pipeline:**
```
raw/neet/*.xlsx               (local Excel files, gitignored)
       │
       │  scripts/clean_neet.py   (codemaps-driven transform)
       ▼
clean/neet_clean.csv
       │
       │  scripts/upload_to_gcs.py --neet-only  (CSV/Excel → parquet → GCS)
       ▼
gs://avantifellows-external-data/
  jnv/raw/neet/<stem>.parquet           (one per raw NEET Excel)
  jnv/clean/jnv_fact_neet_results.parquet
       │
       │  scripts/load_bq.py --neet-only  (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.jnv_fact_neet_results  (asia-south1)
```

**JNVST pipeline:**
```
raw/jnvst/*.xlsx              (local Excel file, gitignored)
       │
       │  scripts/clean_jnvst.py  (column renames, area/gender value mapping)
       ▼
clean/jnvst_clean.csv
       │
       │  scripts/upload_to_gcs.py --jnvst-only  (CSV/Excel → parquet → GCS)
       ▼
gs://avantifellows-external-data/
  jnv/raw/jnvst/<stem>.parquet
  jnv/clean/jnv_fact_selection_test_results.parquet
       │
       │  scripts/load_bq.py --jnvst-only  (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.jnv_fact_selection_test_results  (asia-south1)
```

**EI Asset Test pipeline:**
```
raw/ei_asset_test/*.xlsx      (local Excel file, gitignored)
       │
       │  scripts/clean_ei_asset_test.py  (column renames only)
       ▼
clean/ei_asset_test_clean.csv
       │
       │  scripts/upload_to_gcs.py --ei-asset-test-only  (CSV/Excel → parquet → GCS)
       ▼
gs://avantifellows-external-data/
  jnv/raw/ei_asset_test/<stem>.parquet
  jnv/clean/jnv_fact_ei_asset_test_results.parquet
       │
       │  scripts/load_bq.py --ei-asset-test-only  (load_table_from_uri, PARQUET)
       ▼
avantifellows.external_data_sources.jnv_fact_ei_asset_test_results  (asia-south1)
```

**Single source of truth for pipeline config: [`scripts/sources.py`](scripts/sources.py).**
It declares the GCS bucket/prefix, BQ destination, all clean table
definitions, and the list of raw Excel files + primary sheets for every
pipeline.

**Single source of truth for schema: [`codemaps/mains/shared.py`](codemaps/mains/shared.py).**
It declares `CANONICAL_COLS`, `COLUMN_TYPES`, and all normalisation helpers.

## Commands

```bash
# One-time: set up local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# ── JEE pipeline ──────────────────────────────────────────────────────────────
# 1. Transform raw Excel → clean CSV (mains + advanced merged)
.venv/bin/python scripts/clean_jee.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --jee-only
.venv/bin/python scripts/upload_to_gcs.py --raw-only    # raw only (JEE + NEET)
.venv/bin/python scripts/upload_to_gcs.py --clean-only  # clean only (JEE + NEET)

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --jee-only

# ── NEET pipeline ─────────────────────────────────────────────────────────────
# 1. Transform raw Excel → clean CSV
.venv/bin/python scripts/clean_neet.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --neet-only

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --neet-only

# ── JNVST pipeline ────────────────────────────────────────────────────────────
# 1. Clean raw Excel → CSV (column renames, area/gender value mapping)
.venv/bin/python scripts/clean_jnvst.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --jnvst-only

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --jnvst-only

# ── EI Asset Test pipeline ────────────────────────────────────────────────────
# 1. Clean raw Excel → CSV (column renames only)
.venv/bin/python scripts/clean_ei_asset_test.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --ei-asset-test-only

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --ei-asset-test-only

# ── JEE + NEET at once ────────────────────────────────────────────────────────
.venv/bin/python scripts/upload_to_gcs.py   # upload JEE + NEET raw + clean
.venv/bin/python scripts/load_bq.py         # load JEE + NEET tables
```

One-time GCP prerequisites:

```bash
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/jee_mains/*.xlsx` | No | Source mains Excel files per year. Gitignored. |
| `raw/jee_advanced/*.xlsx` | No | Source advanced Excel files per year. Gitignored. |
| `raw/neet/*.xlsx` | No | Source NEET Excel files per year. Gitignored. |
| `raw/jnvst/*.xlsx` | No | Source JNVST Excel file. Gitignored. |
| `raw/ei_asset_test/*.xlsx` | No | Source EI Asset Test Excel file. Gitignored. |
| `clean/jee_clean.csv` | No | Output of `clean_jee.py`. Gitignored. |
| `clean/neet_clean.csv` | No | Output of `clean_neet.py`. Gitignored. |
| `clean/jnvst_clean.csv` | No | Output of `clean_jnvst.py`. Gitignored. |
| `clean/ei_asset_test_clean.csv` | No | Output of `clean_ei_asset_test.py`. Gitignored. |
| `codemaps/mains/shared.py` | Yes | JEE canonical column list, column types, normalisation functions. |
| `codemaps/mains/y20XX.py` | Yes | Per-year mains column mapping config. |
| `codemaps/mains/__init__.py` | Yes | Registry — `ALL_CODEMAPS` list. |
| `codemaps/advanced/shared.py` | Yes | Advanced column list, column types, rank normalisation. |
| `codemaps/advanced/y20XX.py` | Yes | Per-year advanced column mapping config. |
| `codemaps/advanced/__init__.py` | Yes | Registry — `ALL_ADV_CODEMAPS` list. |
| `codemaps/neet/shared.py` | Yes | NEET canonical column list, column types, normalisation functions. |
| `codemaps/neet/y20XX.py` | Yes | Per-year NEET column mapping config. |
| `codemaps/neet/__init__.py` | Yes | Registry — `ALL_NEET_CODEMAPS` list. Add new years here. |
| `codemaps/jnvst/shared.py` | Yes | JNVST column types and `apply_dtypes`. |
| `codemaps/ei_asset_test/shared.py` | Yes | EI Asset Test column types and `apply_dtypes`. |
| `scripts/sources.py` | Yes | GCS bucket, BQ destination, raw file lists, clean table definitions. |
| `scripts/clean_jee.py` | Yes | JEE transform engine: mains + advanced → merged clean CSV. |
| `scripts/clean_neet.py` | Yes | NEET transform engine: codemap-driven → clean CSV. |
| `scripts/clean_jnvst.py` | Yes | JNVST clean: column renames + area/gender value mapping → CSV. |
| `scripts/clean_ei_asset_test.py` | Yes | EI Asset Test clean: column renames → CSV. |
| `scripts/upload_to_gcs.py` | Yes | Converts Excel + CSV → parquet, uploads to GCS (all pipelines). |
| `scripts/load_bq.py` | Yes | Loads clean parquet from GCS → BQ (WRITE_TRUNCATE). All pipelines. |
| `schemas/` | Yes | YAML column documentation for BQ tables. |

## BQ schema

Four tables in `avantifellows.external_data_sources`:

| Table | Grain | ~Rows |
|---|---|---:|
| `jnv_fact_jee_results` | (test_year, application_no) | ~64k |
| `jnv_fact_neet_results` | (test_year, application_no) | ~114k |
| `jnv_fact_selection_test_results` | (district_rank, roll_no) | ~46k |
| `jnv_fact_ei_asset_test_results` | (id) | ~1.6k |

Key column groups (full list in [`codemaps/mains/shared.py`](codemaps/mains/shared.py)):

| Group | Columns |
|---|---|
| Core | `test_year`, `test_name`, `application_no`, `student_full_name`, `dob`, `student_gender`, `category` |
| Identifiers | `school_code`, `roll_no_s1`, `roll_no_s2` |
| Location | `student_state`, `district_12`, `place_of_school`, `jnv_name`, `jnv_region` |
| 12th board | `year_of_passing_12`, `board_12`, `marks_12_obtained`, `marks_12_total`, `marks_12_pct` |
| 10th board | `year_of_passing_10`, `board_10`, `marks_10_obtained`, `marks_10_total`, `marks_10_pct` |
| Mains scores | `mains_physics_score`, `mains_chemistry_score`, `mains_maths_score`, `mains_total_score`, `mains_max_score` |
| Mains session scores | `mains_*_score_s1` (January), `mains_*_score_s2` (April) — null for single-attempt years |
| Mains ranks | `mains_all_india_rank`, `mains_category_rank`, `mains_all_india_pwd_rank`, `mains_category_pwd_rank`, `mains_obc_rank`, `mains_sc_rank`, `mains_st_rank`, `mains_ews_rank` |
| Mains qualification | `jee_mains_qualified_from_data`, `jee_mains_qualified_calculated`, `jee_mains_qualified` |
| Adv eligibility | `jee_adv_ineligible`, `jee_adv_ineligibility_reason` |
| Advanced ranks | `adv_all_india_rank`, `adv_category_rank`, `adv_all_india_pwd_rank`, `adv_category_pwd_rank`, `adv_obc_rank`, `adv_sc_rank`, `adv_st_rank`, `adv_ews_rank`, `adv_*_pwd_rank`, `adv_prep_*_rank` |
| Advanced qualification | `jee_advanced_qualified_from_data`, `jee_advanced_qualified_calculated`, `jee_advanced_qualified` |
| Prep qualification | `jee_prep_qualified_from_data`, `jee_prep_qualified_calculated`, `jee_prep_qualified` |

Column availability by year — null where the source file doesn't carry that data:

| Column group | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Mains final scores | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Mains session scores (S1/S2) | — | — | ✓ | — | — | ineligible only |
| Mains per-category ranks | ✓ | ✓ | ✓ | — | ✓ | — |
| Mains direct category_rank | — | — | — | ✓ | — | — |
| 10th board marks | — | — | — | ✓ | — | ✓ |
| 12th board marks | ✓ | ✓ | — | ✓ | — | ✓ |
| JNV metadata | partial | ✓ | — | ✓ | ✓ | — |
| jee_adv_ineligible | ✓ | ✓ | ✓ | — | — | ✓ |
| Advanced ranks (from adv Excel) | — | — | — | ✓ | ✓ | — |
| Adv/prep qualification flags | — | — | — | — | ✓ | — |

## Codemap architecture

The clean engine (`clean_jee.py`) is fully config-driven — it contains no
year-specific logic. All year-specific knowledge lives in `codemaps/mains/`
and `codemaps/advanced/`.

**To add a new mains year:**
1. Create `codemaps/mains/yYYYY.py` with a `CODEMAP` dict:
   ```python
   CODEMAP = {
       "source":    {"file": "...", "sheet": "...", "header": 0},
       "constants": {"test_year": "YYYY", "test_name": "JEE Mains Overall",
                     "mains_max_score": 300, "jee_adv_ineligible": None},
       "columns":   {"application_no": ["APPNO"], ...},
       # optional:
       "post_transform": my_fn,   # fn(raw_df, out_df) → out_df
   }
   ```
2. Add one import line to `codemaps/mains/__init__.py` and append to `ALL_CODEMAPS`.
3. Add the raw Excel file to `scripts/sources.py` → `RAW_MAINS_FILES`.
4. Re-run the pipeline.

**To add a new advanced year:**
1. Create `codemaps/advanced/yYYYY.py` with a `CODEMAP` dict:
   ```python
   CODEMAP = {
       "source":    {"file": "...", "sheet": "...", "header": 0},
       "constants": {"test_year": "YYYY", "adv_appeared": True},
       "zero_is_null": False,   # True if file uses 0 instead of NaN for missing ranks
       "columns":   {"application_no": ["..."], "adv_all_india_rank": ["CRL"], ...},
   }
   ```
2. Add one import line to `codemaps/advanced/__init__.py` and append to `ALL_ADV_CODEMAPS`.
3. Add the raw Excel file to `scripts/sources.py` → `RAW_ADV_FILES`.
4. Re-run the pipeline.

**To add a new NEET year:**
1. Create `codemaps/neet/yYYYY.py` with a `CODEMAP` dict:
   ```python
   CODEMAP = {
       "source":    {"file": "NEET YYYY.xlsx", "sheet": "Sheet1", "header": 0},
       "constants": {"test_year": "YYYY", "test_name": "NEET", "neet_max_score": 720},
       "columns":   {"application_no": ["APPLICATION NUMBER"], ...},
       # optional:
       "post_transform": my_fn,   # fn(raw_df, out_df) → out_df
   }
   ```
2. Add one import line to `codemaps/neet/__init__.py` and append to `ALL_NEET_CODEMAPS`.
3. Add the raw Excel file to `scripts/sources.py` → `RAW_NEET_FILES`.
4. Re-run `clean_neet.py`, `upload_to_gcs.py --neet-only`, `load_bq.py --neet-only`.

**Codemap keys:**
- `source` — file, sheet, and optional `header_fallback` (for files with a
  blank first row — see `y2026_ineligible.py`).
- `constants` — values written as-is to every row. A constant that also
  appears in `columns` will be ignored in favour of the constant.
- `columns` — maps canonical column name → list of candidate raw column
  names (first found wins, case-insensitive). Special key `_pwd_raw` feeds
  the category normaliser's PWD prefix logic (mains only).
- `zero_is_null` — advanced codemaps only. When True, rank values of 0 are
  treated as missing (2025 advanced file uses this convention).
- `post_transform` — optional `fn(raw_df, out_df) → out_df` hook for
  anything that can't be expressed as a simple column mapping.

**Column types** (defined in `shared.py` → `COLUMN_TYPES`):

| Type | Transform applied |
|---|---|
| `constant` | Value from `constants` dict, no raw column read |
| `str` | Raw value passed through |
| `float` | `to_float()` — handles ABS, ---, NaN, empty, and mixed fractions like "55 2/5" |
| `gender` | `normalize_gender()` → Male / Female / Others |
| `category` | `normalize_category()` → Gen / Gen-EWS / OBC / SC / ST / PWD-* |
| `appeared` | `appeared()` → False if ABS or null, else True |
| `boolean` | `to_boolean()` → True for yes/1/true/eligible; None if missing |

## Design calls worth knowing before you change them

- **Engine has zero year-specific logic.** `clean_jee.py` is a generic loop
  over `ALL_CODEMAPS` (mains) and `ALL_ADV_CODEMAPS` (advanced). If you find
  yourself adding an `if year == 2024` check there, put it in a
  `post_transform` in the codemap instead.
- **Schema aligned with `fact_student_jee_main_results`.** Column names,
  gender values (Male/Female/Others), and category values
  (Gen/Gen-EWS/OBC/SC/ST/PWD-*) intentionally mirror the production dbt
  fact table so analysts can join or compare without re-mapping.
- **JEE Advanced ranks merged onto JEE Mains rows.** The merge key is
  `(test_year, application_no)`. Students not in the advanced Excel get NaN
  for all `adv_*` rank columns. Currently advanced data exists for 2024 and
  2025 only (~323 and ~430 CRL-ranked students respectively).
- **`jee_advanced_qualified` priority:** rank-derived from the advanced Excel
  file takes precedence; the mains-file flag (only present in 2025) is used
  as a fallback for students not in the advanced file.
- **`jee_advanced_qualified_calculated` is always null.** Advanced Excels
  are rank lists only — no scores — so the cutoff-based calculation used for
  JEE Mains cannot be replicated.
- **`jee_mains_qualified_calculated` uses live BQ cutoffs.** The M2b
  academic level from `dim_nta_cutoffs` is fetched at runtime from BigQuery.
  A prior-year fallback is used if the current year is not yet in the table.
- **2025 uses the All JNV Candidates file, not JEE Mains 2025.xlsx.**
  `JEE 2025 - All JNV Candidates.xlsx` (12,103 rows) is the full JNV
  cohort and supersedes `JEE Mains 2025.xlsx` (4,037 rows, a subset).
  The All JNV file also carries richer JNV metadata and adv/prep flags.
- **2026 is split across two mains files.** `y2026_eligible.py` covers
  candidates who passed Class 12 in 2025 or later (`jee_adv_ineligible =
  False`). `y2026_ineligible.py` covers 2+ year droppers (`jee_adv_ineligible
  = True`). Both share `test_year = "2026"` and are deduped together.
- **`mains_category_rank` is derived in post-processing for all years except 2024.**
  2024 has a direct `Category Rank` column. For other years, `post_process`
  picks from `mains_obc_rank` / `mains_sc_rank` / `mains_st_rank` /
  `mains_ews_rank` based on the candidate's normalised category.
- **`marks_12_pct` and `marks_10_pct` are computed where missing.**
  `post_process` fills these from `obtained/total × 100` if the pct column
  is null but both mark columns are present.
- **WRITE_TRUNCATE on every load.** The BQ table is fully replaced each
  run. No incremental logic.

## Pitfalls

- **Don't commit raw Excel files.** The `.gitignore` covers `raw/` and
  `clean/`. Authoritative raw copies live in GCS under
  `gs://avantifellows-external-data/jnv/raw/`.
- **Run `clean_jee.py` before `upload_to_gcs.py --clean-only`.**
  The upload script reads `clean/jee_clean.csv`; it will exit with an error
  if that file doesn't exist.
- **2024 advanced file stores application numbers as floats.** The 2024
  advanced Excel carries `JEE Main Application Number` as a float (e.g.
  `2.40410001e+11`). `y2024.py`'s `post_transform` normalises these to
  integer strings via `str(int(float(v)))`. The mains `application_no` is
  normalised the same way before the merge.
- **2025 advanced file uses 0 for missing ranks.** `zero_is_null: True` in
  `y2025.py` causes `to_adv_rank()` to treat 0 as NaN.
- **Drop `adv_*` placeholder columns from mains before the merge.** The mains
  engine pre-creates all `CANONICAL_COLS` as NaN, including `adv_*` columns.
  `clean_jee.py` drops these before the merge so advanced values land in the
  correct column names (not `adv_all_india_rank_adv`).
- **Column names in raw files are case-sensitive and vary by year.**
  Always add new raw column name candidates to the codemap's `columns` list
  rather than assuming the exact capitalisation. The engine matches
  case-insensitively.
- **2026 ineligible file has a malformed header row.** The engine retries
  with `header=1` if the first read yields mostly Unnamed columns — driven
  by `header_fallback: 1` in `y2026_ineligible.py`. Don't remove it.
- **Session scores (`mains_*_score_s1`, `mains_*_score_s2`) are null for
  most years.** Only 2023 and the 2026 ineligible cohort have them.
- **`mains_total_score` for JEE Mains is a percentile (0–100), not raw
  marks.** `mains_max_score = 300` is retained for reference but should not
  be used as a denominator for the overall score.
- **`test_year` is a STRING, not INT.** Cast explicitly in SQL if needed:
  `CAST(test_year AS INT64)`.
