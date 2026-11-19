# PLFS Weights — per-release rules and how to apply them

PLFS releases use **four different weight rules**. Using the wrong one will
give estimates that are 2× too high (CY2023) or 100× too high (CY2025) etc.
This file documents the rules and points to the canonical implementation.

## TL;DR — use the module, not the math

```python
from weights import get_weight_fn
weight_fn = get_weight_fn('calendar_2023')

import csv
total = 0.0
with open('clean/calendar_2023/cperv1.csv') as f:
    for row in csv.DictReader(f):
        total += weight_fn(row)

print(f"Weighted population: {total/1e9:.2f}B")    # should print ≈ 1.18B
```

`get_weight_fn(release_id)` looks up the rule in `scripts/releases.py`
(authoritative — also exported as the `weight_rule` column in
`clean/releases.csv`) and returns the matching Python function.

## The four rules

### 1. `combined` — the standard PLFS formula

Used by every annual release, plus calendar releases CY2022 and CY2024.

```
weight = mult / no_qtr / IF(nss = nsc, 100, 200)
```

Where:

| Field    | Meaning                                                                            |
| -------- | ---------------------------------------------------------------------------------- |
| `mult`   | Per-record sub-sample-wise multiplier. Stored as integer with **2 implied decimals** (so `mult=1204376` means a float multiplier of 12,043.76). |
| `no_qtr` | Count of contributing FSUs in this `sector × state × stratum × sub-stratum` cell across the 4 contributing quarters. |
| `nss`    | FSUs surveyed in this cell **for the same sub-sample**.                            |
| `nsc`    | FSUs surveyed in this cell **combined across both sub-samples**.                    |

The `IF(nss = nsc, ...)` test handles the rare case where only one of the two
independent sub-samples landed in this cell — divide by 100 to avoid double-
counting; otherwise divide by 200.

### 2. `half_yearly` — CY2023 only

CY2023 (catalog 208) is the one release that uses a **half-yearly panel**
design instead of quarterly. The standard formula gives a half-year estimate;
divide by 2 for the calendar-year estimate.

```
weight = combined(row) / 2
```

Per the CY2023 README §3: "Simple average of the estimates of the two panels will generate
estimate for the Calendar Year 2023."

### 3. `simple` — CY2025 only

CY2025 (catalog 284) redesigned the weighting. Each record's `mult` is already an ANNUAL weight —
no combining across quarters, just strip the 2 implied decimals.

("Fully-calibrated" is what this said, and it is the wrong word in a document whose whole finding is
that PLFS applies no calibration — see "What is genuinely not established" below. It meant ready to
use, not calibrated to a population total. A loose word in the one place a reader checks the mechanism
is how the invented-mechanism error happened the first time.)

```
weight = mult / 100
```

Per the CY2025 README. No NSS=NSC logic, no NO_QTR.

### 4. `limited` — CY2021, not usable

CY2021 (catalog 209) shipped with a stripped-down schema (Blocks 1, 4, 6
only — no `tedu_lvl`, `pas`, `ind_pas`, `ern_reg`). The dataset is usable for
demographic and Current Weekly Status analysis, but not for engineering-jobs
or wage analyses. `get_weight_fn('calendar_2021')` raises
`NotImplementedError` if you call it for general use.

## Per-release lookup

| Release           | Catalog | Weight rule    |
| ----------------- | ------: | -------------- |
| `annual_2018_19`  | 216     | `combined`     |
| `annual_2019_20`  | 217     | `combined`     |
| `annual_2020_21`  | 206     | `combined`     |
| `calendar_2021`   | 209     | **`limited`**  |
| `annual_2021_22`  | 214     | `combined`     |
| `calendar_2022`   | 211     | `combined`     |
| `annual_2022_23`  | 210     | `combined`     |
| `calendar_2023`   | 208     | **`half_yearly`** |
| `annual_2023_24`  | 213     | `combined`     |
| `calendar_2024`   | 254     | `combined`     |
| `calendar_2025`   | 284     | **`simple`**   |

Source of truth: `clean/releases.csv` column `weight_rule`. Generated from
`scripts/releases.py`.

## Every rule verified against its own release's README, 2026-08-26

Until this audit the rules had been generalised from one or two READMEs. All eleven are now read, and
each coded rule is checked against the sentence in its own release's document.

