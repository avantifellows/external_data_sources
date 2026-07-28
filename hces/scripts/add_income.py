#!/usr/bin/env python3
"""
Derive household income from consumption and write the BigQuery table parquet.

Reads the consumption master produced by transform_hces.py:
    clean/hces_household_master.parquet

HCES measures consumption, not income. We project income at the household level
via the savings identity  Income = Consumption / (1 - s), where the savings rate
s is a function of the household's position in the (people-weighted) MPCE
distribution, interpolated from the CMIE-CPHS 2022-23 savings schedule. This is
ONE of the three schedules the whitepaper triangulates (CMIE / RBI-NAS / WIL);
the loaded table uses the CMIE schedule as the canonical single estimate.

Writes the final table (the one loaded into BigQuery):
    clean/hces_fact_household_master.parquet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

HCES_DIR = Path(__file__).resolve().parent.parent
CLEAN = HCES_DIR / "clean"
MASTER = CLEAN / "hces_household_master.parquet"
OUT = CLEAN / "hces_fact_household_master.parquet"

# CMIE-CPHS 2022-23 savings schedule: percentile in the MPCE distribution -> savings
# rate, linearly interpolated between anchors. Negative at the bottom (the poorest
# dis-save, i.e. consume more than income via transfers/borrowing), rising to ~42%
# at the very top. Anchored to CMIE's reported income-vs-consumption by decile.
SAVINGS_ANCHORS_CMIE = np.array([
    [0.0, -0.55], [10.0, -0.40], [20.0, -0.20], [25.0, -0.10], [30.0, 0.00],
    [40.0, 0.03], [50.0, 0.07], [60.0, 0.11], [70.0, 0.15], [80.0, 0.19],
    [90.0, 0.25], [95.0, 0.30], [99.0, 0.35], [100.0, 0.42],
])


def weighted_percentile(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted-CDF mid-rank percentile (0-100) of each value."""
    order = np.argsort(values, kind="mergesort")
    v, w = values[order], weights[order]
    cw = np.cumsum(w)
    pct_sorted = (cw - 0.5 * w) / cw[-1] * 100.0
    pct = np.empty_like(pct_sorted)
    pct[order] = pct_sorted
    return pct


def main() -> None:
    if not MASTER.exists():
        raise SystemExit(f"{MASTER} not found. Run transform_hces.py first.")
    df = pd.read_parquet(MASTER)
    df = df[df["mpce"].notna() & (df["hh_size"] > 0)].copy()

    # People-weight: a 6-person household counts 6x, so the percentile is the
    # household's rank in the population of individuals (not of households).
    df["people_weight"] = df["weight"] * df["hh_size"]

    pct = weighted_percentile(df["mpce"].to_numpy(), df["people_weight"].to_numpy())
    df["mpce_percentile"] = pct
    df["savings_rate_assumed"] = np.interp(
        pct, SAVINGS_ANCHORS_CMIE[:, 0], SAVINGS_ANCHORS_CMIE[:, 1]
    )
    df["est_monthly_income"] = df["monthly_exp_total"] / (1 - df["savings_rate_assumed"])
    df["est_monthly_savings"] = df["est_monthly_income"] - df["monthly_exp_total"]
    df["est_pcm_income"] = df["est_monthly_income"] / df["hh_size"]

    df.to_parquet(OUT, index=False)
    print(f"  ✓ {len(df):,} households -> {OUT}")


if __name__ == "__main__":
    main()
