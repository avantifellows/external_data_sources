# nvs — NCST Results Pipeline (2026+)

Ingestion pipeline for the Navodaya CoE Selection Test (NCST) results from
2026 onward.

**Why a separate source from `dakshana/`?**  
Prior to 2026, NCST was run by Dakshana Foundation as a smaller,
Dakshana-curated process — those years (2022–2025) live in
[`dakshana/`](../dakshana/). From 2026, NVS administered the test
directly to all eligible JNV students across the country (Dakshana set the
question paper). The 2026 cohort is ~43k students vs ~10–15k in prior years,
and the data is significantly richer — per-subject raw scores, household
socioeconomic data, academic history, and more.

Produces one BigQuery table:
- `avantifellows.external_data_sources.nvs_fact_ncst_results` (2026+)

The first 24 columns match `dakshana_fact_ncst_results` exactly, enabling
SQL UNIONs across both tables for multi-year analysis. Note that dakshana
uses `total_effective_score` (penalty-adjusted raw) while nvs uses
`total_normalized_score` (per-QP-set equated composite):
```sql
SELECT test_year, roll_no, stream, total_effective_score AS score
FROM avantifellows.external_data_sources.dakshana_fact_ncst_results
UNION ALL
SELECT test_year, roll_no, stream, total_normalized_score AS score
FROM avantifellows.external_data_sources.nvs_fact_ncst_results
```

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions,
and column-by-column notes.

## Quick start

```bash
# 1. Set up local Python env (from inside nvs/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel file into raw/  (must be named "NCST 2026.xlsx")

# 3. Transform raw Excel → clean CSV
.venv/bin/python scripts/clean_ncst.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py
```

## Output

| Table | Grain | ~Rows | Columns |
|---|---|---:|---:|
| `nvs_fact_ncst_results` | (test_year, roll_no) | ~43k | 86 |
| `nvs_fact_ncst_screening` | (test_year, roll_no) | 46,191 | 59 |

## NCST Screening (`nvs_fact_ncst_screening`, from the 2027 cycle)

From the 2027 cycle NCST has two stages: a **Screening** test (4 Oct 2026, every
registered Class X student) and the main NCST (13 Dec 2026) for the students the three
agencies shortlist. `nvs_fact_ncst_screening` holds the screening stage: 46,191
registered (43,244 present), marks by subject (of 300; +5/−2, four paper sets not
equated), stream ranks, coaching preferences, and the shortlist — `is_shortlisted`
(11,993) and one flag per agency (Avanti 9,081, ENF 5,000, Dakshana 4,405; they
overlap). Internal only: student-level, with names. Phone numbers are dropped at intake,
from the clean table and from the raw archive.

Source: the combined shortlisting file the agencies sent NVS on 16 Nov 2026
(`raw/NCST 2027 Phase 1 Shortlisting_Combined - NVS.xlsx`, sheet "NCST List").

```bash
python scripts/clean_screening.py          # raw/ → clean/nvs_fact_ncst_screening.parquet, with gates
python scripts/upload_to_gcs.py --screening   # raw sheet (no phones) + clean → GCS
python scripts/load_bq.py --screening         # GCS → BQ (WRITE_TRUNCATE, this table only)
```

The gates in `clean_screening.py` fail the build unless rows, attendance, marks,
totals and the per-agency counts reconcile with the file. See
`schemas/nvs_fact_ncst_screening.yaml` for gotchas (do not use NVS's `1st_choice`
for Medical; do not add the agency flags).

### Column groups (nvs_fact_ncst_results)

| Group | Columns | Notes |
|---|---|---|
| Identity | `test_year`, `roll_no`, `student_full_name` | |
| Demographics | `student_gender`, `category`, `physically_disabled`, `stream`, `dob` | |
| School / geography | `school_name`, `school_code`, `school_district`, `state` | |
| Exam metadata | `attendance`, `qp_set`, `exam_date` | |
| Socioeconomic | `annual_family_income`, `father_annual_income`, `mother_annual_income`, `staff_ward`, `is_father_late` | Income is numeric INR (vs bracket labels in 2022) |
| Coaching preference | `coaching_preference_1/2/3` | |
| Aggregate scores | `total_positive_ques`, `total_negative_ques`, `total_unattempted_ques`, `total_raw_score`, `total_normalized_score` | |
| Per-subject scores | `physics/chemistry/bio/maths/reasoning` × `_positive_ques`, `_negative_ques`, `_unattempted_ques`, `_raw_score`, `_normalized_score` | Pre-computed per-QP-set equated; see schema normalization_logic |
| Academic history | `grade_9/10_math/science_marks`, `grade_9/10_aggregate_pct`, `willing_for_coaching` | Self-reported; unverified |
| Extended family | `is_mother_alive`, `father/mother_education`, `father/mother_occupation`, `guardian` | |
| Home address | `home_village`, `home_post_office`, `home_district`, `home_state`, `domicile_state`, `pin_code` | Separate from school location |
| Household wealth | `household_assets_value`, `household_earning_members`, `household_annual_income`, `father_mother_combined_income`, `max_household_income`, `household_cash_savings`, `house_ownership`, `house_area_sqft`, `house_bedrooms`, `locality_type`, `is_bpl`, `has_ration_card`, `ration_card_color` | |
| Misc | `submission_type` | |
