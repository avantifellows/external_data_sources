# jnv — JNV Results Pipelines

JEE Mains/Advanced, NEET, JNVST selection test, and EI Asset Test results for
Jawahar Navodaya Vidyalaya (JNV) students.

## Which tables are external, and which are ours

All tables are in `avantifellows.external_data_sources`.

| Table | Whose data | Where the data comes from | Years |
|---|---|---|---|
| `jnv_fact_jee_results` | External | NTA files. JEE Main for each year. JEE Advanced ranks for 2024 and 2025 only. | Test years 2021–2026 |
| `jnv_fact_neet_results` | External | NTA files. | Test years 2021–2025 |
| `jnv_fact_board_results_10th` | External | CBSE Grade 10 board results, one file for each year from CBSE/NVS. | Exam years 2022–2026 |
| `jnv_fact_board_results_12th` | External | CBSE Grade 12 board results, one file for each year from CBSE/NVS. | Exam years 2022–2026 |
| `jnv_fact_selection_test_results` | External | JNVST, the Class 6 selection test for admission to a JNV. One file for all districts. | 2018 only |
| `jnv_fact_ei_asset_test_results` | External | EI ASSET, a diagnostic test by Educational Initiatives (EI). One file. | 2025 only |
| `jnv_student_outcome_mapping` | Ours | Built by `scripts/build_student_outcome_mapping.py` from the JEE, NEET and board tables above, the two NCST tables (`dakshana_fact_ncst_results`, `nvs_fact_ncst_results`) and Avanti's `dim_student`. | Cohort years 2021–2028 |

An external table holds the data of the source file, cleaned. Some of its columns are ours:

- `fk_avanti_student_id`, `match_confidence` and `match_count` on the JEE, NEET and board tables. `scripts/add_avanti_fk.py` writes them from the mapping.
- The `*_qualified_calculated` columns on the JEE and NEET tables. The cleaning scripts calculate them from the cutoffs in `production_dbt_final.dim_nta_cutoffs`.
- `b1a_cleared` and `b1b_cleared` on the NEET table. Each is TRUE when the NEET score is at or above that bar (`B1a` or `B1b`) of the student's category in `dim_nta_cutoffs`. B1a is the higher bar. `neet_qualified` is the B2 flag. Production `fact_student_neet_results` has the same two flags, as `b1a_cleared` and `b1_cleared`.

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
#    (filenames must match sources.py → BOARD_RESULTS_10TH_RAW_BY_YEAR / BOARD_RESULTS_12TH_RAW_BY_YEAR)

# 2. Clean → CSV (wide → long unpivot, column renames)
.venv/bin/python scripts/clean_board_results_10th.py
.venv/bin/python scripts/clean_board_results_12th.py

# 3. Upload raw (as parquet) + clean (as parquet) to GCS
.venv/bin/python scripts/upload_to_gcs.py --board-results-10th-only
.venv/bin/python scripts/upload_to_gcs.py --board-results-12th-only

# 4. Load clean parquet from GCS → BigQuery
.venv/bin/python scripts/load_bq.py --board-results-10th-only
.venv/bin/python scripts/load_bq.py --board-results-12th-only

