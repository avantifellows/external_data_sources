# State medical counselling in 60 seconds

A primer for anyone querying `state_medical_*`. Read before writing SQL —
this is the trickiest of the counselling sources.

## The setup

A government medical college's seats split two ways:

- **~15% All India Quota** — counselled nationally by MCC → `mcc_*`.
- **~85% State Quota** — counselled by **each state's own authority**, on its
  own merit list and reservation rules. **This table.**

32 states/UTs, 2025-26 cycle, MBBS + BDS.

## The thing that bites hardest: rank spaces

States don't publish cutoffs on a common scale. `rank_space` tells you what
`closing_rank` actually is:

- **`'NEET AIR'`** (~75% of rows) — a national NEET All-India Rank. Comparable
  across states and to `mcc_*`.
- **`'state-native'`** — that state's own merit rank/score. **NOT comparable**
  to other states or to AIR. `conversion_method` names the native scale.

**Rule:** filter `rank_space = 'NEET AIR'` for any cross-state or cross-source
comparison. Never mix scales.

## Other things that bite

1. **Comparable-AIR for the native states is NOT here.** The upstream pipeline
   estimates one (plus tiers, round multipliers, R3 projections) — those are
   Avanti *models*, kept in College DB, excluded from this neutral table.

2. **`round` is free text** ('R1+R2+R3', 'MopUp', 'Phase-3', …). Don't cast to INT.

3. **Quality flags.** `source_quality` ∈ {official, third-party};
   `is_estimated` TRUE when the closing_rank itself was projected. Filter both
   for strict official actuals.

4. **Category label differs from sibling sources.** Here unreserved = `'UR'`
   (vs `mcc_*` 'Open', `state_cet_*` 'GEN'). `category` may be NULL where a
   state doesn't break category out; `category_raw` keeps the original.

5. **`state` is a 2-letter code** — join `codemaps/state_code.csv` for names.

## What's here vs not

| Here (`state_medical_*`, this repo) | NOT here (College DB) |
|---|---|
| Native closing ranks + rank_space + conversion provenance | Estimated unified AIR for state-native states |
| official/third-party flag, is_estimated | Avanti salary tiers, round multipliers, R3 projection |
| canonical + raw category | — |

## Tables

| Table | Grain | Rows |
|---|---|---:|
| `state_medical_fact_closing_ranks` | (state, college, program, category, round) | ~2.9k |

Column docs: [`state_medical_fact_closing_ranks.yaml`](state_medical_fact_closing_ranks.yaml).
