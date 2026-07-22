# CLAUDE.md — dakshana/

Guidance for Claude Code when working inside the `dakshana/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `dakshana/` unless otherwise noted.

## What this folder is

Two Dakshana datasets share this folder and pipeline scripts:

| Table | Source | Built by | Clean artifact |
|---|---|---|---|
| `dakshana_fact_ncst_results` | NCST selection test, per-year Excel (2022–2025) | `clean_ncst.py` | `clean/ncst_clean.csv` |
| `dakshana_fact_reported_results` | Dakshana self-reported JEE/NEET sheets (per cycle) | `build_reported_results.py` | `clean/dakshana_fact_reported_results.parquet` |

`sources.py` holds both: every output table is an entry in `TABLES`, every raw artifact an entry in
`RAW_FILES`. `upload_to_gcs.py` and `load_bq.py` loop over those lists, so they cover both tables; the
two only differ in shape (NCST clean is a CSV dtyped on upload + raw Excel→parquet; reported clean is
parquet + raw CSVs copied as-is) and `upload_to_gcs.py` dispatches on that. Most of this file documents
the **NCST** pipeline (the heavier one); the reported pipeline is a thin `build_reported_results.py` +
its schema YAML.

### NCST pipeline

A transform + ingestion pipeline for NCST (Navodaya CoE Selection Test)
results for **2022–2025**. In these years, NCST was conducted jointly by
Dakshana Foundation, Ex-Navodaya Foundation (ENF), and Avanti Foundation
as a smaller, Dakshana-curated process to select JNV students for two-year
IIT/NEET coaching programmes. Source data is one Excel file per year.

**2026 and later years live in [`nvs/`](../nvs/)**, not here. From 2026,
NCST was conducted at national scale by NVS directly (Dakshana set the
question paper but did not administer the exam). The 2026 data covers ~43k
students with a much richer schema and belongs to a separate source.

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

# 1. Build clean artifacts
.venv/bin/python scripts/clean_ncst.py                 # NCST: raw Excel → clean/ncst_clean.csv
.venv/bin/python scripts/build_reported_results.py     # reported: raw CSVs → clean/...reported_results.parquet

# 2. Stage to GCS. Default = all clean tables; --raw = original sources. --table picks one, --dry-run previews.
.venv/bin/python scripts/upload_to_gcs.py                                   # all clean tables → clean/
.venv/bin/python scripts/upload_to_gcs.py --raw                             # all originals → raw/
.venv/bin/python scripts/upload_to_gcs.py --table dakshana_fact_ncst_results
.venv/bin/python scripts/upload_to_gcs.py --dry-run

# 3. Load clean parquet from GCS → BigQuery. Loops over all tables; --table / --dry-run as above.
.venv/bin/python scripts/load_bq.py
.venv/bin/python scripts/load_bq.py --table dakshana_fact_reported_results --dry-run
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/NCST *.xlsx` | No | NCST source Excel files per year. Gitignored. |
| `raw/reported/*.csv` | No | Dakshana self-reported JEE/NEET sheets. Gitignored. |
| `clean/ncst_clean.csv` | No | Output of `clean_ncst.py`. Gitignored. |
| `clean/dakshana_fact_reported_results.parquet` | No | Output of `build_reported_results.py`. Gitignored. |
| `codemaps/ncst/__init__.py` | Yes | Registry — `ALL_NCST_CODEMAPS` list. Add new years here. |
| `codemaps/ncst/shared.py` | Yes | `CANONICAL_COLS`, `COLUMN_TYPES`, normalisation helpers, `apply_dtypes`. |
| `codemaps/ncst/y20XX.py` | Yes | Per-year column mapping configs. |
| `scripts/sources.py` | Yes | GCS/BQ config; `TABLES` (output tables) + `RAW_FILES` (raw artifacts) for both datasets. |
| `scripts/clean_ncst.py` | Yes | NCST transform engine: codemap loop → merged clean CSV. |
| `scripts/build_reported_results.py` | Yes | Reported-results transform: JEE+NEET sheets → one long parquet. |
| `scripts/upload_to_gcs.py` | Yes | Stages clean (default) or `--raw` originals to GCS; dispatches per table shape. |
| `scripts/load_bq.py` | Yes | Loads clean parquet from GCS → BQ (WRITE_TRUNCATE) for all tables. |
| `schemas/` | Yes | YAML column documentation, one file per BQ table. |

