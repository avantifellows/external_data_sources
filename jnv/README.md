# jnv — JNV Results Pipelines

JEE Mains/Advanced, NEET, JNVST selection test, and EI Asset Test results for
Jawahar Navodaya Vidyalaya (JNV) students.

Produces six BigQuery tables:
- `avantifellows.external_data_sources.jnv_fact_jee_results` (2021–2026)
- `avantifellows.external_data_sources.jnv_fact_neet_results` (2021–2025)
- `avantifellows.external_data_sources.jnv_fact_selection_test_results` (2018)
- `avantifellows.external_data_sources.jnv_fact_ei_asset_test_results`
- `avantifellows.external_data_sources.jnv_fact_board_results_10th` (2022–2025)
- `avantifellows.external_data_sources.jnv_fact_board_results_12th` (2022–2025)

See [`CLAUDE.md`](CLAUDE.md) for full pipeline orientation, design decisions, and pitfalls.

## Quick start — JEE

```bash
# 1. Set up local Python env (from inside jnv/)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/jee_mains/ and raw/jee_advanced/

# 3. Transform → clean CSV
.venv/bin/python scripts/clean_jee.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --jee-only

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --jee-only
```

## Quick start — NEET

```bash
# 1. Set up local Python env (same venv as JEE)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Drop raw Excel files into raw/neet/ (filenames must match sources.py → RAW_NEET_FILES)

# 3. Transform → clean CSV
.venv/bin/python scripts/clean_neet.py

# 4. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --neet-only

# 5. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --neet-only
```

## Quick start — JNVST Selection Test

```bash
# 1. Drop raw Excel into raw/jnvst/ (filename must match sources.py → RAW_JNVST_FILES)

# 2. Clean → CSV (lowercase columns, rename to descriptive names, map area/gender values)
.venv/bin/python scripts/clean_jnvst.py

# 3. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --jnvst-only

# 4. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --jnvst-only
```

## Quick start — EI Asset Test

```bash
# 1. Drop raw Excel into raw/ei_asset_test/ (filename must match sources.py → RAW_EI_ASSET_TEST_FILES)

# 2. Clean → CSV (lowercase columns, rename firstname/lastname/subjectno)
.venv/bin/python scripts/clean_ei_asset_test.py

# 3. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --ei-asset-test-only

# 4. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --ei-asset-test-only
```

## Quick start — Board Results (10th / 12th)

