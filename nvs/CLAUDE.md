# CLAUDE.md — nvs/

Guidance for Claude Code when working inside the `nvs/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `nvs/` unless otherwise noted.

## What this folder is

A transform + ingestion pipeline for NCST (Navodaya CoE Selection Test)
results, starting from 2026 — the first year NCST was conducted at
**national scale by NVS** (Navodaya Vidyalaya Samiti) directly.

Prior to 2026, NCST was run by Dakshana Foundation as a smaller,
Dakshana-curated process. Those years (2022–2025) live in
[`dakshana/`](../dakshana/) and produce `dakshana_fact_ncst_results`.

**What changed in 2026:** Dakshana Foundation set the question paper, but
NVS administered the exam to all eligible JNV students across the country.
This means the 2026 file covers ~43k students (vs ~10–15k in prior years)
and includes many more data points — household wealth, academic history,
per-subject raw scores — that Dakshana never collected in earlier iterations.
Note that Dakshana-track students are *under-represented* in this dataset:
only ~86 of the ~318 Dakshana-selected students appear here; the rest sat a
separate Dakshana-administered process.

This pipeline follows the same **heavy transform** / codemap pattern as
`dakshana/`.

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
  nvs/raw/ncst/<stem>.parquet       (one per raw Excel)
  nvs/clean/nvs_fact_ncst_results.parquet
       │
       │  scripts/load_bq.py
       ▼
avantifellows.external_data_sources.nvs_fact_ncst_results  (asia-south1)
```

## Commands

```bash
# One-time: set up local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Transform raw Excel → clean CSV
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

| Table | Grain | ~Rows | Columns |
|---|---|---:|---:|
| `nvs_fact_ncst_results` | (test_year, roll_no) | ~43k (2026) | 86 |

The first 24 columns share the same names as `dakshana_fact_ncst_results`
(up to and including `coaching_preference_3`), enabling SQL UNIONs for
multi-year analysis. Column names diverge after that: dakshana uses
`*_effective_score` (penalty-adjusted raw); nvs uses `*_normalized_score`
(per-QP-set equated). Additionally, nvs has per-subject raw question counts,
academic history, extended family info, home address, and household wealth
data that did not exist in pre-2026 cohorts.

See `schemas/nvs_fact_ncst_results.yaml` for full column documentation.

## Codemap architecture

Same engine as `dakshana/` — zero year-specific logic in `clean_ncst.py`.

**To add a new year:**
1. Create `codemaps/ncst/yYYYY.py` with a `CODEMAP` dict.
2. Add one import line to `codemaps/ncst/__init__.py` and append to `ALL_NCST_CODEMAPS`.
3. Add the raw Excel file to `scripts/sources.py` → `RAW_NCST_FILES`.
4. Re-run the pipeline.

## Design calls worth knowing

- **First 24 column names mirror dakshana** (through `coaching_preference_3`).
  Resist renaming them even if 2026 uses different source column names — the
  whole point is cross-table queryability.
- **Normalized scores, not effective scores.** Dakshana calls its scores
  `*_effective_score` (penalty-adjusted raw). NVS 2026 has `*_normalized_score`
  (per-QP-set equated). These are different concepts; the names reflect the
  actual data rather than forcing dakshana terminology.
- **Normalization is per-QP-set, pre-computed in Excel.** Two sets (A/B). Set B
  is the reference (factors = 1.00). Set A students get subject-specific
  scaling. The pipeline reads the pre-computed values directly — no recalculation.
  See y2026.py docstring for verified factors per subject.
- **Bio and Maths are separate columns** (not collapsed into a single
  `math_bio` column). NEET rows have `bio_normalized_score` non-null; JEE rows
  have `maths_normalized_score` non-null. Both columns exist in the schema.
- **father/mother income are numeric in 2026.** Unlike 2022 (string labels
  like "Less than 1 lakh"), 2026 stores actual INR values. Reflected in
  COLUMN_TYPES as "float" (vs "str" in dakshana's shared.py).
- **is_father_late is inverted.** The source column is "Is Father alive"
  (Yes = alive = is_father_late False). post_transform flips Yes/No before
  the engine's normalize_bool runs.
- **household_earning_members column has an encoding artifact** (a spurious
  `Â` character in the column name from the source Excel). Mapped via
  partial-name search in post_transform rather than the columns dict.
- **Self-reported academic marks are unverified.** The source data dictionary
  explicitly notes 10th Math marks are NOT verified CBSE board marks.
- **WRITE_TRUNCATE on every load.** The BQ table is fully replaced each run.

## Pitfalls

- **Don't commit raw Excel files.** The `.gitignore` covers `raw/` and
  `clean/`. Authoritative raw copies live in GCS under
  `gs://avantifellows-external-data/nvs/raw/`.
- **Run `clean_ncst.py` before `upload_to_gcs.py --clean-only`.**
- **Don't confuse `state` with `home_state`.** `state` is the school's state
  (dakshana-compatible). `home_state` is the student's home state. They often
  differ for boarding-school students.
- **`total_normalized_score` is not comparable to `total_effective_score`.**
  2026 uses per-QP-set equated composite scores with a Bio/Maths 25% weighting.
  Pre-2026 dakshana years used a different scale (raw after penalty). Align
  scoring methodology before any cross-year comparison.