# Add ONE new year without touching the years already loaded (both board tables).
# Register the year in sources.py first, then (e.g. 12th, 2026):
.venv/bin/python scripts/clean_board_results_12th.py --year 2026
.venv/bin/python scripts/upload_to_gcs.py --board-results-12th-only --year 2026
.venv/bin/python scripts/load_bq.py --board-results-12th-only --year 2026   # DELETE year + WRITE_APPEND
```

## Output

| Table | Grain | ~Rows |
|---|---|---:|
| `jnv_fact_jee_results` | (test_year, application_no) | ~64k |
| `jnv_fact_neet_results` | (test_year, application_no) | ~114k |
| `jnv_fact_selection_test_results` | (district_rank, roll_no) | ~46k |
| `jnv_fact_ei_asset_test_results` | (id) | ~1.6k |
| `jnv_fact_board_results_10th` | (exam_year, roll_number, subject_code) | ~1.36M |
| `jnv_fact_board_results_12th` | (exam_year, roll_number, subject_code) | ~1.5M |

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
(precision-first). Ambiguity is checked in **both directions**: after matching,
an Avanti id claimed by more than one component either merges them (complementary
stages, one consistent journey — e.g. a 10th-board component and a JEE component
no roll bridge joined) or stays only with the best-tier claimant, the rest marked
`match_confidence = 'shared_fk_conflict'` (step 6b, `_reconcile_shared_fk`). When two or
more claimants share the best tier, a tie-breaker gives each one point for each fact that
agrees with the Avanti student in `dim_student` or `dim_student_historical`: school (a 10th or
12th school code), cohort, DOB and father. The claimant with the most points keeps the id. If
the top score is shared or zero, no claimant keeps the id. Step 6b keeps
an early attempt that a student already has, but does not make a new one. So an
fk sits on exactly one `student_key`, and the build asserts it. **It runs entirely in pandas**: the sources are read from BQ
already aggregated, resolution happens as DataFrame merges, and the finished
table is uploaded (no server-side CTE graph → no planner-complexity errors). One
in-memory pass builds **all cohorts** (2021–2028); there is no per-year flag.
`scripts/add_avanti_fk.py` then keys the resolved `fk_avanti_student_id`,
`match_confidence`, `match_count` **back onto the six source tables** (jee, neet,
board 10th/12th, dakshana + nvs NCST) on each table's grain. The output is one
row per (student, attempt_year).

Columns that describe the student and the school:

- `student_gender`: MALE or FEMALE. It comes from the first record that has a gender, in the
  same order as the name: 12th, 10th, JEE, NEET, NCST.
- `jee_category` and `neet_category`: the category on that exam's record for that attempt
  year. Each exam has its own column, because the category on the form sets the cutoff and
  the category rank for that exam.
- `neet_qualified`, `neet_b1b_cleared` and `neet_b1a_cleared`: the NEET levels, lowest bar
  first. `neet_qualified` is B2 (the qualifying cutoff). The other two are `b1b_cleared` and
  `b1a_cleared` on the NEET table.
- `board_10th_school_udise_code` and `board_12th_school_udise_code`: the UDISE code of the
  board school, from `dim_school` through the board school code. Use it to join to
  `dim_school` or to the UDISE tables for the state, district and region of the school. The
  mapping has no state or district column of its own.

Rules on every link (`_CheckedUnion`). Links are applied strongest first: crosswalk ids,
entrance same-person, DOB + parents, the identity rules, fuzzy names, then the father's
name as an extra word. A link that would break a rule is refused:

- A student has at most one NCST, one 10th and one 12th record.
- A student can have JEE and NEET records in more than one year, but one JEE and one
  NEET record per year at most.
- Every pair of records fits the journey years: NCST and 10th in the same year, 12th two
  years after the 10th, JEE and NEET in the 12th year or later.
- Early attempt: a JEE or NEET record can be one year before the 12th year (the student sat
  the exam in grade 11). An exact link can join it when the father or the mother of the
  early record agrees with a parent on the student's 10th, 12th or NCST record (two people
  can share a name and DOB). A fuzzy link can join two students only when it makes no new
  early exam. In the table, an early attempt is a row whose
  `jee_test_year` or `neet_test_year` is `cohort_year - 1`. Two or more years before the 12th
  year is refused.

Other rules:

- **One word written twice.** Some forms (the NCST form, and the Avanti enrolment forms)
  write the first name twice when the student has no surname. A name that is one word of 4
  or more letters written twice counts as that word once (`ASHA ASHA` → `ASHA`), in the
  records and in the Avanti names (`_one_word_once`). A shorter doubled word stays as it is,
  because it can be one name written with a space.
- **Twin check.** Twins have the same DOB and parents. When the records with one DOB and
  parents show a second person (two records of one stage and one year), the DOB + parents
  rule does not link two records whose given names differ
  (`name_distance.given_names_differ`). Without a second person, a spelling difference is a
  typo, and the records link. Twins with close given names (`ANKIT` and `ANKITA`) pass the
  check, so inside one DOB + parents group the closest names join first (the same name,
  then the higher character similarity), then the record ids. Each twin then keeps their own
  records, and every build gives the same result.
- **Gender check.** Two names are two people when the genders differ and the given names
  differ (`name_distance.given_names_differ`), unless the names are one typo apart (one word,
  same length, one other letter: `name_distance.one_letter_typo`). Then two records do not
  link, and step 6 does not give a student the Avanti id of the other person on the tiers
  that do not need equal names (direct id, strong and fuzzy names, the crosswalk ids). A
  gender difference alone refuses nothing: it can be a data-entry error.
- **Fuzzy names, last.** After the exact rules, the identity rules run again with an
  Indian-name distance (`name_distance.py`), only between students that are still apart.
  A fuzzy link is refused when the step 6 matcher, run on the students before the fuzzy
  round, gives the two students two different Avanti ids.
- **Father's name as an extra word, after the fuzzy names.** Some records add the father's
  first name to the student's name as one more word (`ASHA RAMESH PATIL`, or
  `PATIL ASHA RAMESH` when the surname comes first; father `RAMESH PATIL`), and other records
  of the same student do not (`ASHA PATIL`). Two records of students that are still apart
  link when one name is the other name with one more word (3 or more words, at any
  position), and that word is the first word of the father's name of one of the two records.
  For a name + DOB identity rule, the DOBs must be the same, and the fathers must not differ
  when both records have one (the NCST 2022 records have a DOB and no father). For a
  name + father identity rule, the fathers must match, and a 10th and a 12th record must have
  the same school code. The years must fit the identity rule, and each student can have only
  one such pair. The link goes through the same checks as a fuzzy link (no new early exam,
  no two different Avanti ids).
- **Step 6 record pass.** When the student's identity matches no Avanti student, each
  record's own name, DOB and father are tried (`record_name_dob`,
  `record_name_dob_swapped`, `record_name_father`). It only fills an empty fk, and only
  when one Avanti student matches.
- **Step 6 forward tie-breaker.** When a match tier gives the student 2+ Avanti ids (often one
  person with two `dim_student` ids, enrolled again under a new id), the id with the most
  points (school, cohort, DOB and father, as in step 6b) gets the link, and `match_count` is
  the number of ids. If the top score is shared or zero, the match stays `ambiguous`. A
  pick is a last resort: a unique match on any tier comes first, and in step 6b a pick
  ranks below every unique match.
- **Step 6 school pass.** After the record pass, a student with no candidate can match on a
  10th or 12th record (`name_part_dob_school`): the record DOB is the Avanti DOB, the board
  school code is an Avanti school code, the name words of the shorter name are all in the
  other name (a record often has the given name only), and the gender check does not say two
  people. A given name and a DOB alone are not enough: other students share them. It only
  fills an empty fk.
- **Step 6 strong record pass.** Last, after the school pass, for a student that still has
  no candidate (`record_name_dob_strong`). The student's identity takes the name of one
  record. When that name has fewer words than the `dim_student` name (`PATEL KIRANBHAI`,
  `dim_student` `PATEL KIRAN NARESHBHAI`), another record of the student can still match
  (`PATEL KIRANBHAI NARESHBHAI`). Each record's own name and DOB are tried: the DOB is the
  Avanti DOB, the names pass the strong name test (two shared words, or one name inside the
  other), the first name word of one name is in the other name (a close spelling or a prefix
  counts), the gender check does not say two people, and the school codes agree when the
  student has a 10th or 12th school code and the Avanti student has a board school code.
  Names that share only the middle and last words (`AMIT PRATAP SINGH`,
  `VIVEK PRATAP SINGH`) are two people. It only fills an empty fk.

Scratch run: `--out-table <project.dataset.table>` writes the build to another table, the
refused links to `<table>_refused`, the step 6b ties to `<table>_ties` and the father's-word
links to `<table>_middle_name` (these expire in 30 days; set an expiry on the build table by
hand). Compare it with the production table before a production run.

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

### JEE 2025: the recovery copy

The JEE 2025 rows come from `JEE 2025 - All JNV Candidates.xlsx`. That file has no student name,
no DOB and no 12th roll number. `JEE Mains 2025.xlsx` gives the name, the DOB and the parents'
names for a part of the rows only.

The other rows get the name, the DOB and the 12th roll number from a recovery copy:

- File: `gs://avantifellows-private-data/akshay-data-cleanup/sources/jnv_clean/jee_2025_clean.parquet`.
  Before you run `clean_jee.py`, copy it to `raw/jee_mains/jee_2025_clean.parquet`.
- What it is: a cleaned export of the 2025 results, with one row for each application number of
  the "All JNV Candidates" file. It was made from two NTA files (the "Appeared Candidates Data"
  and the "Registered Candidates Data"). Those two raw files are missing: they are not in GCS
  and not in this repo.
- How it is used: it is a recovery copy, not the source of record. `codemaps/mains/y2025.py`
  joins it on the application number and fills only the cells that are empty. A value from a
  raw file does not change.
- DOB: the file has two formats, `DD-MM-YYYY` and `M/D/YYYY` (month first). The codemap writes
  both as `DD-MM-YYYY`.
- Limit: it has no father's name and no mother's name. The rows that it fills link on the name
  and the DOB, without the check on the parents' names.

When the two NTA raw files are found, make them the source and remove the recovery copy.
