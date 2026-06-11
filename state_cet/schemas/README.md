# State CETs in 60 seconds

A primer for anyone querying `state_cet_*`. Read before writing SQL.

## The setup

Most Indian states run their **own** engineering entrance exam + counselling
for the **state-quota** seats in their colleges — separate from the national
JoSAA pool. One brand per state:

| State | CET |
|---|---|
| Maharashtra | MHT-CET |
| Karnataka | KCET |
| Tamil Nadu | TNEA |
| Andhra Pradesh | AP-EAMCET |
| Telangana | TG-EAPCET |
| West Bengal | WBJEE |
| Kerala | KEAM |
| Gujarat | ACPC |
| Bihar | BCECE |
| Odisha | OJEE |

This table is the harmonized union of their published cutoffs — the
**state-quota counterpart to JoSAA** (`josaa_*`, which is the national
IIT/NIT/IIIT/GFTI pool).

## The things that bite

1. **Rank scales are NOT comparable across CETs.** A KCET rank and an
   MHT-CET rank are different populations. Never threshold/sort across states
   without normalizing. Always read `rank_basis`.

2. **Some CETs report MARKS, not ranks.** TNEA publishes a cutoff mark (out
   of 200). For those rows `closing_rank` is NULL and `closing_mark` carries
   the value. `rank_basis` tells you which.

3. **This is a curated subset, not raw source.** Three things baked in:
   - **Govt colleges only** (private/deemed excluded) — see `college_type`.
   - **Categories harmonized to 5-cat** GEN/EWS/OBC-NCL/SC/ST (original state
     labels like Karnataka GM/2A/3B are dropped here).
   - **Closing rank = final/MAX round** (not a per-round series).
   For raw state labels / private colleges / per-round detail → College DB
   `state-cet-scrape`.

4. **Quota semantics differ per state.** "State (TN domicile)", "HS (Home
   State)", "State Level", "rest of Karnataka" — don't assume uniformity.

5. **College names drift / had PDF newlines** (flattened to spaces here). Use
   keyword `LIKE`/`REGEXP`.

## What's here vs not

| Here (`state_cet_*`, this repo) | NOT here (College DB) |
|---|---|
| Govt-scope closing ranks/marks, 10 states, 5-cat | Avanti salary tiers, stream-tier cutoffs, college bucketing |
| `rank_basis`, `source_url` provenance | Original state category labels, private colleges, per-round series |

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `state_cet_fact_closing_ranks` | (state, cet_name, stream, year, college_code, branch_code, quota, category, gender) | ~7.8k |

Column docs: [`state_cet_fact_closing_ranks.yaml`](state_cet_fact_closing_ranks.yaml).
