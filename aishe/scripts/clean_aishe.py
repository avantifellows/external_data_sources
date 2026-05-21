"""
Parse the AISHE Final Report workbooks in raw/ into the single denormalized
out-turn fact (clean/outturn.parquet → BQ aishe_fact_outturn).

The fact unifies three published cuts into one grain, using the sentinel "All"
for dimensions a given cut doesn't break out:

  Table 33  state × level             → (year, level, state, "All","All","All", gender)
  Table 34a programme × social cat    → (year, "All","All","All", programme, social_category, gender)
  Table 35  UG discipline (3 years)   → (year, "Under Graduate","All", discipline, "All","All", gender)

Grain: (aishe_year, level, state, discipline, programme, social_category, gender) → out_turn

Query by filtering to one slice; never SUM across rows of different grain.
See analysis/README.md for the questions and worked slices.

Usage:
  python3 scripts/clean_aishe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, OUTTURN_YEAR, REPORTS, SENTINEL, TABLES

COLUMNS = ["aishe_year", "level", "state", "discipline", "programme",
           "social_category", "gender", "out_turn"]

LEVELS = [
    "Ph.D.", "M.Phil.", "Post Graduate", "Under Graduate",
    "PG Diploma", "Diploma", "Certificate", "Integrated",
]
GENDERS = ["Male", "Female", "Total"]
SOCIAL_CATEGORIES = [
    "All Categories", "Scheduled Caste", "Scheduled Tribe",
    "Other Backward Classes", "Persons with Disability", "Muslim",
    "Other Minority Communities", "EWS",
]


def _wb(year: str):
    path = REPORTS[year]
    if not path.exists():
        raise SystemExit(
            f"missing raw workbook: {path}\n"
            f"Download the AISHE {year} Final Report and place it there (see README)."
        )
    return openpyxl.load_workbook(path, data_only=True)


def _sheet(wb, *names):
    want = {n.replace(" ", "").lower() for n in names}
    for s in wb.sheetnames:
        if s.replace(" ", "").lower() in want:
            return wb[s]
    raise SystemExit(f"no sheet matching {names} (have: {wb.sheetnames})")


def _row(year, level, state, discipline, programme, social_category, gender, out_turn):
    return {
        "aishe_year": year, "level": level, "state": state,
        "discipline": discipline, "programme": programme,
        "social_category": social_category, "gender": gender,
        "out_turn": int(out_turn) if isinstance(out_turn, (int, float)) else 0,
    }


# ─── Table 33: state × level (2021-22) ────────────────────────────────────────
def state_level_rows(wb) -> list[dict]:
    ws = _sheet(wb, "33OutTurnState")
    out = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        state = row[1]
        if state is None or not str(state).strip():
            continue
        state = str(state).strip()
        if state.lower() in {"all india", "india", "total"}:
            continue
        for li, level in enumerate(LEVELS):
            for gi, gender in enumerate(GENDERS):
                out.append(_row(OUTTURN_YEAR, level, state, SENTINEL, SENTINEL,
                                SENTINEL, gender, row[2 + li * 3 + gi]))
    return out


# ─── Table 34a: programme × social category (2021-22, national, all levels) ───
def programme_social_rows(wb) -> list[dict]:
    ws = _sheet(wb, "34a")
    out = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        prog = row[1]
        if prog is None or not str(prog).strip():
            continue
        prog = str(prog).strip()
        for ci, cat in enumerate(SOCIAL_CATEGORIES):
            for gi, gender in enumerate(GENDERS):
                idx = 2 + ci * 3 + gi
                val = row[idx] if idx < len(row) else None
                out.append(_row(OUTTURN_YEAR, SENTINEL, SENTINEL, SENTINEL,
                                prog, cat, gender, val))
    return out


# ─── Table 35: UG out-turn by discipline (2019-20 → 2021-22, the trend) ───────
def _discipline_series(ws, year) -> list[dict]:
    """35UGDisc layout shifts across years (S.No. column added in 2021-22)."""
    schema = None
    for ri in range(1, 6):
        cells = [str(c.value).strip() if c.value is not None else "" for c in ws[ri]]
        if cells and cells[0] == "Discipline":
            schema = "old"
            break
        if len(cells) >= 2 and cells[1] == "Discipline":
            schema = "new"
            break
    if schema is None:
        raise SystemExit(f"could not detect schema in sheet {ws.title!r}")
    if schema == "old":
        col_disc, col_subj, col_m, col_f, col_t = 0, 1, 2, 3, 4
    else:
        col_disc, col_subj, col_m, col_f, col_t = 1, 2, 3, 4, 5

    out = []
    for r in ws.iter_rows(min_row=4, values_only=True):
        if not r or len(r) <= col_t:
            continue
        disc, subj, male, female, total = r[col_disc], r[col_subj], r[col_m], r[col_f], r[col_t]
        if disc is None or not str(disc).strip():
            continue
        disc_s = str(disc).strip()
        if disc_s.isdigit():
            continue
        is_total = (subj is None or str(subj).strip() == "") or disc_s.endswith("Total")
        if not is_total:
            continue
        clean = disc_s[:-len("Total")].strip() if disc_s.endswith("Total") else disc_s
        if not clean or not isinstance(total, (int, float)):
            continue
        for gender, val in (("Male", male), ("Female", female), ("Total", total)):
            out.append(_row(year, "Under Graduate", SENTINEL, clean, SENTINEL,
                            SENTINEL, gender, val))
    return out


def discipline_rows() -> list[dict]:
    out = []
    for year in REPORTS:
        out += _discipline_series(_sheet(_wb(year), "35UGDisc"), year)
    return out


def main() -> None:
    wb2122 = _wb(OUTTURN_YEAR)
    rows = state_level_rows(wb2122) + programme_social_rows(wb2122) + discipline_rows()
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["out_turn"] = df["out_turn"].astype("Int64")

    CLEAN.mkdir(parents=True, exist_ok=True)
    out = TABLES[0].local_path
    df.to_parquet(out, index=False, engine="pyarrow")

    print(f"AISHE → {out.name}: {len(df):,} rows")
    cuts = {
        "state × level (Table 33)": (df.state != SENTINEL).sum(),
        "programme × social (Table 34a)": (df.programme != SENTINEL).sum(),
        "UG discipline (Table 35, 3 yrs)": (df.discipline != SENTINEL).sum(),
    }
    for k, v in cuts.items():
        print(f"  {k:<34} {v:>6,} rows")
    # Validation: 2021-22 UG out-turn reconciles across the state and discipline cuts.
    ug_state = df[(df.aishe_year == OUTTURN_YEAR) & (df.level == "Under Graduate")
                  & (df.state != SENTINEL) & (df.gender == "Total")].out_turn.sum()
    ug_disc = df[(df.aishe_year == OUTTURN_YEAR) & (df.discipline != SENTINEL)
                 & (df.gender == "Total")].out_turn.sum()
    print(f"  2021-22 UG out-turn: state-cut={ug_state:,}  discipline-cut={ug_disc:,}  "
          f"{'OK' if ug_state == ug_disc == 7754223 else 'CHECK'}")
    print("✓ done.")


if __name__ == "__main__":
    main()
