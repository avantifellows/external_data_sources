"""
Merge the two board-results parsers into the single denormalized fact
(clean/board_results.parquet → BQ board_results_fact_passes).

One grain, with the sentinel "All Categories" / "All Streams" for cells a cut
doesn't break out (the values AISHE/MoE already use):

  Class X overall   (Table 3/1, Sec A)  → level="Class X",  social_category="All Categories", stream="All Streams"
  Class XII overall (Table 3/1, Sec B)  → level="Class XII", social_category="All Categories", stream="All Streams"
  Class XII stream  (Tables 13/15/17 or 31/33/35) → level="Class XII", social_category, stream  (passed only)

Grain: (year, level, state, board, social_category, stream, gender) → passed
Extra measures registered / appeared / pass_percentage are populated only on the
overall (All-Categories, All-Streams) rows; NULL on the stream/category
breakdowns (the source only publishes pass counts there).

The Class XII (All Categories, All Streams) total comes from the overall table
(richer measures); the duplicate row from the stream table is dropped.

Usage:
  python3 scripts/clean_board_results.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_overall import build_df as build_overall_df
from parse_class_xii_stream import build_df as build_stream_df
from sources import TABLES

COLUMNS = ["year", "level", "state", "board", "social_category", "stream",
           "gender", "registered", "appeared", "passed", "pass_percentage"]


def main() -> None:
    # ── overall (Class X + XII): All Categories × All Streams, full measures ──
    overall = build_overall_df().rename(columns={"passed_annual_and_supp": "passed"})
    overall["social_category"] = "All Categories"
    overall["stream"] = "All Streams"

    # ── stream (Class XII): SC/ST + per-stream breakdowns, passed only ──
    stream = build_stream_df().rename(columns={"students_passed": "passed"})
    stream["level"] = "Class XII"
    stream["registered"] = pd.NA
    stream["appeared"] = pd.NA
    stream["pass_percentage"] = pd.NA
    # Drop the (All Categories, All Streams) rows — the overall table owns that
    # cell (with registered/appeared/pass%); keep only the breakdowns here.
    stream = stream[~((stream.social_category == "All Categories")
                      & (stream.stream == "All Streams"))]

    fact = pd.concat([overall[COLUMNS], stream[COLUMNS]], ignore_index=True)

    grain = ["year", "level", "state", "board", "social_category", "stream", "gender"]
    # Drop misparsed rows whose board is a bare number (S.No. fragments from the
    # fragile 2020/2021 stream layout), then de-duplicate identical rows a stream
    # table can yield twice across PDF pages. (The overall parser already dedups;
    # the stream parser doesn't, so the grain must be enforced here.)
    before = len(fact)
    fact = fact[~fact.board.astype(str).str.fullmatch(r"\d+")]
    fact = fact.drop_duplicates(grain, keep="first").reset_index(drop=True)
    if before != len(fact):
        print(f"  cleaned {before - len(fact):,} junk/duplicate-grain rows")

    for col in ["year", "registered", "appeared", "passed"]:
        fact[col] = fact[col].astype("Int64")
    # nullable float — pass_percentage is NA on the stream/category breakdown rows
    fact["pass_percentage"] = pd.to_numeric(fact["pass_percentage"], errors="coerce").astype("Float64")

    out = TABLES[0].local_path
    out.parent.mkdir(parents=True, exist_ok=True)
    fact.to_parquet(out, index=False, engine="pyarrow")

    print(f"\nboard_results → {out.name}: {len(fact):,} rows")
    # Validation: 2024 Class XII all-India passed (All Cat / All Streams / Total).
    v = fact[(fact.year == 2024) & (fact.level == "Class XII")
             & (fact.social_category == "All Categories") & (fact.stream == "All Streams")
             & (fact.gender == "Total")].passed.sum()
    print(f"  2024 Class XII total passed (sum of boards) = {v:,}  "
          f"{'OK' if v == 12929386 else 'CHECK (expect 12,929,386)'}")


if __name__ == "__main__":
    main()
