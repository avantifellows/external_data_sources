# TG-EAPCET in 60 seconds

TGCHE and the Convener TG-EAPCET (JNTU Hyderabad) run Telangana's centralised
admission for degree engineering. This table records the **last admitted**
state rank in each seat bucket, from the Convener's own Last Rank Statement
PDFs (First / Second / Final Phase).

## The one thing that will bite you

**Gender is part of the grain.**

Telangana publishes a separate closing rank per gender for *every* category —
the 33% women's reservation is built into the seat pools, not applied
afterwards. The raw column labels are literally `OC_BOYS` / `OC_GIRLS`.

```sql
-- WRONG: silently mixes two different seat pools
SELECT college_name, MIN(closing_rank)
FROM tgeapcet_fact_cutoffs WHERE category = 'GEN' GROUP BY college_name

-- RIGHT
SELECT college_name, gender, MIN(closing_rank)
FROM tgeapcet_fact_cutoffs WHERE category = 'GEN' GROUP BY college_name, gender
```

## The second thing: SC is split three ways

The 2024 SC Rationalization GO divides SC into **SC_I / SC_II / SC_III**, and
the 2025 PDFs publish all three separately with materially different cutoffs.
`category` rolls them up to `SC`; `category_raw` keeps the real sub-group. If
someone asks "what rank does an SC student need", ask which sub-group.

The 2024 source had a single `SC` column, so year-on-year SC comparisons are
not like-for-like.

## Rank direction

`closing_rank` is a **TG-EAPCET state rank — lower is harder**. It is MAX
across the three phases (the loosest rank a seat actually went at);
`opening_rank` is the MIN. Never compare it against another state's rank or
against a NEET/JEE All India Rank.

## What is deliberately NOT here

**Local area (OU / KU / TGUR).** Telangana allots against local-area sub-pools,
but the 2025 Last Rank Statement does not expose them per row — the published
rank is the headline all-local-area figure. A student's real cutoff in their
own local area can be easier than what this table shows. Say so rather than
implying precision.

## Govt scope

`college_type IN ('Govt','State-Univ-Dept')` → 1,936 rows / 20 colleges.

Careful with `SF`: it is a self-finance stream *inside* a state university
(ESUTSF, JNTM) that fills at private-level ranks, so it maps to `Private/SF`,
not govt. Join on `college_code`, never `college_name` — two Trinity campuses
(TCEK, TCTK) share a name.
