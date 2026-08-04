# UDISE+ DSP microdata — ingest plan

Written to be picked up cold. Nothing is built yet: the raw files are downloaded,
registered in `sources.py` and gitignored, and this is the plan.

## What this is, and what it is not

The existing `udise/` pipeline reads **Report 4000**, a dashboard cross-tab —
one aggregated table, 42,270 rows, state × management × category × class × gender.

This is a different product: the **Data Sharing Portal (DSP)** release, which is
**one row per school**. Same publisher, unrelated shape and scale. It should end up
as its own tables, not folded into `udise_fact_enrolment`.

Held: **2020-21 and 2024-25**, six file groups each, in `raw/dsp/<year>/`.
~754 MB of zips; the enrolment CSV alone is **562 MB uncompressed**.

| Group | CSV | What it holds |
|---|---|---|
| `profile_data_1` | `100_prof1.csv` | state, district, block, rural/urban, category, management, medium, boards, pincode |
| `profile_data_2` | `100_prof2.csv` | continues the profile block |
| `enrolment_data_1` | `100_enr1.csv` | enrolment by class × gender (`cpp_b`…`c12_g`) × `item_group`/`item_id` |
| `enrolment_data_2` | `100_enr2.csv` | continues the enrolment block |
| `teacher_data` | `100_tch.csv` | teacher counts by sex, social group, qualification, class taught |
| `facility_data` | `100_fac.csv` | building, classrooms, toilets, utilities |

Codebooks are committed: `docs/DSP_Schema_2020-21.pdf`, `docs/DSP_Schema_2024-25.pdf`
(they differ — check the right one per year).

## Why Avanti should care

**This is the income-and-poverty dimension AISHE cannot give us.** AISHE has no
household-income variable in any edition and no EWS before 2019-20. UDISE DSP
carries, per school:

- `item_group=3, item_id=13` → **BPL** (Below Poverty Line) enrolment
- `item_group=10, item_id=32` → **EWS** enrolment
- `item_group=1` → social category (General / SC / ST / OBC)
- `item_group=2` → religion (Muslim / Christian / Sikh / Buddhist / Parsi / Jain)
- `item_group=4` → 20 disability types
- `item_group=5, item_id=0` → repeaters

Two years ten years apart also gives a genuine before/after on school-level
composition, and `facility_data` supports a school-quality read.

## PII and safety posture

- Grain is the **school**, not the student. No student records anywhere.
- The school key is `pseudocode`, a **pseudonymised** id. There is no school name
  and no real UDISE code, so these **cannot be linked to Avanti's own school
  lists** — decide whether that kills a use case before investing in the ingest.
- `pseudocode` joins the six groups **to each other**, within a year. Do **not**
  assume it is stable across years until checked — verify by intersecting the
  2020-21 and 2024-25 profile keys and comparing state/district for a sample.
- Nothing under `raw/dsp/` is committed. `.gitignore` covers `*.zip`, `*.csv` and
  `extracted/`. Verify before any commit:
  ```bash
  find raw -type f -print0 | xargs -0 -I{} git check-ignore -q {} || echo LEAK
  ```

## Gotchas already found in the codebook — read before writing code

1. **`Yes=1, No=2`.** Not 1/0. A truthiness test on these columns is wrong for
   every "No" row.
2. **`_b` columns are "Boys + Transgenders"**, per the codebook's own remark. So
   `_b`/`_g` is not a clean male/female split, and a gender ratio built from them
   silently folds transgender students into boys. Say so in the schema docs.
3. **Almost every attribute is a numeric code "As per UDISE DCF"** —
   `school_category`, `school_type`, `managment` (sic, misspelt in the source),
   `rural_urban`, `medium_instr*`, `aff_board_*`. These need codemaps in
   `codemaps/` before the data is usable; the codebook PDFs do not list all the
   DCF values, so some will have to come from the UDISE DCF manual.
4. **`managment` is misspelt in the source.** Keep the source spelling at the raw
   layer and rename on the way out, as `aishe/` does for `Manegement`.
5. **Size.** Do not `pandas.read_csv` a 562 MB CSV on a laptop and hope. Stream in
   chunks or push the CSV straight into BigQuery and reshape in SQL.

## Suggested route

1. **Codemaps first.** `codemaps/dsp_item_group.csv` (the decode above — it is
   small, exact, and everything downstream depends on it), then
   `dsp_school_category.csv`, `dsp_management.csv`, `dsp_rural_urban.csv`.
2. **Profile before enrolment.** `profile_data_1/2` is the smallest useful pair and
   establishes whether `pseudocode` behaves as expected. Land
   `udise_dim_school_dsp` (one row per school per year) and stop there for a first
   PR.
3. **Then enrolment**, reshaped long: one row per
   `(year, pseudocode, class, gender, item_group, item_id)` → count. Wide-to-long
   on 24 class×gender columns against a 562 MB input is the step that needs the
   streaming decision made up front.
4. **Teacher and facility last** — useful, but neither is on the critical path for
   the BPL/EWS question.

**Reconcile every table against a published UDISE+ total before loading**, the same
standard `aishe/` holds to. The UDISE+ dashboard publishes state-level enrolment
totals; the existing `udise_fact_enrolment` (Report 4000, `SUM(enrolment) =
246,932,680` for 2024-25) is a ready cross-check for the DSP enrolment sum once
it is aggregated to the same grain. If those two disagree, find out why before
loading — they are the same survey.

## Open questions to settle first

- Is `pseudocode` stable across 2020-21 and 2024-25? Everything longitudinal
  depends on it.
- Does the DSP enrolment total reconcile with Report 4000 for 2024-25?
- Are the two years' column sets identical, or does 2024-25 add/rename columns
  (the two codebook PDFs differ, so assume not)?
- Given `pseudocode` cannot join to Avanti's schools, which questions does this
  actually answer? Worth confirming with Akshay before the enrolment reshape,
  which is the expensive part.
