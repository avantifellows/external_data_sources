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

Per the CY2023 README §2-3.

### 3. `simple` — CY2025 only

CY2025 (catalog 284) redesigned the weighting. Each record's `mult` is
already a fully-calibrated annual weight; just strip the 2 implied decimals.

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

## Validation

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

### NOT established: why the level is what it is, or why it moves

The totals run **78-84% of contemporaneous population**, and the ratio drifts upward:

| release | Σ weights | / Census 2011 | / contemporaneous pop |
|---|---|---|---|
| annual_2018_19 | 1.078B | 0.890 | 0.779 |
| annual_2021_22 | 1.158B | 0.956 | 0.817 |
| annual_2023_24 | 1.204B | 0.994 | 0.836 |
| calendar_2025 | 1.193B | 0.985 | 0.822 |

Sample size is near-constant across these (413k-428k V1 persons) while the mean weight per person
rises 12.4%, from 2,562 to 2,880. **Neither ratio is flat.** If the weights were pinned to the 2011
frame, column 3 would be constant; if they tracked current population, column 4 would be. Both drift.

So "reproduces Census 2011 by construction" — which this file asserted before this revision — is
wrong. `annual_2023_24` landing at 0.994 is where a drifting series happens to sit, not a design
identity. Two earlier explanations were also wrong: "PLFS under-counts institutional populations /
floating workers" (institutional population is ~1% of India, not 20%) and, in data-assistant's schema
note, "PLFS's own *projected* population" (there is no projection).

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

## What the total actually means

**The summed weight reproduces the CENSUS 2011 population, by construction.** It is not an estimate
of the current population, it is not 15% wrong, and the gap is not under-coverage.

Read the survey's own documents, both in `raw/docs/`:

| where | what it says |
|---|---|
| `EstimationProcedure_PLFS.pdf` §1.2.7 | rural frame is the "List of 2011 Population Census villages"; urban is UFS blocks on 2011 census towns |
| §1.2.8 | urban strata by size class of towns "as per Population Census 2011" |
| §1.2.11.1 | sample allocated "in proportion to the population as per Census 2011" |
| `Technical clarification ... 2022-23.pdf` §2-3 | `weight = 1/P(selection) = Σzᵢ/zᵢ`, "an inverse of inclusion probability", where `Σzᵢ` is "the total size (**Census Population** in rural sector) of the NSS region" |

Searched the estimation procedure for *calibration*, *post-stratification*, *benchmarking* and
*projection*: **no matches.** These are pure design weights and nothing is applied after them. So the
PPS size measure *is* Census 2011 population, and summing the weights can only give the 2011 frame's
population. Measured: `annual_2023_24` state sums come to 1,200.8m against Census 2011's 1,207.5m for
the same 30 states — a ratio of **0.994**.

**This is why PLFS publishes rates and not counts** (`EstimationProcedure` §3.6 defines its outputs as
ratios `R = Ŷ/X̂`). The frame's vintage cancels between a numerator and a denominator, so:

- **A percentage needs no correction at all.** Ever.
- **A count is a 2011-frame count.** For a current-year figure, scale by population growth since 2011
  — about **×1.21** for 2025 (1.4639bn / 1.2109bn). Say which of the two you are quoting.

An earlier version of this section said totals "should land in ~1.08-1.22B (India's actual population
is ~1.4B; PLFS under-counts institutional populations / floating workers)". The band was right and
the explanation was invented — institutional population is ~1% of India, not 15%. That guess also
reached `data-assistant`'s schema note in a different wrong form ("PLFS's own *projected* population"),
and an analysis then argued from it that there was an unexplained coverage deficit. A wrong mechanism
attached to right numbers cannot be caught by checking the numbers, which is why the primary document
is not optional.

Still unexplained, and much smaller: the four earliest releases gross up to 0.89-0.96 of the frame
where 2022-23 onward sit at 0.97-1.01.

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
