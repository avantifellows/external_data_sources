"""
Q3 (equity): out-turn by DISCIPLINE × social category.

AISHE does not publish a discipline × social-category cut. This rolls the
programme × social-category slice of aishe_fact_outturn (Table 34a) up to
discipline level using the heuristic programme→discipline codemap
(codemaps/programme_to_discipline.csv).

Derived, not a base table. Degree-name based: it CANNOT recover subject-based
disciplines (Indian Language, Social Science, Foreign Language, …) — those
students sit in B.A./M.A./B.Sc. programmes and roll up to Arts/Science, which
are therefore over-counted. Reliable for disciplines served by named degrees
(Engineering & Technology, Medical Science, Law, Management, Education,
Commerce, IT & Computer, …).

Source: clean/outturn.parquet (programme cut) + codemaps/programme_to_discipline.csv
Output: prints; writes analyses/out/discipline_social_category.csv if --save.

Usage:
  python3 analyses/rollup_discipline_social_category.py [--save]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sources import CODEMAPS, SENTINEL, TABLES  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="Write the rollup CSV to analyses/out/")
    args = ap.parse_args()

    fact = pd.read_parquet(TABLES[0].local_path)
    prog = fact[fact.programme != SENTINEL][["programme", "social_category", "gender", "out_turn"]]
    cmap = pd.read_csv(CODEMAPS / "programme_to_discipline.csv", dtype=str)[["programme", "discipline"]]

    merged = prog.merge(cmap, on="programme", how="left")
    merged["discipline"] = merged["discipline"].fillna("Others")
    rollup = (merged.groupby(["discipline", "social_category", "gender"], as_index=False)
                    .out_turn.sum())

    unmapped = sorted(set(prog.programme) - set(cmap.programme))
    print(f"discipline × social-category rollup: {len(rollup):,} rows, "
          f"{rollup.discipline.nunique()} disciplines")
    if unmapped:
        print(f"  {len(unmapped)} programmes had no codemap entry → 'Others'")
    print("\nAll-Categories / Total out-turn by discipline (top 12):")
    top = (rollup[(rollup.social_category == "All Categories") & (rollup.gender == "Total")]
           .nlargest(12, "out_turn"))
    for r in top.itertuples(index=False):
        print(f"  {r.discipline:<32} {r.out_turn:>10,}")

    if args.save:
        out_dir = ROOT / "analyses" / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "discipline_social_category.csv"
        rollup.to_csv(path, index=False)
        print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
