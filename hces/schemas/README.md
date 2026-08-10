# HCES in 60 seconds

**What it is.** The **Household Consumption Expenditure Survey (HCES)** is MoSPI's nationally
representative survey of what Indian households *spend*. Fielded across a full year in rotating panels,
it is the source behind India's poverty lines, the CPI weights, and most "how do Indians live" numbers.
The 2023-24 round covers 261,953 households. It records expenditure, demographics, dwelling and assets,
but it does **not** ask income.

**The grain.** One row per surveyed household, keyed by a composite `HHID`. Geography is nested:
state → NSS region → district, and district/region codes are numbered *within* a state, so always key on
`(state_code, ...)`, never the child code alone.

**Two things that change every number:**

1. **Weights are mandatory.** Each sampled household stands in for many real ones. `weight` (= raw
   multiplier / 100) is the number of households the row represents; `people_weight` (= weight × hh_size)
   is the number of persons. A `COUNT(*)` is a *sample size*, not a population. Use `SUM(weight)` for
   households and `SUM(people_weight)` for people. National weighted totals: ~330M households, ~1.4B people.

2. **Consumption is measured; income is derived.** HCES measures spending, not earning. India has no
   nationwide income survey. So income here is *projected* from consumption via the savings identity
   `income = consumption / (1 - s)`, where the savings rate `s` rises with the household's position in the
   spending distribution (negative at the bottom, where households dis-save). The `est_*` columns are that
   projection under **one** schedule (CMIE-CPHS 2022-23). They are a modelled estimate, not a surveyed
   fact. The whitepaper triangulates two more schedules (RBI-NAS, WIL); this table ships the CMIE one as
   the canonical single estimate.

**MPCE.** Monthly Per-Capita Expenditure = total monthly spend / household size. The standard NSS welfare
ranking variable. The income projection's percentile is computed on people-weighted MPCE.

**Consumption vs income vs poverty.** `monthly_exp_total` / `mpce` = measured spend. `est_monthly_income`
= modelled income. `ration_card_name` = an official poverty-status proxy (AAY/BPL/APL), independent of the
income estimate. Don't conflate the three.
