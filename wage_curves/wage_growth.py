"""
Wage growth, age 25 → 40 — from PLFS, plus a projection for the NIRF elite.

PLFS gives an age–wage profile (median/P75/P90 by 5-yr age band) for the degree
buckets it can separate (Engineering, Medicine, Agriculture) and the general
bucket. From it we read the 25→40 growth multiple per discipline.

THE ELITE PROBLEM: the NIRF top tiers start far above anything PLFS observes —
IIT median is ₹13L/yr, but PLFS engineering P90 tops out around ₹96k/mo
(~₹11.5L/yr) even at age 40-44. So PLFS literally does not contain IIT-level
earners (small population + top-coding). We therefore can't *measure* their
growth; we project it two ways and bound it:
  • PLFS-rate (floor): apply the PLFS engineering median multiplier (~1.7×).
    Assumes the elite grow at the population rate — almost certainly too low.
  • Elite CAGR: a documented early-career CAGR for IIT/IIM-type trajectories
    (tech / finance / management / equity). Default 9%/yr → ~3.6× over 15 yrs.
    Anchored to IIT alumni salary data: start ₹8-15L → ₹30-60L mid-career (5-10y)
    → ₹50L-1cr senior (15y+), which implies a ~8-10% 15-yr-average CAGR (steeper
    early, then flattening). Tune with --elite-cagr. Caveat: top-campus *entry*
    wages are down ~22% real since 2010 & IIT placement <70%, so the START is
    under pressure even as the growth multiple stays steep. Sources in README.

Also note the PLFS multiple is CROSS-SECTIONAL (today's 40-yr-olds vs today's
25-yr-olds), which UNDER-states true longitudinal growth: today's 40-yr-olds
started ~15 yrs ago at lower real wages, so a 25-yr-old today will likely exceed
them by 40. Treat the PLFS multiple as a lower bound.

Run: python3 wage_curves/wage_growth.py [--elite-cagr 0.09]
"""

import argparse
import collections
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PLFS = ROOT.parent / "plfs"
SRC = PLFS / "clean" / "annual_2022_23" / "perv1.csv"
FULL = ROOT / "wage_curve_full.csv"
sys.path.insert(0, str(PLFS / "scripts"))
from weights import get_weight_fn          # noqa: E402

BANDS = ["25-29", "30-34", "35-39", "40-44"]


def band(a):
    if 25 <= a <= 29: return "25-29"
    if 30 <= a <= 34: return "30-34"
    if 35 <= a <= 39: return "35-39"
    if 40 <= a <= 44: return "40-44"
    return None


def bucket(tedu, gedu):
    if tedu in ("03", "13"): return "Engineering"
    if tedu in ("04", "14"): return "Medicine"
    if tedu in ("02", "12"): return "Agriculture"
    if tedu in ("", "01") and gedu in ("12", "13"): return "General"
    return None


def wmedian(vw):
    if not vw: return None
    s = sorted(vw); tw = sum(w for _, w in s); c = 0.0
    for v, w in s:
        c += w
        if c >= tw / 2: return v
    return s[-1][0]


def plfs_profile():
    wf = get_weight_fn("annual_2022_23")
    agg = collections.defaultdict(list)
    with SRC.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            b = bucket((r.get("tedu_lvl") or "").strip(), (r.get("gedu_lvl") or "").strip())
            if not b:
                continue
            try:
                a = int(r["age"])
            except (ValueError, KeyError):
                continue
            bd = band(a)
            if not bd or r.get("pas") != "31":
                continue
            try:
                e = int(r.get("ern_reg", "0") or "0")
            except ValueError:
                e = 0
            if e > 0:
                agg[(b, bd)].append((e, wf(r)))
    return agg


def eng_tiers_start():
    """Engineering tier start wages (₹/yr) from the full curve."""
    out = {}
    for r in csv.DictReader(FULL.open()):
        if r["discipline"] == "Engineering" and r.get("start_wage_inr"):
            out[r["tier"]] = float(r["start_wage_inr"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--elite-cagr", type=float, default=0.09,
                    help="Assumed early-career CAGR for NIRF-elite trajectories (default 0.09).")
    args = ap.parse_args()

    agg = plfs_profile()

    print("PLFS age–wage profile (annual_2022_23, regular-salaried median ₹/mo)")
    print(f'{"Discipline":<12}' + "".join(f"{b:>10}" for b in BANDS) + f'{"25→40":>8}{"n(40)":>7}')
    print("-" * 70)
    mult = {}
    for b in ["Engineering", "Medicine", "Agriculture", "General"]:
        meds = {bd: wmedian(agg[(b, bd)]) for bd in BANDS}
        m25, m40 = meds["25-29"], meds["40-44"]
        mult[b] = (m40 / m25) if (m25 and m40) else None
        cells = "".join(f'{("₹"+format(meds[bd],",")) if meds[bd] else "—":>10}' for bd in BANDS)
        print(f'{b:<12}{cells}{(f"{mult[b]:.2f}x" if mult[b] else "—"):>8}{len(agg[(b,"40-44")]):>7}')

    m = mult["Engineering"]
    print(f"\nNIRF engineering elite — projected wage at ~40 (start = fresh-grad median)")
    print(f"  PLFS-rate floor = ×{m:.2f} (engineering median 25→40, cross-sectional, a LOWER bound)")
    print(f"  Elite CAGR      = ×{(1+args.elite_cagr)**15:.2f} ({args.elite_cagr:.0%}/yr over 15 yrs)")
    print(f'\n{"Tier":<36}{"Start ₹/yr":>12}{"@40 PLFS-rate":>15}{"@40 elite":>13}')
    print("-" * 78)
    rows = []
    for tier, start in eng_tiers_start().items():
        p_floor = start * m
        p_elite = start * (1 + args.elite_cagr) ** 15
        print(f'{tier:<36}{start:>12,.0f}{p_floor:>15,.0f}{p_elite:>13,.0f}')
        rows.append(dict(tier=tier, start_inr=round(start), age40_plfs_rate=round(p_floor),
                         age40_elite_cagr=round(p_elite), plfs_multiple=round(m, 2),
                         elite_cagr=args.elite_cagr))
    out = ROOT / "wage_growth.csv"
    with out.open("w", newline="") as f:
        cols = ["tier", "start_inr", "age40_plfs_rate", "age40_elite_cagr", "plfs_multiple", "elite_cagr"]
        wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
    print(f"\nWrote {ROOT.name}/{out.name}")
    print("Caveat: the elite column is an assumption (PLFS can't observe IIT-level earners). "
          "Validate --elite-cagr against an IIT/IIM alumni salary survey.")


if __name__ == "__main__":
    main()
