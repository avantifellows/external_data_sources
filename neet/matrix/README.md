# neet/matrix_2026

The **NEET-2026 minimum-marks matrix**: for each state/UT and category, the minimum NEET
marks that realistically win a **government** MBBS (B1a) / BDS (B1b) seat, plus B2b (the
national qualifying floor).

Output: one CSV, 370 rows = 37 tracks × 10 category rows. All 36 states/UTs + "All India"
(the 15% AIQ track). **32 tracks carry numbers; 5 are deliberately blank** with the reason
recorded in a `data_status` column.

## Why this is separate from `neet/scrape/`

`scrape/` parses each state's counselling data into per-college closing ranks — the input a
*college predictor* needs. This directory answers a different question: **"what is the bar?"**
— one floor per (state, category), which is what a counsellor or a programme team needs when
estimating how many students will convert.

## Layout

```
builders/     28 per-state matrix builders + the AIQ builder + 2 model-fitting scripts
parsers/       7 parsers we wrote for official PDFs the pipeline did not already cover
docs/          methodology + provenance (see below)
*.py           two utilities (predictor loader, source collector)
```

## Method, in one paragraph

Take each state's 2025 government-college closing ranks. Drop private colleges, NRI,
management and PwD sub-pools. Per category take the **median of the five loosest colleges**,
so one freak seat cannot set the bar. Convert rank → marks with a curve fitted on 32,093 real
(marks, AIR) pairs, validated against four states' *published* marks (TN ±1, MP ±1, Haryana
mean +0.86 sd 2.39, Tripura ratios 0.96–1.03). Then project to 2026 with a measured
easier-paper shift, `+0.085 × (720 − marks)` — a curve, not a flat add, because the inflation
is ~0 at the top and grows as marks fall. A 530 in 2025 becomes ~546 in 2026.

Full write-up: **`docs/NEET_2026_HOW_WE_BUILT_IT.md`** (readable, ~3k words).
Per-state provenance: `docs/NEET_2026_MATRIX_DECISIONS.md`.
Per-state coverage at a glance: `docs/NEET_STATE_COVERAGE.md`.
Source-of-truth ledger + cross-cutting lessons: `docs/NEET_SOURCE_OF_TRUTH.md`.

## Raw inputs are NOT in git

Per this repo's convention (`neet/.gitignore`), the source PDFs, page images and extracted
CSVs are staged to GCS, not committed. The builders read them from:

- `amogh-csv/medical-state-counselling/extracted_data/` — the state-counselling pipeline output
- `amogh-csv/medical-national-ranks/extracted_data/` — AIQ + the NMC/DCI college rosters
- `neet_pdfs/` — official state cutoff PDFs
- `amogh-csv/*.pdf` and `amogh-csv/mizoram-zmch-2025-admitted/` (10 page images) — the
  official documents we sourced ourselves for RJ/HR/OD/TR/MZ/MN/AR/ML/NL/Ladakh/Chandigarh

Every source is catalogued with provenance in `docs/NEET_SOURCE_OF_TRUTH.md`.

## Not yet done

The matrix is currently a CSV. It has **not** been staged to GCS or loaded to BigQuery — the
next step is a `clean/` parquet + a `neet_dim_marks_matrix_2026` fact table, following the
same `upload_to_gcs.py` / `load_bq.py` pattern the other sources in this repo use.
