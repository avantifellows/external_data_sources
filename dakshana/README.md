# Dakshana — partner-reported results

`⏸ PAUSED — first table done & staged to GCS (BQ load pending approval):
dakshana_fact_reported_results. (dim_dakshana_ncst etc. were loaded by an older process.)`

Dakshana runs intensive JEE/NEET coaching at a set of Navodaya (JNV) Centres of Excellence and shares a
self-reported result sheet each cycle. This source harmonises those sheets into BigQuery under
`avantifellows.external_data_sources`.

## Why this source exists

Dakshana students are routinely **mis-attributed** in the warehouse: the `student_program='Dakshana CoE'`
tag is patchy and inconsistent year-to-year, so a Dakshana student (e.g. at JNV Bengaluru Urban) often
shows up as Nodal/NVS. Dakshana's own sheet names every Dakshana student + their CoE, so it is the
**authoritative Dakshana attribution** — and it pins **which JNVs were Dakshana in a given year** (the
footprint moves: Bundi/Kottayam/Lucknow were Dakshana in 2025, handed to Avanti from 2026).

## Pipeline

```
raw/ (Dakshana sheets, gitignored)  --build_*.py-->  clean/*.parquet (gitignored)
   --upload_to_gcs.py [--raw]-->  gs://avantifellows-external-data/dakshana/{raw,clean}/
   --load_bq.py-->                avantifellows.external_data_sources.dakshana_fact_*
```

- `scripts/build_reported_results.py` — harmonise the JEE-Main + NEET sheets into one long table with an
  `exam` + `score_type` discriminator (JEE score is a percentile, NEET is raw marks — never mix).
- `scripts/sources.py`, `upload_to_gcs.py` (`--raw` stages originals), `load_bq.py` (both `--dry-run`).

## Linking to Avanti students

The sheets carry **name + CoE only** — no `student_id` / `application_no`. Attach to an Avanti student by
name (+ DoB) via the identity crosswalk, not by id.

Tables are added one at a time, each its own PR paired with a bq-assistant schema PR. **No production
GCS/BQ writes without an explicit go** — clean parquet is gitignored; load is post-approval.
