# MHT-CET concepts in 60 seconds

MHT-CET is Maharashtra's state engineering/pharmacy entrance exam. The State CET
Cell runs about ten separate Centralised Admission Processes (CAPs) under one
roof — engineering, pharmacy, architecture, B.Design and more — each on its own
portal, all sharing one reservation taxonomy. This table records the last rank
admitted into each seat bucket for the 2025-26 cycle.

## Reading a category code

`category_raw` is the CET Cell's own code, and the legend printed on every
cutoff page decodes it in three parts:

```
G OPEN S
│  │   └─ End:    H = Home University, O = Other than Home University,
│  │              S = State Level, AI = All India
│  └───── Middle: OPEN / OBC / SC / ST / VJ / NT1 / NT2 / NT3 / SEBC / SBC
└──────── Start:  G = General (gender-NEUTRAL), L = Ladies (female-reserved)
```

So `GOPENS` is General/Open/State-Level and `LSCH` is Ladies/SC/Home-University.
Standalone codes also appear: `EWS`, `TFWS` (tuition-fee waiver), `ORPHAN`, `MI`
(minority), plus `DEF*` and `PWD*` prefixes for defence and disability seats.

## The one that's easy to get backwards

**`G` means General, not "boys".** G-seats are gender-neutral — open to every
candidate, women included. Maharashtra's 30% female reservation is *horizontal*:
it gives women `L*` seats **in addition to** their access to the `G*` pool.

```sql
-- WRONG: shows a female candidate ~1/3 of the seats she can actually take
WHERE gender = 'Girls'

-- RIGHT
WHERE gender IN ('All', 'Girls')
```

`gender` is only ever `'All'` or `'Girls'`. If you ever see `'Boys'`, the
upstream parser has regressed — `build_clean.py` fails the build on it.

## Vertical categories vs horizontal flags

`category` is the canonical 5-bucket rollup (`GEN`, `EWS`, `OBC-NCL`, `SC`,
`ST`) plus `OTHER`. Maharashtra's VJ / NT1–3 / SEBC / SBC groups have no clean
national equivalent, so they land in `OTHER` — that is ~22k rows, not a rounding
error. Use `category_raw` when you need the real Maharashtra category.

Horizontal flags are properties of the *seat*, not the candidate's social
category, and live in `sub_pool`: `PWD`/`PWDR` (disability), `DEF`/`DEFR`
(defence), `TFWS`, `ORPHAN`, `MIN`. A `PWDROBC` seat is an OBC seat carrying a
disability flag — `category = 'OBC-NCL'`, `sub_pool = 'PWDR'`.

```sql
-- Clean base-category aggregate: exclude the horizontal pools
WHERE sub_pool = ''
```

## Quota is a domicile pair

`quota` is the candidate's home-university region versus the college's:
`State Level`, `Home → Home`, `Other → Other`, `Home → Other`, `Other → Home`.
The same bucket closes at very different ranks across these pools, so never
aggregate over `quota` without meaning to.

## Two more traps

**Architecture is a different rank space.** It admits on MAH-AAC-CET / NATA
merit, not the MHT-CET PCM state merit rank. Filter on `stream` or `rank_basis`
before comparing ranks across streams. It is also the only stream with
`opening_score` / `closing_score` populated.

**A single-observation bucket is not a threshold.** `closing_rank` is
`MAX(rank)` over all rounds and stages; `num_rank_observations = 1` means a
one-seat pool that closed wherever its single applicant happened to sit. Many
NT/SEBC pools at low-demand colleges look "tighter" than the open pool for
exactly this reason — it is real counselling behaviour, not bad data.

## Codes are strings

`college_code` and `branch_code` are zero-padded (`'03012'` = VJTI). Casting to
INT silently breaks joins.

## Reproducibility

Every parsed per-stream CSV and the clean Parquet live under
`gs://avantifellows-external-data/mhtcet/`. The parsers that produced them are
in [`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2)
(`state_cet/scrape/scripts/state_MH.py`, `state_MH_arch.py`), with a regression
suite (`test_state_MH.py`) and an invariant scanner (`validate_MH.py`).