| release | its README says | coded | ✓ |
|---|---|---|---|
| `annual_2018_19` | `MLTS/100 if NSS=NSC = MLTS/200 otherwise`; "For annual estimate, MLTS may be divided by number of quarters" | `combined` | ✓ |
| `annual_2019_20` | identical wording | `combined` | ✓ |
| `annual_2020_21` | same, divisor defined as "(count of surveyed FSUs in a sector x state x stratum x substratum)" | `combined` | ✓ |
| `annual_2021_22` | same, "(number of times a particular sector x state x stratum x substratum contributes in the year in terms of surveyed FSUs)" | `combined` | ✓ |
| `annual_2022_23` | `MULT/100 … /200`; "MULT may be divided by NO_QTR (count of occurrences of surveyed FSUs…)" | `combined` | ✓ |
| `annual_2023_24` | `MULT/100 … /200`; "divided by NO_QTR (count of contributing sector x state x stratum x substratum in 4 quarters)" | `combined` | ✓ |
| `calendar_2022` | `MULT/(NO_QTR*100)` if `NSS=NSC` else `MULT/(NO_QTR*200)` — divisor inside the formula | `combined` | ✓ same arithmetic |
| `calendar_2023` | same formula **for the Half Yearly Panel**, then §3: "Simple average of the estimates of the two panels will generate estimate for the Calendar Year 2023" | `half_yearly` (`combined`/2) | ✓ |
| `calendar_2024` | `MULT/(NO_QTR*100)` … `*200`, for the Calendar Year | `combined` | ✓ |
| `calendar_2025` | "Since the weight (MULT) is calculated at two places of decimal, the final weight will be: Final Weight = MULT/100" | `simple` | ✓ |
| `calendar_2021` | `MLTS/100 … /200` **with no NO_QTR**, and "Simple average of the estimates of the two Panels will generate estimate for the Calendar Year 2021" | `limited` | n/a — see below |

Three things this audit changed or found:

1. **`annual_2023_24` had no documentation in this repo at all.** Its acquisition took only the Nesstar
   bundle and the portal's download guide, so its rule had never been checked against its own README.
   Pulled from catalog 213 and filed in `raw/docs_annual_2023_24/` — it matches `combined`. See that
   folder's `SOURCE.md`.
2. **`calendar_2023`'s `/2` is correct and now sourced.** It is §3 of its README ("simple average of the
   estimates of the two panels"), not §2-3 as this file previously cited. The number was right; the
   citation pointed at the wrong paragraph.
3. **`calendar_2021` is a HALF-YEARLY release, not just a limited one.** Its README carries the same
   "simple average of the two Panels" instruction and gives the formula *without* `NO_QTR`. It is
   currently `limited` (stripped schema, `weight_annual` NULL) so nothing is wrong today — but if it is
   ever enabled it needs `half_yearly` and its own divisor handling, **not** `combined`. Recorded here
   because "limited" hides that.

## Why the totals move between releases — context, not an open question

`raw/docs_annual_2023_24/Note_on_Updated_Instruction_for_PLFS_2023-24.pdf` §2.1.5 records the urban
frame code changing: "A new frame code **2017-22 UFS-18** for urban samples has been added. The updated
frame codes for urban areas … are: 2007-12 UFS-15, 2012-17 UFS-17, 2017-22 UFS-18."

So the urban sampling frame is refreshed between releases, which is a documented reason for the frame's
implied population — and therefore the weighted total — to move. Useful to know when a release's total
shifts and you are wondering whether something broke: the answer may simply be that the frame was
updated.

**NOTHING DEPENDS ON PINNING THIS DOWN, and an earlier version of this section wrongly called it a
follow-up worth doing.** Two reasons it is not owed work:

- **Percentages are unaffected.** Any scale error cancels between a numerator and a denominator, which
  is why PLFS publishes ratios and why the India HE dashboard reads only rates from these weights.
- **A count needs a MEASURED factor, not an explained one.** The correction is the target year's
  population over that release's own weighted total. That is empirical: it is correct whatever the
  cause of the level, and it stays correct if the level ever moves, which is why it is computed per
  release rather than derived once from a mechanism.

The frame code itself is item 11 of Schedule 0.0PL and no clean CSV carries it, so the hypothesis
cannot be tested against our own data. That is a fact about the parse, not a gap holding anything up —
worth doing only if someone one day wants to attribute the urban drift specifically, which no current
consumer needs.

## Sub-sample-wise and quarterly estimates

The rules above are for the **annual / calendar-year combined estimate** —
the most common use. The PLFS documentation also defines:

- **Sub-sample-wise weight** (use when you've filtered to one sub-sample
  only, e.g., for variance estimation):
  ```
  weight_subsample = mult / no_qtr / 100
  ```

- **Quarterly combined weight** (use when restricting to a single quarter):
  ```
  weight_quarter = mult / IF(nss = nsc, 100, 200)
  ```
  Note: not divided by `no_qtr` because you're not annualizing.

These aren't in the module today — if you need them, add `_quarterly_*` rules
to `scripts/weights.py`. PR welcome.

## On the formula commonly shared by researchers

A pattern that floats around in NSSO / PLFS analysis examples:

