# CMS-E — Comprehensive Modular Survey: Education (NSS 80th Round, 2025)

MoSPI's nationally representative survey of **what Indian households spend on
school education** — and, from the household roster, **who is not in school at
all**. Unit-level microdata → 3 BigQuery tables.

---

## Why we need this

Avanti's core claim is that talented students from low-income families cannot
buy their way to a JEE or NEET seat, and that the coaching market prices them
out. Until now we have asserted that. This table lets us **measure** it, on
nationally representative government data, at the two cuts we actually argue in:
**state by state** and **by gender**.

Concretely, it answers:

- **How large is the paid-coaching market our students are excluded from, and
  who is in it?** 27% of school students take private coaching; among Classes
  IX–XII, participation is nearly flat from the poorest decile to the ninth
  (36% → 48%) while *spend* runs 3.2x across the same range. Poor families buy
  coaching at almost the same rate and get a third as much of it. That is a
  sharper and more defensible framing of the gap than participation alone.
- **What does the equity gap look like by social group and gender?** Coaching in
  Classes IX–XII: ST 20.3%, SC 38.1%, OBC 37.4%, Others 45.5% — a 25-point
  ST-to-Others gap. By gender, 39.4% male vs 36.3% female, narrower than usually
  assumed and worth stating accurately rather than overstating.
- **How much do families actually pay, per state?** Needed for programme design
  and for the fundraising narrative — the cost we displace, benchmarked against
  what families in that state really spend.
- **How thin is public scholarship support?** Government scholarships are the
  first funding source for **1.2%** of students; other household members fund
  **95%**. That single pair of numbers grounds the case for privately funded
  scholarships better than anything we have had.
- **Who never gets to the starting line?** The person file is a full household
  roster, not a list of students, so it measures children who are *not enrolled*.
  Across compulsory schooling ages (6–17) **6.2%** are out of school, rising to
  **14.6%** at ages 15–17 — and the gradient is the steepest
  thing in this source: **28.1% in the poorest consumption decile against 3.7% in
  the richest**, a 7.5x gap, with **ST 25.1% against Others 7.5%**. (Deciles over
  households, weighted, hostel households excluded — the recipe changes the number,
  so `schemas/cmse_fact_person.yaml` states it beside the figure and `clean_cmse.py`
  reprints the whole series on every build.) Set beside the
  25-point ST-to-Others gap in coaching *among those who are enrolled*, that is the
  full shape of the problem on one survey: a gap in getting in, then a gap in what
  you can buy once you are.

It is also the natural companion to two tables already in the warehouse:
`hces_fact_household_master` (consumption and derived income, for levels) and
`plfs_fact_persons` (labour-force structure). CMS-E is the education-spend leg.

---

## What we are committing

**BigQuery** — `avantifellows.external_data_sources`:

| Table | Grain | Rows | Clustered on |
|---|---|---|---|
| `cmse_fact_student` | one row per student | 59,417 | `state_code`, `gender_name`, `enrolment_level_code`, `cut` |
| `cmse_fact_household` | one row per surveyed household | 52,085 | `state_code`, `sector_name`, `social_group_name` |
| `cmse_fact_person` | one row per member asked the enrolment question | 214,757 | `state_code`, `age_band`, `is_enrolled`, `social_group_name` |

**GCS** — `gs://avantifellows-external-data/cmse/`:

- `raw/CMSE80HH25.csv`, `raw/CMSE80PER25.csv`, `raw/CMSE80PERST25.csv` — the
  three MoSPI unit-level files as released
- `raw/docs/` — all six official MoSPI documentation files plus the DDI codebook
- `clean/cmse_fact_student.parquet`, `clean/cmse_fact_household.parquet`,
  `clean/cmse_fact_person.parquet`

**In git** — pipeline only: `scripts/` (transform, codemap builder, GCS staging,
BQ loader), `schemas/` (3 table YAMLs + the concepts primer), `codemaps/`
(13 CSVs, all generated from the official MoSPI code lists), and `docs/` (the
official documentation — public, small, and the only way to audit the decode).

**Not in git**: the raw CSVs (27 MB) and the clean parquet. Both live in GCS.

No PII. The microdata is anonymised at source — no names, no addresses, and
district codes carry no published name lookup.

---

## From which sources

