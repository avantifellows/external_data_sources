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

### Column groups

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