```
mult / IF(Sector × Stratum × Sub-Stratum
        = Sector × Stratum × Sub-Stratum × Sub-Sample, 100, 200)
```

This re-derives the `NSS = NSC` check by grouping. It has three subtle issues:

1. **It drops `state` from the cell key.** PLFS stratum codes reset per
   state — `Stratum = 2` in Punjab and `Stratum = 2` in Tamil Nadu are
   different strata. Grouping without state collapses unrelated strata.
   Fix: include `state` in the grouping key.
2. **It re-does work the file already did.** PLFS provides `nss` and `nsc`
   per record. Just compare them; don't re-derive by grouping. Also more
   robust under filtering — the stored values were computed on the full
   sample before any analysis filter.
3. **It produces only the quarterly combined estimate.** For an **annual**
   estimate (which is what almost every analysis wants), you also need the
   `/ no_qtr` factor.

Our `_combined()` in `weights.py` handles all three correctly.

## What the total actually means

**Verified, and it is less than I first claimed.** Two things are established and one is not, and the
line between them matters because this section has now carried three different wrong explanations.

### Established: our arithmetic is MoSPI's arithmetic

The per-release README states the rule directly. `docs_annual_2018_19/README_July18_June19.pdf`
"Note for users" §3:

> For generating combined estimate (taking both the subsamples together) ... Final weight = MLTS/100
> if NSS=NSC, = MLTS/200 otherwise.

and §4:

> Generation of combined estimate for the entire Year: For annual estimate, MLTS may be divided by
> number of quarters.

That is exactly `_combined()`. The sample also matches the published counts exactly — 2018-19 has
420,757 V1 persons in 101,579 households, the figures printed in its own README. **So the level of the
weighted total is MoSPI's, not an artefact of this pipeline.**

### Established: the frame and the PPS size measure are Census 2011

`EstimationProcedure_PLFS.pdf` §1.2.7 (rural frame = "List of 2011 Population Census villages"),
§1.2.8 (urban strata by town size "as per Population Census 2011"), §1.2.11.1 (allocation "in
proportion to the population as per Census 2011"). The technical clarification §2-3 gives the weight as
`Σzᵢ/zᵢ`, "an inverse of inclusion probability", where `Σzᵢ` is "the total size (Census Population in
rural sector) of the NSS region". No calibration, post-stratification or benchmarking step appears
anywhere in the estimation procedure.

That explains a shortfall against the current population, and in the right direction.

### The totals are STABLE across recent releases, and sit below contemporaneous population

With the documented Assam PPS defect excluded — nine rows carrying 5,925,062 each, which inflated
`annual_2022_23` and `calendar_2022` — the picture is two eras, not a trend:

| era | Σ weights / Census 2011 | spread |
|---|---|---|
| **2022-23 onward** (6 releases) | 0.962 – 0.996 | **3.3%** |
| 2018-19 → 2021-22 (4 releases) | 0.890 – 0.956 | 6.6% |

Per release: 2018-19 0.890, 2019-20 0.923, 2020-21 0.914, 2021-22 0.956, then CY2022 0.962,
2022-23 0.966, CY2023 0.975, CY2025 0.985, 2023-24 0.995, CY2024 0.996.

**So there is no drift to explain in the current data.** The recent six sit flat at 96-100% of the 2011
count. Excluding the Assam defect is what made that visible: it had put 2022-23 and CY2022 at 1.010 and
1.006, above their neighbours, so removing it tightened the series rather than disturbing it.

The four earliest releases sit 4-11% lower. That is a level difference confined to 2018-2021, not an
ongoing trend, and it coincides with documented design changes — the MoSPI clarification records NSS
regions becoming the basic stratum for 2022-23 and 2023-24, and SRSWOR replacing PPS from January 2025.

### What is genuinely not established

Why the level sits below contemporaneous population at all — roughly 82-84% on recent releases. A PPS
design with inverse-probability weights should be unbiased for the current total, and a 2011 frame
misses only people in units formed since 2011, which is far less than the gap. So the frame's vintage
does not account for it, and no document in `raw/docs/` does either.

That is MoSPI's number rather than a calculation of ours, and nothing here depends on it: see the rule
below. Three earlier explanations in this repo and its consumers were wrong — "under-counts
institutional populations / floating workers" (institutional population is ~1% of India, not 20%),
"PLFS's own *projected* population" (there is no projection), and "reproduces Census 2011 by
construction" (which this file asserted, on the strength of one release landing at 0.994).

**Four guesses is enough. The honest statement is: the shortfall's direction follows from a
Census-2011 frame, and its magnitude and drift are not explained by any document in `raw/docs/`.**
If you need the reason, it is a question for MoSPI, not for inference.

### What to do about it

