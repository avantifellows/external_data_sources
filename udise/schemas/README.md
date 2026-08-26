# udise schemas

▶ **NEXT: run the GCS upload + BigQuery load.** Everything up to that point is
built and committed — the five DSP editions are gzipped locally under
`raw/dsp/_staged/`, `schemas/dsp_layouts.json` records every observed header, and
`scripts/dsp_build_bq.py --print-sql` generates the finished SQL. The load needs a
working `gcloud auth login`; it blocked on an expired token.

```bash
python3 scripts/dsp_stage.py --raw          # source zips → GCS raw/ (audit copy)
python3 scripts/dsp_stage.py --load-only    # local gz → GCS staging → BQ staging
python3 scripts/dsp_build_bq.py             # staging → the two finished tables + validate
python3 scripts/dsp_build_bq.py --drop-staging   # once the numbers check out
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
  yet. They are not on the critical path for the BPL/EWS question.
- **2021-22.** No such edition is held. Adding it later needs only the zips in
  `raw/dsp/2021-22/` and the year added to `DSP_YEARS`.
