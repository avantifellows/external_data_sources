# udise schemas

▶ **NEXT: push both branches and open the paired PRs** — `add-udise-dsp-microdata`
here and `add-udise-dsp-schemas` in data-assistant. Both are committed locally; the
push is gated by the ship hook. The BigQuery build is done and validated, staging is
dropped, and the source zips are in GCS.

```bash
python3 scripts/dsp_build_bq.py --validate    # re-run the checks any time
```

| Table | Grain | Schema |
|---|---|---|
| `udise_fact_enrolment` | state × management × category × location × class × gender, AY 2024-25 | [udise_fact_enrolment.yaml](udise_fact_enrolment.yaml) |
| `udise_dim_school_dsp` | school × academic year, 5 editions | [udise_dim_school_dsp.yaml](udise_dim_school_dsp.yaml) |
| `udise_fact_enrolment_dsp` | school × item × class × gender × academic year, 5 editions | [udise_fact_enrolment_dsp.yaml](udise_fact_enrolment_dsp.yaml) |

`dsp_layouts.json` is generated, not hand-written: `dsp_stage.py` records the
header of every CSV it stages. It is committed so that an upstream schema change
shows up as a git diff instead of as wrong numbers.

## UDISE+ concepts in 60 seconds

**UDISE+** (Unified District Information System for Education *Plus*) is the
Ministry of Education's annual **census of every school in India** — government,
aided, private, recognised and unrecognised, about 1.5 million of them. Each school
files a **DCF** (Data Capture Format) return once a year. Almost every attribute in
that return is a numeric DCF code rather than text.

The same census reaches us two completely different ways, and they must never be
mixed:

- **Report 4000** — an aggregated cross-tab generated on demand from the UDISE+
  dashboard. State × management × category × class × gender. One table:
  `udise_fact_enrolment`.
- **DSP** (Data Sharing Portal) — a de-identified **school-level** extract, one row
  per school, downloaded as zips per file group per year. Two tables so far:
  `udise_dim_school_dsp` and `udise_fact_enrolment_dsp`.

### The five things that get DSP numbers wrong

1. **`9` means "Not Applicable"**, on nearly every coded column, in every edition.
   It is not a category and it is not a count. Averaging a column without
   excluding 9 produces nonsense.
2. **Yes is 1 and No is 2** — not 1/0. Every `*_yn` column and most of the
   flag-shaped ones. A truthiness test is wrong for every "No" row.
3. **`_b` is "Boys + Transgenders"** in every edition through 2024-25 — the
   codebook says so outright. 2025-26 is the first edition with a separate `_t`
   column. `udise_fact_enrolment_dsp` puts this in the `gender` *value*
   (`boys_incl_transgender` vs `boys`) so it cannot be missed.
4. **The item breakdowns overlap.** Only `item_group=1` (social category)
   partitions the student body. Religion is a subset, BPL and EWS and repeaters and
   disability all cut across it. Summing across item groups double-counts children.
5. **`pseudocode` is pseudonymised.** It joins the DSP tables to each other within
   a year and nothing else. There is no school name and no UDISE code in the
   release, so it cannot reach Avanti's own school lists. Cross-year stability is
   unverified.

### Codemaps

Everything in `../codemaps/` is transcribed from the committed codebook PDFs in
`../docs/`, not guessed:

| File | Decodes |
|---|---|
| `dsp_item_group.csv` | the (item_group, item_id) enrolment breakdown — social category, religion, BPL, EWS, 20 disability types, repeaters |
| `dsp_item_desc_2020_21.csv` | 2020-21's text `item_desc` labels back onto those codes, and says plainly where no mapping exists |
| `dsp_school_category.csv` | school category → class range |
| `dsp_management.csv` | management code → who runs the school, plus a Government/Aided/Private/Other rollup |
| `dsp_school_type.csv`, `dsp_rural_urban.csv`, `dsp_resi_school.csv`, `dsp_building_status.csv`, `dsp_yes_no.csv` | the small enums |

Medium of instruction and affiliation board are DCF codes whose value lists the
codebooks never publish. They are carried as raw codes with no label, because a
guessed label is worse than no label.

## What is deliberately not loaded

- **2020-21 School Profile 2, source positions 20-45.** The CSV header names them
  `rte_ews_c0_b … rte_ews_c12_g`; the 2020-21 codebook says positions 20-37 are
  `rte_bld_*` and only 38-45 are `rte_ews_c9 … c12`. Header and codebook disagree
  about what 26 columns of numbers mean, so neither reading is publishable.
- **`NationalStreamEnrolment.csv`** (inside the 2020-21 enrolment_data_1 zip) — a
  class 11/12 stream × caste cut no other edition publishes. Different grain; it
  needs its own table.
- **`teacher_data`, `facility_data`, `safety`.** Downloaded and registered in
  `sources.py`, staged by `dsp_stage.py --groups …` on request, but not modelled
  yet. They are not on the critical path for the BPL question.
- **2021-22.** No such edition is held. Adding it later needs only the zips in
  `raw/dsp/2021-22/` and the year added to `DSP_YEARS`.

## What the data turned out to say, and the codebooks did not

Four things only showed up once the source was in BigQuery. All four are recorded
in the codemaps and schema YAMLs; they are collected here because each one changes
a query someone would otherwise write with confidence.

1. **EWS is a one-year column.** The codebook documents `item_group=10, item_id=32`
   as EWS enrolment, which makes it look like the poverty variable to reach for. It
   is published in **2023-24 only** — 25,100 schools, 762,929 students. It is absent
   from 2022-23, 2024-25 and 2025-26. **BPL (`item_group=3, item_id=13`) is the
   poverty variable that actually spans the panel**: 1.11-1.27 million schools and
   87-92 million students in every coded edition.
2. **`item_group=4` has a 21st disability code.** Every codebook lists item_ids 1-20;
   the data carries `item_id=21` in all four coded editions, with no published label.
   Left unlabelled rather than guessed. It is still included in a SUM over the group.
3. **The age id decodes to `age = item_id + 1`.** The codebooks describe
   `item_group=8`'s item_id only as "Age id (2 to 22)" and publish no key, which
   would have left the whole age cut unusable. It is derivable from the data because
   2020-21 labels the same cut in words: max id 22 lines up with max label `Age23`,
   the modal id for class 1 is 5 against an RTE class-1 entry age of 6, and modal id
   per class tracks Age(id+1) at classes 1, 5 and 10 alike. The fact carries this as
   a **derived** `age_years` column with raw `item_id` beside it; the derivation and
   its evidence are in `../codemaps/dsp_age_item_id.csv`.
4. **12% of 2020-21 schools carry an unlabelled enrolment row.** 182,426 of
   1,509,136 schools have one extra row with an empty `item_desc`, sitting right
   after BPL. It is not a total (it never exceeds the school's General+SC+ST+OBC
   sum), not a duplicate of BPL or Aadhar, and not EWS-shaped (75% of the schools
   carrying it are `managment=1`, Dept. of Education, where the RTE/EWS quota does
   not apply). It is worth ~8.9% of enrolment in the schools that report it. No
   codebook names it, so it stays unmapped — the rows are in the fact with
   `item_dimension IS NULL`, which is how you find and exclude them.