## BQ schema

Two tables in `avantifellows.external_data_sources`:

| Table | Grain | ~Rows |
|---|---|---:|
| `dakshana_fact_ncst_results` | (test_year, roll_no) | ~49k |
| `dakshana_fact_reported_results` | (test_year, exam, student) | ~371 (2025) |

`dakshana_fact_reported_results` is one long table of Dakshana's self-reported JEE-Main + NEET outcomes,
with an `exam` + `score_type` discriminator (**JEE score is a percentile, NEET is raw marks — never
mix**). It carries name + Dakshana CoE but **no `student_id`/`application_no`** — link to Avanti students
by name (+ DoB) via the identity crosswalk. See `schemas/dakshana_fact_reported_results.yaml` for columns.

The rest of this section documents `dakshana_fact_ncst_results`. Key column groups:

| Group | Columns |
|---|---|
| Core | `test_year`, `roll_no`, `student_full_name`, `father_name`, `mother_name`, `student_gender`, `category`, `stream` |
| Demographics | `physically_disabled`, `dob`, `staff_ward`, `is_father_late` |
| Location | `school_name`, `school_code`, `nvs_region`, `state` |
| Socioeconomic | `annual_family_income`, `father_annual_income`, `mother_annual_income` |
| Preference | `coaching_preference_1`, `coaching_preference_2`, `coaching_preference_3` |
| Scores | `physics_effective_score`, `chemistry_effective_score`, `math_bio_effective_score`, `reasoning_effective_score`, `total_effective_score` |
| 2025 only | `march_total_effective_score`, `dec_total_effective_score` |
| Avanti linkage | `fk_avanti_student_id`, `match_confidence`, `match_count` (written by `jnv/scripts/add_avanti_fk.py`; identity-derived) |

Column availability by year:

| Column group | 2022 | 2023 | 2024 | 2025 |
|---|:---:|:---:|:---:|:---:|
| All score columns | ✓ | ✓ | ✓ | ✓ |
| Coaching preferences | ✓ | ✓ | ✓ | ✓ |
| nvs_region | ✓ | ✓ | — | — |
| state | — | — | ✓ | — |
| dob | ✓ | — | — | — |
| father_name | — | ✓ | ✓ | — |
| mother_name | — | — | — | — |
| school_code | — | — | — | ✓ |
| father/mother income | ✓ | — | ✓ | — |
| is_father_late | ✓ | ✓ | ✓ | — |
| march/dec total | — | — | — | ✓ |

**Avanti linkage** — `fk_avanti_student_id` / `match_confidence` / `match_count` are keyed onto this
table by `jnv/scripts/add_avanti_fk.py` from `jnv_student_outcome_mapping`. NCST has no roll that bridges
to the board/JEE/NEET keys, so the fk is IDENTITY-derived: name+DOB, name+father, or (2024 only) a direct
`Avanti ID` read from the raw Excel. So `father_name` also does double duty as a match key — it is what
lets the DOB-less 2023/2024 rows link at all. fk counts: 2022 ≈1,400 · 2023 ≈255 · 2024 ≈2,989 · 2025 = 0
(no DOB/father) · (nvs 2026 ≈8,108). ⚠️ Re-run order after any NCST reload: `load_bq` →
`build_student_outcome_mapping.py` → `add_avanti_fk.py` (load_bq WRITE_TRUNCATE drops the fk columns).

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
3. Add the raw Excel file to `scripts/sources.py` → `RAW_FILES` as
   `RawFile("NCST YYYY.xlsx", "ncst/", sheet="<sheet name>")`.
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
- **Build the clean artifact before staging it.** The default
  `upload_to_gcs.py` reads each table's `clean/` file (`ncst_clean.csv` for
  NCST, the parquet for reported); run `clean_ncst.py` /
  `build_reported_results.py` first or it errors. Stage one table at a time
  with `--table <bq_name>`.