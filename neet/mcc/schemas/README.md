# MCC / AIQ medical counselling in 60 seconds

A primer for anyone querying `mcc_*`. Read before writing SQL.

## The setup

**MCC** (Medical Counselling Committee, under DGHS) runs the **national**
medical admission counselling on the **NEET-UG All India Rank (AIR)**. It allots:

- the **15% All India Quota** of government MBBS/BDS seats (`quota = 'All India'`),
- **100% of deemed / central** seats — AIIMS, JIPMER, ESIC, DU, AMU, BHU, …,
- plus NRI / paid / ESI / B.Sc-Nursing pools.

It's the medical analogue of JoSAA (engineering), and the **national**
counterpart to the ~85% state-quota seats counselled by state authorities
(→ `state_medical_*`).

## The things that bite

1. **closing_rank is a NEET AIR** (lower = better; 1 = national topper). The
   cutoff = worst AIR that still got a seat.

2. **Huge closing ranks are normal.** BDS, paid, deemed, and NRI pools sit far
   down the merit list — closing ranks of 100k–500k+ are expected there, not
   data errors. Segment by `course` and `quota` before drawing conclusions.

3. **This is the FULL AIQ allotment, not govt-only.** Every quota MCC counsels
   is here. For just the government AIQ pool, filter `quota = 'All India'`. (A
   govt-scoped cut for Avanti analysis lives in College DB, not here.)

4. **PwD is a flag, not a category.** `category` ∈ {Open, OBC, SC, ST, EWS};
   `is_pwd` carries the disability sub-pool split. Don't string-match "PwD".

5. **R1 only, for now.** `round = 1`, `year = 2025`. R2/R3 will append as
   higher `round` values later — take max round per bucket for "final".

## What's here vs not

| Here (`mcc_*`, this repo) | NOT here (College DB) |
|---|---|
| Full AIQ R1 closing ranks, all quotas, MBBS/BDS/Nursing | Govt-only scoped cut, institute_type tagging |
| `category` + `is_pwd`, `allotted_count` | Avanti salary tiers / college bucketing |
| — | State-quota (85%) seats → that's `state_medical_*` |

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `mcc_fact_closing_ranks` | (institute, course, quota, category, is_pwd, year, round) | ~3.1k |

Column docs: [`mcc_fact_closing_ranks.yaml`](mcc_fact_closing_ranks.yaml).
