# CLAUDE.md — dakshana/

Guidance for Claude Code when working inside the `dakshana/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `dakshana/` unless otherwise noted.

## What this folder is

A transform + ingestion pipeline for NCST (Navodaya CoE Selection Test)
results. NCST is conducted jointly by Dakshana Foundation, Ex-Navodaya
Foundation (ENF), and Avanti Foundation to select JNV students for
two-year IIT/NEET coaching programmes. Source data is one Excel file per
year (2022–2025).

Each file carries student scores (effective after penalty), coaching
preferences, and demographic details. Contact columns (mobile, email) are
intentionally excluded.

This pipeline follows the **heavy transform** pattern from
[`jnv/`](../jnv/CLAUDE.md): a codemap-driven engine with no year-specific
logic in the clean script.

```
raw/NCST <year>.xlsx           (local Excel files, gitignored)
       │
       │  scripts/clean_ncst.py   (codemap-driven transform)
       ▼
clean/ncst_clean.csv
       │
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/
  dakshana/raw/ncst/<stem>.parquet       (one per raw Excel)
  dakshana/clean/dakshana_fact_ncst_results.parquet
       │
       │  scripts/load_bq.py
       ▼
avantifellows.external_data_sources.dakshana_fact_ncst_results  (asia-south1)
```

## Commands

```bash
# One-time: set up local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Transform raw Excel files → clean CSV
.venv/bin/python scripts/clean_ncst.py

# 2. Upload raw Excel (as parquet) + clean CSV (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py
.venv/bin/python scripts/upload_to_gcs.py --raw-only
.venv/bin/python scripts/upload_to_gcs.py --clean-only

# 3. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/NCST *.xlsx` | No | Source Excel files per year. Gitignored. |
| `clean/ncst_clean.csv` | No | Output of `clean_ncst.py`. Gitignored. |
| `codemaps/ncst/__init__.py` | Yes | Registry — `ALL_NCST_CODEMAPS` list. Add new years here. |
| `codemaps/ncst/shared.py` | Yes | `CANONICAL_COLS`, `COLUMN_TYPES`, normalisation helpers, `apply_dtypes`. |
| `codemaps/ncst/y20XX.py` | Yes | Per-year column mapping configs. |
| `scripts/sources.py` | Yes | GCS bucket, BQ destination, raw file list, clean table definition. |
| `scripts/clean_ncst.py` | Yes | Transform engine: codemap loop → merged clean CSV. |
| `scripts/upload_to_gcs.py` | Yes | Converts Excel + CSV → parquet, uploads to GCS. |
| `scripts/load_bq.py` | Yes | Loads clean parquet from GCS → BQ (WRITE_TRUNCATE). |
| `schemas/` | Yes | YAML column documentation for the BQ table. |

## BQ schema

One table in `avantifellows.external_data_sources`:

| Table | Grain | ~Rows |
|---|---|---:|
| `dakshana_fact_ncst_results` | (test_year, roll_no) | ~49k |

Key column groups:

| Group | Columns |
|---|---|
| Core | `test_year`, `roll_no`, `student_full_name`, `student_gender`, `category`, `stream` |
| Demographics | `physically_disabled`, `dob`, `staff_ward`, `is_father_late` |
| Location | `school_name`, `school_code`, `nvs_region`, `state` |
| Socioeconomic | `annual_family_income`, `father_annual_income`, `mother_annual_income` |
| Preference | `coaching_preference_1`, `coaching_preference_2`, `coaching_preference_3` |
| Scores | `physics_effective_score`, `chemistry_effective_score`, `math_bio_effective_score`, `reasoning_effective_score`, `total_effective_score` |
| 2025 only | `march_total_effective_score`, `dec_total_effective_score` |

Column availability by year:

| Column group | 2022 | 2023 | 2024 | 2025 |
|---|:---:|:---:|:---:|:---:|
| All score columns | ✓ | ✓ | ✓ | ✓ |
| Coaching preferences | ✓ | ✓ | ✓ | ✓ |
| nvs_region | ✓ | ✓ | — | — |
| state | — | — | ✓ | — |
| dob | ✓ | — | — | — |
| school_code | — | — | — | ✓ |
| father/mother income | ✓ | — | ✓ | — |
| is_father_late | ✓ | ✓ | ✓ | — |
| march/dec total | — | — | — | ✓ |

