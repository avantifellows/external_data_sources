"""
PLFS per-release weight functions — single source of truth.

Every PLFS release ships its own weight rule, and we MUST use the right one
or estimates will be off by 2x (CY2023) or 100x (CY2025) etc. This module
codifies the four rules and exposes a single API:

    from weights import get_weight_fn
    weight_fn = get_weight_fn('calendar_2023')

    for row in csv.DictReader(f):
        w = weight_fn(row)   # returns float, the calibrated annual weight

Where the rules come from:
    - 'combined'    : the standard PLFS formula in the operational README that
                      ships with every annual release + CY2022 + CY2024.
                      weight = mult / no_qtr / IF(nss = nsc, 100, 200)
    - 'half_yearly' : CY2023 (catalog 208) — half-yearly panel design. The
                      standard formula gives a half-year estimate; need an
                      extra /2 to get the full calendar-year estimate.
    - 'simple'      : CY2025 (catalog 284) — redesigned weight scheme. Each
                      record's `mult` is calibrated for the full year directly.
                      weight = mult / 100
    - 'limited'     : CY2021 (catalog 209) — stripped-down schema. No usable
                      weight column for engineering-jobs analysis; raises
                      NotImplementedError.

Every release's weight_rule is recorded in clean/releases.csv and in
scripts/releases.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))
from releases import RELEASES


# ---- Cell-value coercion -------------------------------------------------

def _safe_int(x, default: int = 0) -> int:
    """Read a cell value as int. Handles '', None, '1234.0' (float-style)."""
    if x is None:
        return default
    try:
        return int(x)
    except (ValueError, TypeError):
        # CY2022's pre-converted CSV stored some ints as "1234.0"
        try:
            return int(float(x))
        except (ValueError, TypeError):
            return default


# ---- The four rules ------------------------------------------------------

def _combined(row: Mapping[str, str]) -> float:
    """Standard PLFS rule. mult/100 in two implied decimals; divide by no_qtr
    (number of contributing cells across quarters) and by 100 if both sub-samples
    sampled the same FSU count, else 200."""
    mult = _safe_int(row.get("mult"))
    nss = _safe_int(row.get("nss"))
    nsc = _safe_int(row.get("nsc"))
    no_qtr = _safe_int(row.get("no_qtr"), 1) or 1
    divisor = 100 if nss == nsc else 200
    return mult / no_qtr / divisor


def _half_yearly(row: Mapping[str, str]) -> float:
    """CY2023 — half-yearly panels. Apply standard formula then halve again
    for the full calendar year."""
    return _combined(row) / 2


def _simple(row: Mapping[str, str]) -> float:
    """CY2025 — mult already calibrated; just strip the 2 implied decimals."""
    return _safe_int(row.get("mult")) / 100


def _limited(row: Mapping[str, str]) -> float:
    """CY2021 has limited schema (Blocks 1, 4, 6 only). Don't use this release
    for engineering-jobs analysis."""
    raise NotImplementedError(
        "CY2021 (cat 209) ships a stripped-down schema with no tedu_lvl / pas / "
        "ind_pas / ern_reg. Use a different release for engineering-jobs work."
    )


# ---- Public API ----------------------------------------------------------

WEIGHT_FNS: dict[str, Callable[[Mapping[str, str]], float]] = {
    "combined":    _combined,
    "half_yearly": _half_yearly,
    "simple":      _simple,
    "limited":     _limited,
}


def get_weight_fn(release_id: str) -> Callable[[Mapping[str, str]], float]:
    """Return the calibrated weight function for the given release.

    The function takes a dict-like row (e.g., from csv.DictReader) and returns
    a float — the row's contribution to a weighted annual estimate.
    """
    cfg = RELEASES.get(release_id)
    if cfg is None:
        raise KeyError(f"Unknown release: {release_id!r}. "
                       f"Known: {sorted(RELEASES)}")
    rule = cfg["weight_rule"]
    if rule not in WEIGHT_FNS:
        raise ValueError(f"Release {release_id!r} has unknown weight rule {rule!r}. "
                         f"Known rules: {sorted(WEIGHT_FNS)}")
    return WEIGHT_FNS[rule]


def weight_rule_of(release_id: str) -> str:
    """Return the named weight rule for a release (e.g., 'combined')."""
    return RELEASES[release_id]["weight_rule"]


# ---- Self-test -----------------------------------------------------------

def _self_test() -> None:
    """Sanity-check: each release's calibrated weight summed across all
    persons should yield ~1.1-1.2B (close to India's ~1.4B population — PLFS
    slightly under-counts institutional/floating populations)."""
    import csv as _csv

    print(f'{"Release":<18} {"Rule":<14} {"Σ weights (B)":>15} {"Status":>8}')
    print("-" * 60)
    for rid, cfg in RELEASES.items():
        if cfg["weight_rule"] == "limited":
            print(f'  {rid:<18} {cfg["weight_rule"]:<14} {"—":>15} {"skip":>8}')
            continue
        weight_fn = get_weight_fn(rid)
        # Pick the person-level file
        out_dir = cfg["out_dir"]
        per_path = (out_dir / "perv1.csv") if (out_dir / "perv1.csv").exists() else (out_dir / "cperv1.csv")
        if not per_path.exists():
            print(f'  {rid:<18} {cfg["weight_rule"]:<14} {"missing":>15}')
            continue
        total = 0.0
        with per_path.open() as f:
            for row in _csv.DictReader(f):
                try:
                    total += weight_fn(row)
                except Exception:
                    pass
        billions = total / 1e9
        ok = 0.95 <= billions <= 1.35
        status = "✓" if ok else "WARN"
        print(f'  {rid:<18} {cfg["weight_rule"]:<14} {billions:>14.2f}B {status:>8}')


if __name__ == "__main__":
    _self_test()
