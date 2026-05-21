# roi — wage-curve estimate (FROZEN method)

How Avanti estimates **graduate wages + employment by destination tier**. Three
public sources, one shared taxonomy, one decomposition that reconciles to the
population baseline. This is the canonical method — it replaces the earlier
hand-blended 5-tier `wage_curves.csv` approach.

## The three sources

```
NIRF   nirf_fact_aggregate (BQ)        ── top-college placement % + median salary
   │   scripts/nirf_tiers.py              (ranking_year 2022 = full top-200 eng)
   ▼   → clean/nirf_tiers.csv
AISHE  ug_discipline_extrapolated       ── annual UG graduate universe (the master
   │   scripts/aishe_grads.py              count per field), 2024-25
   ▼   → clean/aishe_grads.csv
PLFS   PLFS CY2025 person microdata     ── population wage + % in regular work,
   ·   scripts/plfs_baseline.py            by field × credential, 25-29/30-34/35-40
   ·   compute() — in-memory, no CSV       (sibling repo ../../PLFS)
        scripts/avanti_estimate.py  ← combines all three (the Avanti Estimate)
        → clean/avanti_estimate.csv  (detailed)  + clean/avanti_estimate_deck.csv (rollup)
```

## Common taxonomy — `taxonomy.py` (single source of truth)

All three sources speak one language so they can be joined. Three levels:

1. **Common field** (9): Engineering · Medical · Other Technical · IT & Computer ·
   Science · Commerce · Management · Law · Other. STEM = first five.
2. **PLFS wage cell** — PLFS only resolves wages for 4 cells (Engineering,
   Medical, Other Technical, and one general-degree cell that every academic
   field shares). `PLFS_WAGE_FIELD` maps each common field to its cell.
3. **NIRF tier** — the ranked top-college cohorts: IIT · NIT · IIIT ·
   Other NIRF Top-200 Eng · Top NIRF Medical & Dental · Top NIRF Architecture &
   Planning · Top NIRF Law · Top NIRF Pharmacy. `NIRF_TIER_TO_FIELD` rolls them
   up into the common fields.

`taxonomy.py` holds `AISHE_TO_FIELD`, `PLFS_WAGE_FIELD`, `NIRF_TIER_TO_FIELD`,
`nirf_tier()`, `STEM_FIELDS` — change classifications here and all scripts follow.

## The decomposition (`avanti_estimate.py`)

For each field: **AISHE = the universe**, carve the NIRF top tiers off the front
at NIRF wages, and **back out the residual** so the graduate-weighted average of
(tops + residual) equals the PLFS field average:

> `rest_wage = (PLFS_avg · AISHE_total − Σ NIRF_wageᵢ · gradsᵢ) / (AISHE_total − Σ gradsᵢ)`

- **Engineering** splits IIT / NIT / IIIT / Top Engineering / Other, with IIT,
  NIT, IIIT scaled to **national** graduate counts and IIT+NIT+IIIT+Top pinned to
  250,000 grads.
- **Medical** splits **Govt** and **Private** MBBS/BDS (NMC/DCI seat counts) at
  the govt junior-resident wage; the rest is the PLFS residual.
- Law, Other-Technical (Pharmacy) carve their NIRF top; the residual is PLFS.
- Fields with no NIRF salary (IT & Computer, Science, Commerce, Management, Other)
  sit wholly on the PLFS general-degree wage.

### Deck rollup (6 buckets)
`avanti_estimate_deck.csv` clubs the detailed rows into the deck taxonomy:
**IIT · NIT/IIIT · Top Engg Colleges · MBBS/BDS — Govt · MBBS/BDS — Private ·
Others** (grad-weighted). "Others" = the all-graduate residual = the slide-E2
counterfactual.

## Run

```bash
cd external_data_sources/roi
./run_roi.sh        # nirf_tiers → aishe_grads → avanti_estimate (PLFS in-memory)
python3 scripts/avanti_estimate.py   # the Avanti Estimate + deck rollup
python3 scripts/plfs_baseline.py     # standalone: the 8-group PLFS table
```

## Assumptions (all tunable at the top of `avanti_estimate.py`)

| Input | Value | Source |
|---|--:|---|
| IIT / NIT / IIIT national grads | 16K / 22K / 8K | JoSAA seat matrix (approx) |
| Top-engineering cap | 250,000 | working assumption |
| Govt MBBS+BDS grads | 60,000 | NMC/DCI seat matrix |
| Private MBBS+BDS grads | 78,000 | NMC/DCI seat matrix |
| MBBS/BDS early wage | ₹7.0L | 7th CPC junior-resident scale |

## Flags (accepted simplifications)
- **NIRF package vs realized wage** — NIRF salary is the placement *package* of
  placed students; PLFS is the *realized* median of those in regular work.
  Treated as comparable; packages run higher, so residuals are conservative.
- **Median-as-mean** — PLFS gives a median; the back-out is a mean identity.
  (Pushes "Other Medical" down to ~₹1.6L, an artifact — it lands in Others anyway.)
- **"If-working" wages**; employment shown separately.
- NIRF salaries are **2022** (~35% below 2025).

## Remaining steps (frozen method, open implementation)
1. **Mid/senior age bands** — extend the estimate from 25-29 to the full curve
   (30-34, 35-40) using the PLFS growth multipliers (data already in `compute()`).
2. **Wire into consumers** — repoint the donor-report RoI / projection / deck
   from the legacy `wage_curves.py` loader to `avanti_estimate_deck.csv`
   (done as part of the monorepo merge).
3. **MBBS count refinement** and the **2022→2025 recency hybrid** if current ₹ needed.

## Outputs (`clean/`)
| File | Grain |
|---|---|
| `nirf_tiers.csv` | NIRF top-college tier |
| `aishe_grads.csv` | UG discipline + field rollups |
| `avanti_estimate.csv` | field × tier (detailed) |
| `avanti_estimate_deck.csv` | 6 deck buckets |

PLFS has no CSV — `plfs_baseline.compute()` returns aggregates in memory.

> **Legacy:** `wage_curves.py` (old 5-tier blend + loader API) is retained only so
> the donor-report consumers keep importing until they are repointed in the
> monorepo merge. Do not extend it — `avanti_estimate.py` is the method.
