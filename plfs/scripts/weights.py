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

# Census 2011, used as a STABLE YARDSTICK for drift detection, not as a target the weights are
# supposed to hit. The observed ratio to it runs 0.89-1.00 and drifts upward, so this is a reference
# point that makes a change in the weights visible — nothing more. See WEIGHTS.md "What the total
# actually means", including what is NOT established about why the level moves.
CENSUS_2011 = 1.2109

# PPS assigns weight = frame_size / unit_size, so a unit recorded with near-zero size gets a
# near-infinite weight. MoSPI documented this happening once — an uninhabited Assam village in
# 2022-23, weight 5,925,062 — and asked users to account for it. The largest legitimate weight across
# the eleven releases is 347,281, so this bound sits ~2.9x above anything real and ~17x below the
# defect. Rows above it must be excluded from any estimate: nine of them stand for 53.3m people.
SUSPECT_WEIGHT = 1_000_000


def _self_test() -> int:
    """Assert the two properties that follow from PLFS's documented sample design.

    1. Each release's summed weight stays inside the band the ten loaded releases actually occupy,
       measured against Census 2011 as a fixed yardstick. This is DRIFT DETECTION, not a claim that
       the weights should equal any particular number: the observed ratio runs 0.89-1.00 and moves
       upward release to release. A new release landing outside the band means the load or the weight
       rule changed, which is the thing worth catching. See WEIGHTS.md for what is and is not
       established about the level itself.
    2. No single weight is absurd. The band in (1) is a national aggregate and is far too coarse to
       notice a single catastrophic weight: the Assam PPS defect inflates its release by 4.4%, well
       inside any sane band, while inflating Assam threefold and the national age-25-29 estimate by
       11.2%. It has to be checked per record.

    Returns the number of failures, so callers and CI can act on it.
    """
    import csv as _csv

    fails = []
    print(f'{"Release":<18} {"Rule":<14} {"Σ weights":>12} {"/C2011":>8} {"max weight":>12} {"suspect":>8}')
    print("-" * 78)
    for rid, cfg in RELEASES.items():
        if cfg["weight_rule"] == "limited":
            print(f'  {rid:<18} {cfg["weight_rule"]:<14} {"—":>12} {"":>8} {"":>12} {"skip":>8}')
            continue
        weight_fn = get_weight_fn(rid)
        out_dir = cfg["out_dir"]
        per_path = (out_dir / "perv1.csv") if (out_dir / "perv1.csv").exists() else (out_dir / "cperv1.csv")
        if not per_path.exists():
            print(f'  {rid:<18} {cfg["weight_rule"]:<14} {"missing":>12}')
            fails.append(f"{rid}: {per_path} is missing")
            continue
        total, mx, n_suspect, n_bad = 0.0, 0.0, 0, 0
        with per_path.open() as f:
            for row in _csv.DictReader(f):
                try:
                    w = weight_fn(row)
                except Exception as e:   # noqa: BLE001 - counted and reported, never swallowed
                    # The previous version was `except Exception: pass`, which silently dropped any
                    # row whose weight would not compute. A release with a changed layout would then
                    # read LOW and sail through the band check as a plausible number.
                    n_bad += 1
                    if n_bad == 1:
                        fails.append(f"{rid}: weight_fn raised on a row ({type(e).__name__}: {e}); "
                                     f"the layout or the weight rule is wrong for this release")
                    continue
                total += w
                mx = max(mx, w)
                if w > SUSPECT_WEIGHT:
                    n_suspect += 1
        billions = total / 1e9
        ratio = billions / CENSUS_2011
        flag = ""
        if not 0.85 <= ratio <= 1.05:
            fails.append(f"{rid}: summed weight is {ratio:.3f} of the Census 2011 frame "
                         f"({billions:.3f}B) — outside 0.85-1.05, so this release is not grossing up "
                         f"to the frame its design implies")
            flag = " TOTAL"
        if n_suspect:
            fails.append(f"{rid}: {n_suspect} row(s) exceed the suspect-weight bound "
                         f"({SUSPECT_WEIGHT:,}; max seen {mx:,.0f}). PPS on a near-zero-size unit — "
                         f"see the MoSPI clarification in raw/docs_annual_2022_23/. Exclude them.")
            flag = " WEIGHT"
        if n_bad:
            flag += " ROWS"
        print(f'  {rid:<18} {cfg["weight_rule"]:<14} {billions:>11.3f}B {ratio:>8.3f} '
              f'{mx:>12,.0f} {n_suspect:>8}{flag}')

    if fails:
        print(f"\n{len(fails)} problem(s):\n")
        for f in fails:
            print(f"  - {f}\n")
    else:
        print(f"\nOK — every release sits within 0.85-1.05 of the Census 2011 yardstick "
              f"({CENSUS_2011}B) and no weight exceeds {SUSPECT_WEIGHT:,}. NB: that band is where "
              f"these releases happen to fall, not a target — see WEIGHTS.md.")
    return len(fails)


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(1 if _self_test() else 0)
