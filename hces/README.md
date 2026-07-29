# HCES 2023-24 — Household Consumption Expenditure Survey

Pipeline for one BigQuery table: **`external_data_sources.hces_fact_household_master`** — one row per
household surveyed in MoSPI's NSS Household Consumption Expenditure Survey (HCES) 2023-24 (261,953
households), with geography, demographics, dwelling/assets, monthly consumption, MPCE, the survey weight,
and a derived income estimate.

See `schemas/README.md` for "HCES in 60 seconds" (what the survey is and the two gotchas that change every
number). Full column docs: `schemas/hces_fact_household_master.yaml`.

## Why Avanti needs this

Avanti serves low-income students, so we need a defensible, national picture of the income distribution
those families sit in. This table gives us four things:

- **Size the population we serve** — how many, and where, India's low-income ("poor-but-not-destitute")
  households are.
- **EWS benchmarking** — where our students' families fall against the ₹8 LPA EWS income cutoff and the
  broader distribution.
- **Fundraising / positioning** — ground the donor and board narrative about the scale of the need in
  official numbers, not assertion.
- **A reusable income baseline** — other Avanti analyses can benchmark students' family income against the
  national distribution by joining to this table.

## What is committed

- **In git (this folder):** the pipeline scripts + schema + this README. No data.
- **In GCS (`gs://avantifellows-external-data/hces/`):** `raw/HCES_Data_2023-24_Csv/` (15 NSS level CSVs,
  3.4 GB) and `clean/hces_fact_household_master.parquet` (the BQ table source).
- **In BigQuery (post-review):** `external_data_sources.hces_fact_household_master`, one row per household,
  261,953 rows.

## Source & provenance

- **Publisher:** Ministry of Statistics and Programme Implementation (MoSPI), Government of India — NSS.
- **Dataset:** Household Consumption Expenditure Survey (HCES), round **2023-24**; the 15 unit-level
  ("level") CSVs.
- **Released:** by MoSPI, Dec 2024. **Staged to GCS:** Jul 2026.
- **Licence / PII:** public, anonymised microdata. No PII — composite sampling household ids only, no
  names or contacts.

## Data locations

```
gs://avantifellows-external-data/hces/
  raw/HCES_Data_2023-24_Csv/*.csv          # 15 NSS level CSVs, 3.4 GB (audit / regenerate)
  clean/hces_fact_household_master.parquet # the BQ table source, 261,953 rows
```

Raw and clean are gitignored; the pipeline scripts + this schema are the audit trail. Only levels L1
(identification + demographics), L3 (dwelling/assets) and L15 (consumption) feed the master; the other 12
level files are archived to `raw/` but not read.

## Pipeline

```bash
cd hces
pip install -r requirements.txt

# 1. Stage raw locally (or set HCES_RAW_DIR to wherever the CSVs live):
gsutil -m cp -r gs://avantifellows-external-data/hces/raw/HCES_Data_2023-24_Csv raw/

# 2. Build the consumption master (raw -> clean/hces_household_master.parquet):
python3 scripts/transform_hces.py

# 3. Derive income, write the BQ table parquet (clean/hces_fact_household_master.parquet):
python3 scripts/add_income.py

# 4. Upload to GCS (clean only; raw is already staged):
python3 scripts/upload_to_gcs.py --clean-only

# 5. Load BigQuery (post-review; WRITE_TRUNCATE, clustered on state_code, sector_code):
python3 scripts/load_bq.py --dry-run    # verify
python3 scripts/load_bq.py              # load
```

## Files

| Path | Role |
|---|---|
| `scripts/transform_hces.py` | Raw NSS level CSVs (L1/L3/L15) → household consumption master |
| `scripts/add_income.py` | Consumption → income via the CMIE savings schedule; writes the BQ parquet |
| `scripts/sources.py` | Central config (GCS bucket/prefix, BQ ids, table + raw defs) |
| `scripts/upload_to_gcs.py` | Stage raw + clean to GCS (`--raw-only` / `--clean-only`) |
| `scripts/load_bq.py` | Load the clean parquet into BigQuery |
| `schemas/hces_fact_household_master.yaml` | Column docs + domain teaching |
| `schemas/README.md` | HCES concepts primer |

## Related

The whitepaper built on this table lives in the `data-assistant` repo at `analysis/hces-poverty-estimate/`.
