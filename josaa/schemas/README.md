# JoSAA in 60 seconds

A primer for anyone querying `josaa_*` who hasn't worked with engineering
counselling data. Read this before writing SQL.

## The setup

**JoSAA** = Joint Seat Allocation Authority. It runs *one* centralized
counselling for India's centrally-funded engineering institutes:

- **IITs** — admit on the **JEE Advanced** rank.
- **NITs, IIITs, GFTIs** (Government Funded Technical Institutes) — admit on
  the **JEE Main** rank.

Students rank their program preferences; JoSAA allots seats over several
**rounds**. After each round it publishes, per seat bucket, the **opening
rank** (first/best candidate allotted) and **closing rank** (last/worst
candidate allotted = the **cutoff**).

## The five things that bite

1. **Two rank spaces, never mix them.** A closing rank of 5,000 at an IIT
   (Advanced) is a far stronger student than 5,000 at an NIT (Main). The
   institute decides which space applies.

2. **Rounds are snapshots, not increments.** Each (year, round) is a complete
   re-publication of cutoffs. To get the year's *final* cutoff, take the row
   with the max `round` per (institute, program, quota, seat_type, gender,
   year). **Never sum or average across rounds.**

3. **Closing rank ≠ "best closing rank."** Cutoffs move round to round (often
   loosen as upgrades cascade). "Closing rank for the year" is a definitional
   choice — Avanti's convention is MAX(closing_rank) across main rounds, but
   that's a College-DB convention, applied downstream, not baked in here.

4. **Preparatory ranks live on a different scale.** Ranks flagged
   `*_is_preparatory` (JoSAA's trailing-`P` list, for certain SC/ST/PwD
   candidates) are not comparable to main-list ranks. Filter them out unless
   you specifically want them.

5. **Institute names drift.** Same college, different spelling across years.
   Match with keyword `LIKE`/`REGEXP`, not equality.

## What's here vs what's not

| Here (`josaa_*`, this repo) | NOT here (College DB repo) |
|---|---|
| Raw JoSAA opening/closing ranks, all rounds, all years | Avanti salary tiers, `college_type` taxonomy |
| `quota`, `seat_type`, `gender` exactly as published | Canonical `college_id` / state mapping, NIRF-salary enrichment |
| Preparatory flags | "final closing rank = MAX across rounds" derivation |

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `josaa_fact_cutoffs` | (institute, program, quota, seat_type, gender, year, round) | ~523k |

Column-level docs: [`josaa_fact_cutoffs.yaml`](josaa_fact_cutoffs.yaml).
