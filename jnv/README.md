# JNV — NTA exam results for the Navodaya cohort

`▶ NEXT: dakshana_fact_reported_results_2025 (authoritative Dakshana student list). Done & staged to
GCS (BQ load pending approval): jnv_fact_jee_advanced_rank_list, jnv_fact_jee_main_candidate_details.`

NTA publishes the JNV cohort's exam results (JEE Main, JEE Advanced rank lists, NEET) as per-year
Excel/CSV exports; Dakshana additionally shares self-reported result sheets for its CoEs. This source
harmonises those into clean BigQuery tables under `avantifellows.external_data_sources`.

## Why this source exists

Production already has `jnv_fact_jee_results` (combined Mains+Advanced) and `dakshana_fact_ncst_results`,
but three gaps remain that these raw NTA/Dakshana files fill:

1. **JEE-Advanced roll + category ranks** — production's advanced fact carries only an `application_no`;
   the NTA rank lists carry the Advanced registration (`adv_roll_no`), the Common Rank List rank, and the
   per-category ranks (EWS/OBC/SC/ST + PwD + preparatory). → `jnv_fact_jee_advanced_rank_list` (this PR).
2. **The 2025 application→JNV-school mapping** that the production export dropped (Issue #26). → a
   planned `jnv_fact_jee_main_2025` table.
3. **Authoritative Dakshana identification** — the `student_program='Dakshana CoE'` tag is patchy
   year-to-year; Dakshana's own reported sheets name every Dakshana student + their CoE. → a planned
   `dakshana_fact_reported_results_2025` table.

## Pipeline

```
raw/ (NTA + Dakshana exports, gitignored)  --build_*.py-->  clean/*.parquet (gitignored)
   --upload_to_gcs.py-->  gs://avantifellows-external-data/jnv/clean/
   --load_bq.py-->        avantifellows.external_data_sources.jnv_fact_*
```

- `scripts/build_jee_advanced_rank_list.py` — harmonise `JEE Advanced 2024.csv` + `JEE Advanced 2025.csv`
  (different schemas per year) into one table. Run: `python3 scripts/build_jee_advanced_rank_list.py --raw <dir>`.
- `scripts/build_jee_main_candidate_details.py` — the NTA JEE-Main candidate-details export → the
  application→JNV-school mapping + Class-12 board/marks (fixes the Issue-#26 school-mapping gap).
- `scripts/sources.py` — the table registry (GCS/BQ targets, clustering).
- `scripts/upload_to_gcs.py`, `scripts/load_bq.py` — stage to GCS, load to BQ. **Both support `--dry-run`;
  do not write to production GCS/BQ without an explicit go.**

## JNV NTA concepts in 60 seconds

- **JEE Main → JEE Advanced**: Main is the first exam; clearing a percentile bar makes you eligible for
  Advanced (the IIT exam). Advanced qualifiers get ranks.
- **Rank lists**: a qualifier gets a Common Rank List (CRL) rank, plus a rank in their reserved category
  (EWS / OBC-NCL / SC / ST) if applicable. 1 = top; 0/blank = not on that list.
- **PwD**: persons-with-disability candidates appear on `<category>_PwD` lists.
- **PREP**: a preparatory-course rank (a reserved-category provision), not a direct IIT seat — flagged
  separately and excluded from `qualified`.
- **IDs differ by year**: 2025 has the Avanti `student_id` (joins straight to `dim_student`); 2024 has
  only application number + name/DoB (link via the identity crosswalk).

Tables are added **one at a time**, each its own PR paired with a bq-assistant schema PR.
