# AISHE — analytical questions (and the table shape they imply)

AISHE out-turn data exists to answer a handful of questions about India's
higher-education graduate supply. Following the `plfs/` convention, the BigQuery
shape is derived from these questions — a *small* number of wide, denormalized
facts; per-question and derived logic lives here in `analysis/`, not as extra
tables.

## The questions

1. **Annual graduate supply by discipline, and its trend.**
   How many students complete UG programmes each year in Engineering, Science,
   Arts, Commerce, Medical Science, …? How fast is each discipline growing
   (2019-20 → 2021-22)?
   *Cut:* aishe_year × discipline × gender, metric ∈ {enrolment, out_turn}.
   → **`aishe_fact_ug_discipline_trend`**

2. **Gender composition of graduates.**
   Female share of graduates by discipline, by level (PhD/PG/UG/…), and by
   state. Where are the largest gender gaps?
   *Cut:* gender is carried on every fact (Boys / Girls / Total) — no separate
   table.

3. **Equity: graduate output by social category.**
   How many SC / ST / OBC / EWS / Muslim / other-minority / PwD students
   graduate, by degree programme — and rolled up to discipline? How does
   representation differ across B.Tech vs B.A. vs MBBS?
   *Cut:* programme × social_category × gender (national).
   → **`aishe_fact_outturn`** (programme × social_category slice);
   discipline rollup → `analysis/rollup_discipline_social_category.py`.

4. **Graduate output by state and level.**
   Which states produce the most graduates, and at what levels (PhD / PG / UG /
   PG Diploma / Diploma / Certificate / Integrated)?
   *Cut:* state × level × gender.
   → **`aishe_fact_outturn`** (state × level slice).

5. **Projected graduate capacity (planning).**
   Given the trend, what is the expected annual UG supply by discipline in
   2024-25 / 2025-26, for sizing programmes against demand?
   → `analysis/project_discipline_2025_26.py` on top of
   `aishe_fact_ug_discipline_trend`. Model estimate, not published data.

## The table shape that falls out — 2 tables (was 7)

Per plfs/'s "few well-shaped facts, denormalize aggressively per use case":

### `aishe_fact_outturn`  — one wide cross-sectional out-turn fact (2021-22)
Unifies AISHE Tables **33** (state × level), **34a** (programme × social
category), and **35** (UG discipline) into a single fact. Dimensions that don't
apply to a given source cut carry the sentinel **`"All"`** — consistent with how
AISHE itself already reports `Total` gender, `All Categories`, and `All Streams`.

Grain: `(aishe_year, level, state, discipline, programme, social_category, gender)` → `out_turn`

Query by filtering to the slice you want; **never `SUM(out_turn)` across rows of
different grain** (e.g. don't add a `state=`specific row to a `state="All"` row).
Worked slices:
- state × level:        `programme="All" AND discipline="All" AND social_category="All"`
- programme × social:   `state="All" AND discipline="All" AND level="All"`
- UG by discipline:     `state="All" AND programme="All" AND social_category="All" AND level="Under Graduate"`

### `aishe_fact_ug_discipline_trend`  — UG enrolment + out-turn by discipline, 2019-20 → 2021-22
The time series behind Q1 and the input to the Q5 projection (AISHE Tables 12 +
35 across three reports).

Grain: `(aishe_year, metric, discipline, gender)` → `value`  (metric ∈ enrolment | out_turn)

## Not tables — derived logic lives here in `analysis/`

- **`rollup_discipline_social_category.py`** — rolls Table 34a (programme ×
  social category) up to discipline using the heuristic
  `codemaps/programme_to_discipline.csv`. Degree-name based; cannot recover
  subject-based disciplines (Indian Language, Social Science, …). Emit as a
  notebook output or a BQ view if needed downstream — not a base table.
- **`project_discipline_2025_26.py`** — linear (OLS) projection of the trend to
  AY 2024-25 / 2025-26. Model estimate, not AISHE-published data.

The programme→discipline **codemap stays a committed CSV**
(`codemaps/programme_to_discipline.csv`) — the audit interface the rollup reads —
rather than a BQ dimension table.

## Why this is better than 7 tables

The original split mirrored the source PDF tables (one per published table +
derived rollups). But the *questions* only need two shapes: a denormalized
2021-22 cross-section you slice by any dimension, and a discipline time-series.
The discipline×social rollup and the projection are **derivations** of those,
so they belong in `analysis/` (reproducible, reviewable) — keeping BigQuery to
two clean facts instead of seven overlapping ones.
