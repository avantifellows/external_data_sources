# aishe/schemas

⏸ PAUSED — resume by fixing the seven unreconciled `(year, table)` pairs listed in
the comment above `PDF_TABLES` in [`../scripts/sources.py`](../scripts/sources.py).
Highest value first: **Table 34 for 2018-19** (off by just −51, one wrapped
programme name, and Table 33's Grand Total can anchor it), then
**(2017-18, Table 12)** (+38,652, one subject row read as a discipline), then the
two ranked-list Table 35s (2016-17, 2017-18), which need a different reader.

Also outstanding, in order:
1. The **GER / GPI time series** (`raw/aishe_timeseries_*.pdf`, both parsed and
   verified, 2011-12 → 2021-22) — its own table, its own PR. GPI is **not**
   derivable from GER (checked all 33 cells; published GPI runs up to 0.055 below
   female-GER/male-GER), so both series must be stored.
2. **2022-23 / 2023-24** from PDF — captions must be checked before registering.
3. **2012-13 → 2014-15** — PDFs fetch, no `PDF_TABLES` entries yet.
4. The paired **data-assistant** PR: schema copy at
   `docs/schemas/external_data_sources/aishe_fact_higher_ed_students.yaml`, an
   analysis-intent block in `docs/analyses/external_data_sources.yaml`, and a
   regenerated `CLAUDE.md`.

---

## AISHE concepts in 60 seconds

**AISHE** = All India Survey on Higher Education, run annually by the Ministry of
Education. It is India's official census of higher education — universities,
colleges and standalone institutions self-report through the AISHE portal. It is
*the* national source for how many students are enrolled, how many graduate, in
which subjects, where, and from which social groups.

**Response is voluntary and incomplete.** The reports say "based on actual
response" precisely because not every registered institution replies. A year's
figures are the responding institutions' totals, not the country's true totals, so
a year-on-year change can reflect who answered as much as what happened.

**enrolment vs graduates.** `enrolment` is the *stock* — students currently
studying. `graduates` (AISHE calls it "out-turn") is the annual *flow* — those who
qualified that year. A four-year B.Tech. cohort has roughly four times as many
enrolled as graduating annually. Never compare one to the other as if they measure
the same thing.

**Three ways students get classified, easily confused:**

| Concept | Means | Examples |
|---|---|---|
| `level` | stage of study | Ph.D., Post Graduate, Under Graduate, Diploma |
| `programme` | the named degree | B.A., B.Tech., MBBS, M.Sc. |
| `discipline` | the broad subject area | Arts, Science, Engineering & Technology |

`programme` and `discipline` use **incompatible classifications** and cannot be
cross-walked exactly. Table 34a is degree-based; Tables 12/35 are subject-based.
For subject-based numbers use the `ug_discipline` cut, not the programme cut.

**Social categories overlap.** `All Categories` is a superset of SC / ST / OBC /
PwD / Muslim / Other Minority / EWS, and those bands overlap each other too (a
person can be both SC and PwD). Summing across `social_category` double-counts.

**GER and GPI** (published separately, not yet a table). *Gross Enrolment Ratio* is
enrolment in higher education as a percentage of the 18–23 population — so it moves
when either enrolment or the population projection changes, and AISHE's series is
pinned to the 2011 Census projection. *Gender Parity Index* is the ratio of female
to male participation; 1.0 means parity, above 1.0 means women participate more.

**Why Avanti cares.** Low-income student representation in top-tier colleges;
whether the STEM / non-STEM mix is shifting; per-state graduate supply against
Avanti's own footprint; and the long-run gender gap. The STEM split lives in
[`../codemaps/discipline_to_stem.csv`](../codemaps/discipline_to_stem.csv) — broad
definition, including medical and paramedical.

## Tables documented here

| Schema | Table | Grain |
|---|---|---|
| `aishe_fact_higher_ed_students.yaml` | the student fact | cut × year × metric × dims |
| `aishe_dim_colleges.yaml` | college registry | `aishe_code` |
| `aishe_dim_universities.yaml` | university registry | `aishe_code` |
| `aishe_dim_standalone_institutions.yaml` | standalone registry | `aishe_code` |
| `aishe_dim_research_institutions.yaml` | R&D institute registry | `aishe_code` |
| `aishe_dim_pm_vidyalaxmi_eligible_institutions.yaml` | PM Vidyalaxmi eligibility | `aishe_code` |

The schema YAMLs are **documentation**, not enforced at load — the physical BQ
table may carry more columns than a YAML lists.