| | |
|---|---|
| Publisher | Ministry of Statistics & Programme Implementation (MoSPI) / National Statistical Office |
| Survey | Comprehensive Modular Survey: Education (Schedule CMS-E), NSS 80th Round |
| Reference period | April–June 2025; expenditure refers to academic year 2025-26 |
| Coverage | All of India except villages in Andaman & Nicobar Islands |
| Catalog | [microdata.gov.in NADA catalog 255](https://microdata.gov.in/NADA/index.php/catalog/255) |
| Headline release | [PIB release 275295](https://archive.pib.gov.in/newsite/PrintRelease.aspx?relid=275295), 26 Aug 2025 |
| Retrieved | 2026-08-26 |
| Licence | Government of India open microdata, free for research and analysis with attribution |

Sample: 4,366 first-stage units (2,384 villages + 1,982 urban blocks), 52,085
households, 221,617 household members of whom 57,742 are enrolled students,
weighted to 242.3 million students in 287.0 million households.

---

## Provenance and verification

The build refuses to emit numbers nobody checked. `clean_cmse.py` reconciles
**fourteen** figures against MoSPI's own PIB release — enrolment shares by
sector, fee-paying rates by school type, average spend, coaching rates rural and
urban, and the funding split — and exits non-zero if any drifts:

```
[ok ] government school share %                    got 55.9      published 55.9
[ok ] avg annual school spend, government (Rs)     got 2,863.3   published 2,863.0
[ok ] avg annual school spend, non-government (Rs) got 25,001.9  published 25,002.0
[ok ] students taking private coaching %           got 27.0      published 27.0
[ok ] funded by government scholarship %           got 1.2       published 1.2
…14/14 reconcile
```

`cmse_fact_person` has **no published figure of its own** — MoSPI publishes no
out-of-school number for CMS-E — so its build-time anchor is internal and strict: its
enrolled half must be exactly, as a row set, `cmse_fact_student`'s `resident` cut, and
the build fails otherwise.

For the *level*, PLFS is the independent check, and it separates the two age bands
sharply. At **15–17 it corroborates**: not attending an educational institution runs
14.2–16.4% across the ten PLFS releases carrying the field, against CMS-E's 14.6%,
with PLFS on the high side as its principal-activity measure should be. At **3–5 it
does not** — PLFS reads 73–83% against CMS-E's 46.2%, a gap no bound explains, because
the two surveys count pre-primary attendance differently. So the secondary-age figure
carries independent agreement and the pre-primary one does not; see the foot of
[`schemas/cmse_fact_person.yaml`](schemas/cmse_fact_person.yaml).

Read [`schemas/README.md`](schemas/README.md) before analysing. Four traps in
this data change results materially — government in-kind support valued at zero,
integrated coaching invisible to the coaching columns, state fee regulation
masquerading as demand, and single-member hostel households inverting per-capita
rankings. All four are documented there with the fix.

---

## Layout

```
cmse/
├── README.md                  # this file
├── CLAUDE.md                  # orientation for Claude Code
├── requirements.txt
├── codemaps/                  # 13 CSVs generated from the official code lists
├── docs/                      # the six official MoSPI files + DDI codebook
├── schemas/                   # 3 table YAMLs + the concepts primer
├── scripts/
│   ├── sources.py             # single source of truth: paths, tables, code lists
│   ├── build_codemaps.py      # official xlsx → codemaps/*.csv
│   ├── clean_cmse.py          # raw CSV → clean parquet, with reconciliation
│   ├── check_person_guards.py # breaks each roster guard on purpose; all must fire
│   ├── upload_to_gcs.py       # stage raw+docs and clean to GCS
│   └── load_bq.py             # GCS parquet → BigQuery
├── raw/                       # gitignored
└── clean/                     # gitignored
```

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

# 1. put the three MoSPI CSVs in raw/  (from the NADA catalog above)
python3 scripts/build_codemaps.py         # regenerate codemaps from docs/
python3 scripts/clean_cmse.py             # → clean/*.parquet, reconciles or fails
python3 scripts/check_person_guards.py    # proves the roster's guards actually fire
python3 scripts/upload_to_gcs.py --raw    # stage source CSVs + docs
python3 scripts/upload_to_gcs.py          # stage clean parquet
python3 scripts/load_bq.py                # load all three tables (WRITE_TRUNCATE)
```

Idempotent throughout. No orchestrator, no schedule — this runs on demand, and
CMS-E is a one-off round with no successor announced.
