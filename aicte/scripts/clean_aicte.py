"""
Unify the three AICTE dashboard panels into one wide fact, written to
clean/intake.parquet.

The AICTE dashboard exposes the same intake/enrolment/passout/placement series
sliced three ways (national, by state, by institution-type). Following the
repo's denormalize-to-one-wide-fact convention (cf. board_results), we merge all
three cuts onto a single grain and fill the dimensions a cut doesn't break out
with an "All" sentinel — one fact, not three tables.

Output (BQ: aicte_fact_intake), one row per
  (year, program, level, state, institution_type)
→ approved_intake, enrolled, passed, placed, institutions, girls, boys, faculties

  - National rows:  state="All", institution_type="All"  (faculties populated here)
  - State rows:     institution_type="All"               (faculties NULL)
  - Inst-type rows: state="All"                           (faculties NULL)

So the national totals are the rows where state="All" AND institution_type="All".
**Query by filtering to one slice — don't SUM across the "All"-sentinel rows and
the broken-out rows, which would double-count.**

Usage:
  python3 scripts/clean_aicte.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, PANEL_INST_TYPE, PANEL_NATIONAL, PANEL_STATE, TABLES

# Final column order (BQ schema order).
DIMS = ["cut", "year", "program", "level", "state", "institution_type"]
INT_MEASURES = [
    "approved_intake", "enrolled", "passed", "placed",
    "institutions", "girls", "boys", "faculties",
]
COLUMNS = DIMS + INT_MEASURES

SENTINEL = "All"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"missing panel CSV: {path}\nRun scripts/fetch.py first.")
    return pd.read_csv(path, dtype=str)


def build_df() -> pd.DataFrame:
    national = _read(PANEL_NATIONAL)
    national["cut"] = "national"
    national["state"] = SENTINEL
    national["institution_type"] = SENTINEL

    state = _read(PANEL_STATE)
    state["cut"] = "state"
    state["institution_type"] = SENTINEL
    state["faculties"] = pd.NA

    inst = _read(PANEL_INST_TYPE)
    inst["cut"] = "inst_type"
    inst["state"] = SENTINEL
    inst["faculties"] = pd.NA

    df = pd.concat([national, state, inst], ignore_index=True)
    df = df.reindex(columns=COLUMNS)

    for c in INT_MEASURES:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    return df


def main() -> None:
    df = build_df()
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = TABLES[0].local_path
    df.to_parquet(out, index=False, engine="pyarrow")

    nat = df[(df.state == SENTINEL) & (df.institution_type == SENTINEL)]
    print(f"aicte_fact_intake: {len(df):,} rows → {out.name}")
    print(f"  national rows (state=All, institution_type=All): {len(nat):,}")
    print(f"  years={df.year.nunique()}  programs={df.program.nunique()}  "
          f"levels={df.level.nunique()}  states={df.state.nunique() - 1}  "
          f"institution_types={df.institution_type.nunique() - 1}")


if __name__ == "__main__":
    main()
