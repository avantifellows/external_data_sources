#!/usr/bin/env python3
"""
aishe_grads.py — annual UG graduate universe, on the common field taxonomy.

Source: AISHE UG out-turn (graduates) by discipline, extrapolated to 2024-25
(`aishe/clean/ug_discipline_extrapolated.parquet`, metric='out_turn',
gender='Total'; linear fit 2019-22, base 2021-22).

Disciplines are folded into the nine common fields defined in `taxonomy.py`
(the shared AISHE↔PLFS language): Engineering, Medical, Other Technical,
IT & Computer, Science, Commerce, Management, Law, Other. STEM = the first five.

AISHE is the denominator that sizes each tier's share of all STEM / all UG.

Output: roi/clean/aishe_grads.csv — one row per discipline (out-turn + common
field) plus rollup rows (per-field totals, STEM total, all-UG total). The
`__STEM_UG__` / `__ALL_UG__` rollups are what the wage-curve step reads.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import pandas as pd

import taxonomy   # shared field crosswalk

HERE = Path(__file__).resolve()
SRC = HERE.parents[2] / "aishe" / "clean" / "ug_discipline_extrapolated.parquet"
OUT = HERE.parents[1] / "clean" / "aishe_grads.csv"
TARGET_YEAR = "2024-25"


def main() -> None:
    if not SRC.exists():
        sys.exit(f"AISHE extrapolated parquet not found: {SRC}")
    df = pd.read_parquet(SRC)
    ut = df[(df["metric"] == "out_turn")
            & (df["target_year"] == TARGET_YEAR)
            & (df["gender"] == "Total")].copy()
    if ut.empty:
        sys.exit(f"No out_turn rows for {TARGET_YEAR}.")

    ut["ug_outturn"] = ut["value_estimate"].round().astype(int)
    ut["field"] = ut["discipline"].map(taxonomy.aishe_field)
    ut = ut.sort_values("ug_outturn", ascending=False)

    by_field = ut.groupby("field")["ug_outturn"].sum().to_dict()
    all_ug = int(ut["ug_outturn"].sum())
    stem_ug = int(sum(by_field.get(f, 0) for f in taxonomy.STEM_FIELDS))

    rows = [{
        "discipline": r["discipline"],
        "ug_outturn_2024_25": int(r["ug_outturn"]),
        "field": r["field"],
    } for _, r in ut.iterrows()]

    rollups = [{"discipline": f"__FIELD_{f.upper().replace(' & ', '_').replace(' ', '_')}__",
                "ug_outturn_2024_25": int(by_field.get(f, 0)), "field": f}
               for f in taxonomy.COMMON_FIELDS]
    rollups += [
        {"discipline": "__STEM_UG__", "ug_outturn_2024_25": stem_ug, "field": "total_stem"},
        {"discipline": "__ALL_UG__", "ug_outturn_2024_25": all_ug, "field": "total_all"},
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=["discipline", "ug_outturn_2024_25", "field"])
        wtr.writeheader()
        wtr.writerows(rows + rollups)

    print(f"AISHE UG graduates {TARGET_YEAR}, common field taxonomy → {OUT.name}\n")
    print(f'{"Field":<18} {"UG grads/yr":>13} {"% all UG":>9}  {"→ PLFS wage cell":<16}')
    print("-" * 62)
    for fld in taxonomy.COMMON_FIELDS:
        v = by_field.get(fld, 0)
        stem = " STEM" if fld in taxonomy.STEM_FIELDS else ""
        print(f'{fld:<18} {v:>13,} {100*v/all_ug:>8.1f}%  '
              f'{taxonomy.plfs_field(fld):<16}{stem}')
    print("-" * 62)
    print(f'{"STEM total":<18} {stem_ug:>13,} {100*stem_ug/all_ug:>8.1f}%')
    print(f'{"All UG total":<18} {all_ug:>13,} {100.0:>8.1f}%')


if __name__ == "__main__":
    main()