## Codemap architecture

The engine (`clean_ncst.py`) contains no year-specific logic. All
year-specific knowledge lives in `codemaps/ncst/`.

**To add a new year:**
1. Create `codemaps/ncst/yYYYY.py` with a `CODEMAP` dict:
   ```python
   CODEMAP = {
       "source":    {"file": "NCST YYYY.xlsx", "sheet": "...", "header": 0},
       "constants": {"test_year": "YYYY"},
       "columns":   {"roll_no": ["..."], "student_full_name": ["..."], ...},
       # optional:
       "post_transform": my_fn,   # fn(raw_df, out_df) → out_df
   }
   ```
2. Add one import line to `codemaps/ncst/__init__.py` and append to `ALL_NCST_CODEMAPS`.
3. Add the raw Excel file to `scripts/sources.py` → `RAW_NCST_FILES`.
4. Re-run the pipeline.

**Codemap keys:**
- `source` — `file`, `sheet`, and `header` (0 for most years; 2 for 2025 which
  has a merged-cell title row and a sub-header row before the column names).
- `constants` — values written as-is to every row.
- `columns` — maps canonical column name → list of candidate raw column names
  (first found wins, case-insensitive).
- `post_transform` — optional `fn(raw_df, out_df) → out_df` for anything that
  can't be expressed as a simple column mapping (e.g. positional score
  extraction in 2025, DOB coercion in 2022).

## Design calls worth knowing

- **Engine has zero year-specific logic.** `clean_ncst.py` loops over
  `ALL_NCST_CODEMAPS`. If you find yourself adding `if year == 2024` there,
  put it in a `post_transform` in the codemap instead.
- **2025 has a multi-row header.** The sheet has a merged title row, a
  sub-header row, and the column-name row at index 2. `header=2` in the
  codemap source handles this. Score columns (+ve/-ve/Eff × 5 subjects × 2
  sittings = 30 columns) have duplicate names after pandas reads them; the
  `post_transform` uses positional `iloc` instead.
- **2025 canonical scores come from the better sitting.** The engine picks
  physics/chemistry/math_bio/reasoning/total from whichever of March 2025
  or December 2024 had the higher total_effective_score. Both raw totals are
  preserved as `march_total_effective_score` and `dec_total_effective_score`.
- **`total_effective_score` scales differ across years.** 2025 uses max 500
  (Engineering) or 625 (Medical). Earlier years used a different scale.
  Do not compare raw totals across years without normalising.
- **Coaching preferences are normalised.** Short forms ('Dakshana', 'ENF',
  'Avanti') in 2022 are expanded to full names used in 2024–2025
  ('Dakshana Foundation', 'Ex-Navodaya Foundation', 'Avanti Foundation').
- **WRITE_TRUNCATE on every load.** The BQ table is fully replaced each run.
- **`test_year` is a STRING, not INT.** Cast explicitly in SQL if needed:
  `CAST(test_year AS INT64)`.

## Pitfalls

- **Don't commit raw Excel files.** The `.gitignore` covers `raw/` and
  `clean/`. Authoritative raw copies live in GCS under
  `gs://avantifellows-external-data/dakshana/raw/`.
- **2022 has two columns named "Region".** Pandas renames the duplicate to
  `Region.1`. The codemap maps `nvs_region` to the first `Region` only
  (a JNV administrative region like "Jaipur"). The second column is a
  numeric district code — intentionally ignored.
- **2022 father/mother income are string labels, not numbers.** Values like
  "Less than 1 lakh" and "Zero" are income-bracket labels. They map to
  `father_annual_income` / `mother_annual_income` as strings, not floats.
- **2023 reasoning scores can be negative.** A few rows have a negative
  effective score for reasoning (penalty only, zero positive marks).
  These are kept as-is.
- **Run `clean_ncst.py` before `upload_to_gcs.py --clean-only`.** The
  upload script reads `clean/ncst_clean.csv`; it will error if that file
  doesn't exist.