- **A percentage needs no correction, ever.** This is the operative point and it does not depend on
  any of the above: the frame's vintage and any scale error cancel between a numerator and a
  denominator. It is why PLFS publishes ratios (`EstimationProcedure` §3.6).
- **A count needs a per-release factor, measured rather than reasoned.** Divide the target year's
  population by that release's weighted total. Do not derive one factor and reuse it: the ratio moves
  from 0.78 to 0.84 across the releases, so a single factor is wrong at both ends.

## Validation

`python3 scripts/weights.py` asserts the two properties that follow from the design above, and exits
non-zero if either fails.

Current output:

```
annual_2018_19     combined                 1.08B  ✓
annual_2019_20     combined                 1.12B  ✓
annual_2020_21     combined                 1.11B  ✓
calendar_2021      limited                      —  skip
annual_2021_22     combined                 1.16B  ✓
calendar_2022      combined                 1.22B  ✓
annual_2022_23     combined                 1.22B  ✓
calendar_2023      half_yearly              1.18B  ✓
annual_2023_24     combined                 1.20B  ✓
calendar_2024      combined                 1.21B  ✓
calendar_2025      simple                   1.19B  ✓
```

The self-test checks **both**:

1. **Ratio to the Census 2011 frame within 0.85-1.05.** A release outside it is not grossing up to
   the frame its design implies, so the load or the weight rule is wrong.
2. **No single weight above `SUSPECT_WEIGHT` (1,000,000).** The national band in (1) is far too coarse
   to catch one catastrophic weight: the Assam PPS defect below inflates its release by only 4.4%,
   comfortably inside any sane band, while inflating Assam threefold and the national age-25-29
   estimate by 11.2%. It has to be checked per record.

It also **counts and reports rows whose weight fails to compute** instead of skipping them. The
previous version wrapped the call in `except Exception: pass`, so a release with a changed layout would
have read low and passed the band check as a plausible number.

Run it after adding any release, or after touching `weights.py`.

## The 2022-23 PPS weight defect

`annual_2022_23` and `calendar_2022` each contain **nine rows with weight 5,925,062** — 17x the
largest legitimate weight in any release. An **uninhabited** Assam village was selected by PPS: its
Census 2011 population is zero (entered as one for selection), and `weight = Σzᵢ/zᵢ` explodes as `zᵢ`
approaches zero. MoSPI documented it in
`raw/docs_annual_2022_23/Technical clarification regarding high multiplier value in PLFS 2022-23.pdf`,
confirmed it happened once in ~12,000 FSUs a year, and fixed the design from January 2025 (SRSWOR
instead of PPS, plus a separate all-India stratum for uninhabited villages).

Nine rows stand for 53.3m people:

| | contaminated | expected |
|---|---|---|
| Assam, all ages | 94.0m | ~31m (Census 2011: 31.21m) |
| Assam, age 25-29 | 15.6m | 3.76m (adjacent releases: 2.90m, 3.02m) |
| National, age 25-29 | 105.7m | 93.8m — **11.2% inflated** |

`load_bq.py` marks these rows with **`weight_suspect = TRUE`** on the loaded tables, so the exclusion
is explicit and greppable rather than folklore. **Filter `WHERE NOT weight_suspect` for any estimate**
— nothing legitimate is excluded by it. The rows are kept rather than dropped because they are
legitimately sampled and their responses are real; it is only the weight that is unusable.

## How to apply weights in analysis code

```python
import csv
from weights import get_weight_fn

release_id = 'calendar_2025'
weight_fn = get_weight_fn(release_id)

# Engineering grads age 25-29 — weighted population
total = 0.0
with open(f'clean/{release_id}/cperv1.csv') as f:
    for row in csv.DictReader(f):
        try:
            age = int(row['age'])
        except (ValueError, KeyError):
            continue
        if 25 <= age <= 29 and row.get('tedu_lvl') == '03':
            total += weight_fn(row)

print(f"Engineering grads aged 25-29 in {release_id}: {total:,.0f}")
# → Engineering grads aged 25-29 in calendar_2025: 2,656,011
```

Same code pattern works for any release. Never hardcode a weight formula in
an analysis — always go through `get_weight_fn(release_id)`.

## When you add a new release

1. Set the `weight_rule` field in `scripts/releases.py` to one of the four
   names — usually `combined`. Verify by reading the release's README.
2. Run `python3 scripts/releases.py` to regenerate `clean/releases.csv`.
3. Run `python3 scripts/weights.py` — the self-test should pass for the new
   release. If it doesn't (`Σ weights` < 0.95B or > 1.35B), the rule is wrong.
4. If the release introduces a **new weight rule** (e.g., MoSPI changes the
   methodology again — they've done it for CY2023 and CY2025 already), add
   a new `_<rule>()` function to `scripts/weights.py` and register it in
   `WEIGHT_FNS`. Document the rule in this file.
