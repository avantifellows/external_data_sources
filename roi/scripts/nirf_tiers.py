#!/usr/bin/env python3
"""
nirf_tiers.py — top-college placement rates + salaries, by NIRF tier.

Source: avantifellows.external_data_sources.nirf_fact_aggregate.

Year: ranking_year 2022 — the most recent NIRF cycle that ranked the full
**top 200** engineering institutes (2023-25 rank only the top 100). One institute
carries several rows (per academic_year, per programme); we dedupe to the latest
academic_year per institute and take that institute's reported median salary,
graduating-on-time count, and students-placed count.

Tiers are the NIRF top-college layer defined in taxonomy.py:
    IIT / NIT / IIIT / Other NIRF Top-200 Eng    (Engineering, by institute name)
    Top NIRF Medical & Dental                    (Medical + Dental merged)
    Top NIRF Architecture & Planning
    Top NIRF Law
    Top NIRF Pharmacy
(Management is ranked but reports no salary in 2022, so it is absent.)

Per tier: institute count, placement rate (placed / graduating), and a
graduate-weighted mean of institute median salaries.

Output: roi/clean/nirf_tiers.csv
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

import taxonomy

OUT = Path(__file__).resolve().parent.parent / "clean" / "nirf_tiers.csv"
RANKING_YEAR = 2022

# institute-level dedup (latest academic_year) for the ranked disciplines we use
SQL = f"""
SELECT ranking_category,
       ANY_VALUE(institute_name) AS institute_name,
       ARRAY_AGG(median_salary      ORDER BY academic_year DESC, median_salary DESC LIMIT 1)[OFFSET(0)] AS median_salary,
       ARRAY_AGG(graduating_on_time ORDER BY academic_year DESC, graduating_on_time DESC LIMIT 1)[OFFSET(0)] AS grads,
       ARRAY_AGG(students_placed    ORDER BY academic_year DESC, students_placed DESC LIMIT 1)[OFFSET(0)] AS placed
FROM `avantifellows.external_data_sources.nirf_fact_aggregate`
WHERE ranking_year = {RANKING_YEAR}
  AND median_salary > 0 AND graduating_on_time > 0
  AND ranking_category IN ('Engineering','Medical','Dental','Law','Pharmacy',
                           'Architecture','Architecture and Planning')
GROUP BY ranking_category, institute_id
"""


def query() -> list[dict]:
    # --max_rows: bq defaults to 100 displayed rows; this pull is one row per
    # institute (~400), so raise the cap or the result is silently truncated.
    proc = subprocess.run(
        ["bq", "query", "--use_legacy_sql=false", "--format=csv",
         "--max_rows=100000", "--quiet=true", SQL],
        capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.exit(f"bq error:\n{proc.stderr}")
    return list(csv.DictReader(io.StringIO(proc.stdout)))


def main() -> None:
    institutes = query()

    # accumulate per NIRF tier
    agg: dict[str, dict] = {}
    for r in institutes:
        tier = taxonomy.nirf_tier(r["ranking_category"], r["institute_name"])
        if tier is None:
            continue
        grads = float(r["grads"])
        sal = float(r["median_salary"])
        a = agg.setdefault(tier, {"n": 0, "grads": 0.0, "sal_x_grads": 0.0,
                                  "placed": 0.0, "grads_placed": 0.0})
        a["n"] += 1
        a["grads"] += grads
        a["sal_x_grads"] += sal * grads
        # placement rate only over institutes that report a placed count
        if r["placed"] not in ("", None):
            a["placed"] += float(r["placed"])
            a["grads_placed"] += grads

    rows = []
    for tier in taxonomy.NIRF_TIERS:
        a = agg.get(tier)
        if not a:
            continue
        rate = (round(100 * a["placed"] / a["grads_placed"], 1)
                if a["grads_placed"] else None)
        rows.append({
            "tier": tier,
            "common_field": taxonomy.NIRF_TIER_TO_FIELD[tier],
            "ranking_year": RANKING_YEAR,
            "n_institutes": a["n"],
            "annual_grads": int(a["grads"]),
            "annual_placed": int(a["placed"]),
            "placement_rate_pct": rate,
            "grad_wtd_median_salary": round(a["sal_x_grads"] / a["grads"]),
        })

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    print(f"NIRF {RANKING_YEAR} top-college tiers (grad-weighted) → {OUT.name}\n")
    print(f'{"NIRF tier":<30} {"field":<12} {"inst":>5} {"grads":>7} '
          f'{"placed%":>8} {"median":>8}')
    print("-" * 76)
    for r in rows:
        print(f'{r["tier"]:<30} {r["common_field"]:<12} {r["n_institutes"]:>5} '
              f'{r["annual_grads"]:>7,} {r["placement_rate_pct"]:>7.1f}% '
              f'₹{r["grad_wtd_median_salary"]/1e5:>5.1f}L')


if __name__ == "__main__":
    main()
