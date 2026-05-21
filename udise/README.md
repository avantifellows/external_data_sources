# udise

UDISE+ school enrolment → BigQuery.

School enrolment by state × school-management × school-category × location ×
class × gender, AY 2024-25. The source is a wide dashboard cross-tab; this
reshapes it to one long-form fact, then stages parquet → GCS → BQ.

**Source:** UDISE+ Dashboard *Report 4000 — Enrolment by Location, School
Category and School Management for Each Class & Level of Education*, AY 2024-25,
exported from [dashboard.udiseplus.gov.in](https://dashboard.udiseplus.gov.in/).
The dashboard generates the report on demand and has **no static download URL**,
so — like PLFS — there is **no `fetch.py`**; the raw xlsx staged on GCS is the
regenerable source of record.

## Pipeline at a glance

```
UDISE+ dashboard (Report 4000)              (manual export — no static URL)
       ▼
raw/udise_2024-25_enrolment.xlsx            (local; gitignored)
       │ scripts/clean_udise.py             (wide cross-tab → long fact)
       ▼
clean/enrolment.parquet                     (local; gitignored)
       │ scripts/upload_to_gcs.py           (raw xlsx + clean parquet → GCS)
       ▼
gs://avantifellows-external-data/udise/raw/<xlsx>          (traceability)
gs://avantifellows-external-data/udise/clean/enrolment.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.udise_fact_enrolment   (asia-south1)
```

## Table produced

**`udise_fact_enrolment`** — 42,270 rows. Grain:
`(academic_year, state, school_management, school_category, urban_rural, class_level, gender)` → `enrolment`.

Schema: [`schemas/udise_fact_enrolment.yaml`](schemas/udise_fact_enrolment.yaml).

**Validation:** `SUM(enrolment)` = **246,932,680**, matching the all-India total
the dashboard reports.

## Reshape notes (read before analysing)

- **Only leaf detail rows are kept.** The export is hierarchical — it mixes
  detail rows with subtotal rows (`urban_rural="Total"` = Rural+Urban, blank-
  urban_rural state subtotals, a blank-Location all-India grand total). The
  cleaner keeps only `urban_rural ∈ {Rural, Urban}` rows with state + management
  + category present, so the fact never double-counts. Totals are derivable by
  summing.
- **Gender is Girls/Boys only** — the source reports no per-class total or third
  gender; the wide "Overall" column (a row total) is dropped as derivable.
- **`class_level`** spans `Balvatika-1/2/3` (pre-primary) and `Class-1` … `Class-12`.

## Running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
gcloud auth application-default login            # for upload + load

# 1. drop the dashboard export into raw/ as udise_2024-25_enrolment.xlsx
# 2. reshape → clean/enrolment.parquet
.venv/bin/python scripts/clean_udise.py
# 3. stage raw + clean to GCS
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py
# 4. load to BigQuery (post-approval)
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## Refreshing for a new academic year

1. Export the same Report 4000 for the new AY from the UDISE+ dashboard, save as
   `raw/udise_<AY>_enrolment.xlsx`, and point `SOURCE_XLSX` / `ACADEMIC_YEAR` in
   `scripts/sources.py` at it.
2. `clean_udise.py` → `upload_to_gcs.py` → `load_bq.py`. The fact keys on
   `academic_year`, so new years append cleanly.
