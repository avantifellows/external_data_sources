#!/usr/bin/env python3
"""
Parse the 3 DU CUET UG-2025 round PDFs and build the clean fact table.

Each round PDF is the University's minimum-allocation-score table for that
round only — rounds are NOT cumulative, and a later round can quote a LOWER
score than an earlier one for the same (college, program, category) as seats
are reallocated. So "the cutoff after N rounds" is the MIN across rounds
actually published for that cell, not the latest round's value and not the
lowest ever offered (a category can be blank in a round, meaning no seat was
open in that category that round — not a zero).

Round 1 / Round 3 PDFs share one 6-category layout: UR, OBC, SC, ST, EWS,
PwBD. Round 2 additionally reports SIKH, KM, SGC, and ORPHAN (Female/Male) —
those extra columns are parsed but dropped from this fact, which is scoped to
the 6 categories common to all three rounds (see schemas/README.md).

Program identity is matched on (college, program) normalized (lowercased,
periods stripped, whitespace collapsed) because Round 2's PDF consistently
spells programs with a trailing period DU's other two PDFs omit (e.g.
"B.Sc. (Hons.) Botany" vs "B.Sc (Hons.) Botany") — same seat, different
typesetting. 124 program rows (all from Round 2) have NO Round-1 counterpart even
after normalizing — these are "BA Program" combination-subject seats that
didn't exist, or were labelled differently enough, in Round 1 (DU opens/edits
some combination seats between rounds). They are kept as their own rows
rather than dropped or fuzzy-matched onto a similarly-named-but-different
combination, since a fuzzy match here would silently attribute one seat's
cutoff to a different subject pairing.

Usage:
  python3 scripts/build_clean.py --dry-run     # parse + validate, don't write
  python3 scripts/build_clean.py               # write clean/ducuet_fact_cutoffs.parquet
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, ROUNDS, TABLES

CATEGORIES = ["UR", "OBC", "SC", "ST", "EWS", "PwBD"]


def _clean_cell(v: str | None) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", v).strip()


def _normalize_key(college: str, program: str) -> tuple[str, str]:
    def norm(s: str) -> str:
        s = s.lower().replace(".", "")
        return re.sub(r"\s+", " ", s).strip()

    return norm(college), norm(program)


def _to_float(s: str) -> float | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_round_1_3(path: Path) -> list[dict]:
    """Round 1 / Round 3 layout: every real column is padded with 2 blank
    merged-cell columns (S.NO, ., ., COLLEGE, ., ., PROGRAM, ., ., UR, ., ., ...).
    A row whose S.NO cell is blank and whose program cell is non-blank is the
    tail of a program name that wrapped across a page break (DU's table
    sometimes splits a long combination-subject name mid-cell at the page
    boundary) — glue it onto the previous row's program name."""
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if row[1] == "S.NO." or (len(row) > 4 and row[4] == "COLLEGE NAME"):
                        continue
                    sno = _clean_cell(row[0])
                    college = _clean_cell(row[3])
                    program = _clean_cell(row[6])
                    if not sno or not sno.isdigit():
                        if program and not college and rows:
                            rows[-1]["program"] = (rows[-1]["program"] + " " + program).strip()
                        continue
                    rows.append(
                        {
                            "college": college,
                            "program": program,
                            "UR": _clean_cell(row[9]),
                            "OBC": _clean_cell(row[12]),
                            "SC": _clean_cell(row[15]),
                            "ST": _clean_cell(row[18]),
                            "EWS": _clean_cell(row[21]),
                            "PwBD": _clean_cell(row[24]) if len(row) > 24 else "",
                        }
                    )
    return rows


def parse_round_2(path: Path) -> list[dict]:
    """Round 2 layout: no blank-column padding, but more category columns
    (UR, OBC-NCL, SC, ST, EWS, SIKH, PwBD, KM, SGC, ORPHAN-F, ORPHAN-M) at
    fixed indices 3/4/7/8/9/10/11/12/13/15/18 verified against the header AND
    several data pages (see build notes) — only the 6 categories shared with
    Round 1/3 are kept here. Same page-break program-name continuation as
    Round 1/3, at the row shape ('', '', <tail text>, ...)."""
    rows: list[dict] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    if row[0] in ("S.NO.", None) and row[1] in ("COLLEGE NAME", None):
                        continue
                    sno = _clean_cell(row[0])
                    college = _clean_cell(row[1])
                    program = _clean_cell(row[2])
                    if not sno or not sno.isdigit():
                        if program and not college and rows:
                            rows[-1]["program"] = (rows[-1]["program"] + " " + program).strip()
                        continue
                    rows.append(
                        {
                            "college": college,
                            "program": program,
                            "UR": _clean_cell(row[3]),
                            "OBC": _clean_cell(row[4]),
                            "SC": _clean_cell(row[7]),
                            "ST": _clean_cell(row[8]),
                            "EWS": _clean_cell(row[9]),
                            "PwBD": _clean_cell(row[11]),
                        }
                    )
    return rows


PARSERS = {1: parse_round_1_3, 2: parse_round_2, 3: parse_round_1_3}


def build_df() -> pd.DataFrame:
    merged: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []

    for round_no, path in sorted(ROUNDS.items()):
        if not path.exists():
            raise SystemExit(f"missing raw PDF for round {round_no}: {path}")
        for row in PARSERS[round_no](path):
            key = _normalize_key(row["college"], row["program"])
            if key not in merged:
                merged[key] = {
                    "college_name": row["college"],
                    "program_name": row["program"],
                    "min_scores": {c: None for c in CATEGORIES},
                    "rounds_seen": set(),
                }
                order.append(key)
            entry = merged[key]
            entry["rounds_seen"].add(round_no)
            for cat in CATEGORIES:
                val = _to_float(row[cat])
                if val is None:
                    continue
                cur = entry["min_scores"][cat]
                entry["min_scores"][cat] = val if cur is None else min(cur, val)

    records = []
    for key in order:
        e = merged[key]
        for cat in CATEGORIES:
            score = e["min_scores"][cat]
            if score is None:
                continue
            records.append(
                {
                    "college_name": e["college_name"],
                    "program_name": e["program_name"],
                    "category": cat,
                    "min_allocation_score": score,
                    "rounds_published": ",".join(str(r) for r in sorted(e["rounds_seen"])),
                }
            )
    df = pd.DataFrame.from_records(records)
    return df


def validate(df: pd.DataFrame) -> None:
    dupe_grain = df.duplicated(subset=["college_name", "program_name", "category"]).sum()
    assert dupe_grain == 0, f"{dupe_grain} duplicate (college_name, program_name, category) rows"
    assert df["min_allocation_score"].notna().all(), "found null scores after filtering"
    assert set(df["category"]) <= set(CATEGORIES), f"unexpected category values: {set(df['category']) - set(CATEGORIES)}"
    n_programs = df.drop_duplicates(["college_name", "program_name"]).shape[0]
    print(f"  {len(df):,} rows, {n_programs:,} distinct (college, program) pairs, {df['college_name'].nunique():,} colleges")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Parse + validate; don't write parquet")
    args = ap.parse_args()

    print("Parsing 3 round PDFs and taking the min per (college, program, category)...")
    df = build_df()
    validate(df)

    table = TABLES[0]
    if args.dry_run:
        print(f"  [dry-run] would write {table.local_path}")
        return

    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(table.local_path, index=False)
    print(f"✓ wrote {table.local_path} ({len(df):,} rows)")


if __name__ == "__main__":
    main()
