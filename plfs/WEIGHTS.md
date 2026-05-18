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

`python3 scripts/weights.py` runs a self-test: it sums the calibrated weights
across each release's `perv1`/`cperv1` table and prints the result. **All
totals should land in ~1.08-1.22B** (India's actual population is ~1.4B;
PLFS under-counts institutional populations / floating workers).

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

If a release ever drifts outside `0.95B – 1.35B`, the self-test flags it. Run
this after adding any new release, or after touching `weights.py`.

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