```bash
# 1. Drop raw Excel files into raw/board_results_10th/ and raw/board_results_12th/
#    (filenames must match sources.py → RAW_BOARD_RESULTS_10TH_FILES / RAW_BOARD_RESULTS_12TH_FILES)

# 2. Clean → CSV (wide → long unpivot, column renames)
.venv/bin/python scripts/clean_board_results_10th.py
.venv/bin/python scripts/clean_board_results_12th.py

# 3. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --board-results-10th-only
.venv/bin/python scripts/upload_to_gcs.py --board-results-12th-only

# 4. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --board-results-10th-only
.venv/bin/python scripts/load_bq.py --board-results-12th-only
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `jnv_fact_jee_results` | (test_year, application_no) | ~64k |
| `jnv_fact_neet_results` | (test_year, application_no) | ~114k |
| `jnv_fact_selection_test_results` | (district_rank, roll_no) | ~46k |
| `jnv_fact_ei_asset_test_results` | (id) | ~1.6k |
| `jnv_fact_board_results_10th` | (exam_year, roll_number, subject_code) | ~1.1M |
| `jnv_fact_board_results_12th` | (exam_year, roll_number, subject_code) | ~1.2M |

Plus the cross-exam identity map `jnv_student_outcome_mapping` (one row per
student × entrance attempt; see [`student_journey_mapping.md`](student_journey_mapping.md)).

## Student journey mapping + Avanti FK enrichment

`scripts/build_student_outcome_mapping.py` resolves a single student across all
five stages (**NCST → 10th → 12th → JEE → NEET**) and to Avanti's `dim_student`.
It models identity as a **graph / union-find** problem: every source record is a
node, trusted links (deterministic crosswalks + unambiguous name+DOB/name+father
identity rules) are edges, and each connected component is one student — then it
explodes to one row per (student, attempt_year). The Avanti fk is a **tiered
name+DOB(+father) match against `dim_student`** (direct-id → name+dob →
name+dob-swapped → name+father → strong-name → fuzzy-name → 10th-roll fill), with
a name gate on the direct-id crosswalks and ambiguous matches withheld
(precision-first). **It runs entirely in pandas**: the sources are read from BQ
already aggregated, resolution happens as DataFrame merges, and the finished
table is uploaded (no server-side CTE graph → no planner-complexity errors). One
in-memory pass builds **all cohorts** (2021–2028); there is no per-year flag.
`scripts/add_avanti_fk.py` then keys the resolved `fk_avanti_student_id`,
`match_confidence`, `match_count` **back onto the six source tables** (jee, neet,
board 10th/12th, dakshana + nvs NCST) on each table's grain. The output is one
row per (student, attempt_year), 47 columns.

> ⚠️ **`fk_avanti_student_id` = `COALESCE(pk_student_id, apaar_id)`.** It's a
> `pk_student_id` for most students, but an `apaar_id` for students who have no pk in
> `dim_student` (only an apaar — mostly JNV NVS). Join back with
> `COALESCE(pk_student_id, apaar_id) = fk_avanti_student_id`, not `pk_student_id` alone.

```bash
.venv/bin/python scripts/build_student_outcome_mapping.py   # rebuild the whole table (all cohorts)
.venv/bin/python scripts/add_avanti_fk.py                   # write fk back to the six source tables
```

⚠️ **Run order matters.** `load_bq.py` rebuilds the source tables with
`WRITE_TRUNCATE`, which **drops the fk columns**. After any reload, re-run in
order: **`load_bq.py` → `build_student_outcome_mapping.py` →
`add_avanti_fk.py`**. (No circularity — the mapping reads names/rolls/apps, never
the fk it later writes back.)

## Adding a new JEE year

1. Create `codemaps/mains/yYYYY.py` with a `CODEMAP` dict (copy nearest year as template).
2. Add one import line to `codemaps/mains/__init__.py` and append to `ALL_CODEMAPS`.
3. Add the raw Excel file entry to `scripts/sources.py` → `RAW_MAINS_FILES`.
4. Re-run steps 3–5 above.

## Adding a new NEET year

1. Create `codemaps/neet/yYYYY.py` with a `CODEMAP` dict (copy nearest year as template).
2. Add one import line to `codemaps/neet/__init__.py` and append to `ALL_NEET_CODEMAPS`.
3. Add the raw Excel file entry to `scripts/sources.py` → `RAW_NEET_FILES`.
4. Re-run steps 3–5 above.

## GCS layout

```
gs://avantifellows-external-data/
  jnv/raw/jee_mains/<stem>.parquet            ← one per raw JEE Mains Excel
  jnv/raw/jee_advanced/<stem>.parquet         ← one per raw JEE Advanced Excel
  jnv/raw/neet/<stem>.parquet                 ← one per raw NEET Excel
  jnv/raw/jnvst/<stem>.parquet                ← raw JNVST Excel
  jnv/raw/ei_asset_test/<stem>.parquet        ← raw EI Asset Test Excel
  jnv/raw/board_results_10th/<stem>.parquet   ← one per raw 10th board Excel
  jnv/raw/board_results_12th/<stem>.parquet   ← one per raw 12th board Excel
  jnv/clean/jnv_fact_jee_results.parquet
  jnv/clean/jnv_fact_neet_results.parquet
  jnv/clean/jnv_fact_selection_test_results.parquet
  jnv/clean/jnv_fact_ei_asset_test_results.parquet
  jnv/clean/jnv_fact_board_results_10th.parquet
  jnv/clean/jnv_fact_board_results_12th.parquet
```

## Source provenance

The authoritative raw sources live in **GCS** at `gs://avantifellows-external-data/jnv/raw/`
(`.csv` / `.parquet`, one per upstream Excel — see the GCS layout above). These have been
verified against the loaded BigQuery tables by Priyanka.

The same raw source files are also **mirrored in Google Drive** for convenience:
<https://drive.google.com/drive/folders/1cZYTEesgr1vcLF5GVffsAkPPSLs9whyW> (includes the 2025
NTA files and Dakshana's self-reported data). GCS is the source of truth for the pipeline; the
Drive copy is a human-browsable backup — keep them in sync when new source files arrive.

Recorded per avantifellows/external_data_sources#28.
