"""
Q5 (capacity): project UG out-turn by discipline to AY 2024-25 / 2025-26.

Ordinary least-squares fit on the 3-year discipline trend in aishe_fact_outturn
(the discipline slice: discipline != "All", years 2019-20 → 2021-22), projected
forward. Estimates floored at 0.

MODEL ESTIMATE, not AISHE-published data — use for directional planning only.

Source: clean/outturn.parquet (discipline slice)
Output: prints; writes outputs/discipline_projection_2025_26.csv if --save.

Usage:
  python3 analysis/project_discipline_2025_26.py [--save]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sources import SENTINEL, TABLES  # noqa: E402

YEAR_INDEX = {"2019-20": 2019, "2020-21": 2020, "2021-22": 2021}
TARGETS = {"2024-25": 2024, "2025-26": 2025}


def _fit(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, my
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return slope, my - slope * mx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="Write the projection CSV to outputs/")
    args = ap.parse_args()

    fact = pd.read_parquet(TABLES[0].local_path)
    disc = fact[(fact.discipline != SENTINEL)][["aishe_year", "discipline", "gender", "out_turn"]]
    disc = disc[disc.aishe_year.isin(YEAR_INDEX)]

    rows = []
    for (discipline, gender), g in disc.groupby(["discipline", "gender"]):
        pts = sorted((YEAR_INDEX[y], int(v)) for y, v in zip(g.aishe_year, g.out_turn))
        if len(pts) < 2 or max(v for _, v in pts) == 0:
            continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        slope, intercept = _fit(xs, ys)
        base_year, base_val = xs[-1], ys[-1]
        for label, ti in TARGETS.items():
            est = max(0.0, slope * ti + intercept)
            rows.append({
                "target_year": label, "discipline": discipline, "gender": gender,
                "out_turn_estimate": int(round(est)),
                "base_year": "2021-22", "base_year_value": base_val,
                "growth_pct_total": round((est / base_val - 1) * 100, 1) if base_val else None,
                "method": "OLS on 3 years (2019-22)",
            })
    proj = pd.DataFrame(rows)

    print(f"projection: {len(proj):,} rows ({proj.discipline.nunique()} disciplines × "
          f"{len(TARGETS)} target years × gender)")
    print("\nProjected 2025-26 UG out-turn (Total), top 12:")
    top = (proj[(proj.target_year == "2025-26") & (proj.gender == "Total")]
           .nlargest(12, "out_turn_estimate"))
    for r in top.itertuples(index=False):
        print(f"  {r.discipline:<32} {r.out_turn_estimate:>10,}  ({r.growth_pct_total:+.0f}% vs 2021-22)")

    if args.save:
        out_dir = ROOT / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "discipline_projection_2025_26.csv"
        proj.to_csv(path, index=False)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
