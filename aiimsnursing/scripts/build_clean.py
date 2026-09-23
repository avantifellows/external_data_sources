#!/usr/bin/env python3
"""
Parse the AIIMS B.Sc. (Hons.) Nursing seat-allocation PDFs.

Layout (pdftotext -layout): one line per eligible candidate in overall-rank
order —
    Roll No.  Overall Rank  Category  [PWBD]  Allotted Institute  Allotted Seat Category
    8037319   7330          UR        PWBD    AIIMS JODHPUR       UR-PWBD
    8117863   1             UR                NR/NP               NA
The allotted institute is 'AIIMS <CITY>', 'NR/NP' (did not participate) or
'FCNA' (filled choices not available at that rank). Each PDF ends with the
last rank allotted per category, excluding PwBD and PwBD only; the parse is
checked against it.

Outputs:
  aiimsnursing_fact_allotments  one row per (round, overall_rank); roll
                                numbers are dropped here
  aiimsnursing_fact_cutoffs     opening / closing rank per (round, institute,
                                seat_category) over allotted candidates

Usage:
  python3 scripts/build_clean.py            # parse + write parquet
  python3 scripts/build_clean.py --dry-run  # parse + report only
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, RAW, RAW_FILES, TABLES, YEAR

LINE = re.compile(
    r"^\s*(?P<roll>\d{6,8})\s+(?P<rank>\d+)\s+(?P<cat>UR|EWS|OBC-NCL|OBC|SC|ST)"
    r"(?:\s+(?P<pwbd>PWBD))?\s+(?P<inst>AIIMS [A-Z]+|NR/NP|FCNA)\s+(?P<seat>[A-Z-]+)\s*$")
CANDIDATE = re.compile(r"^\s*\d{6,8}\s+\d+\s")
SUMMARY = re.compile(r"(Excluding PWBD|PWBD Only)\s+(.+)$")
SUMMARY_COLS = ["UR", "OBC", "SC", "ST", "EWS"]
# AIIMS prints the Mangalagiri campus as "MANGLAGIRI" throughout; kept verbatim
INSTITUTES = {"BHATINDA", "BHOPAL", "BHUBANESWAR", "BIBINAGAR", "BILASPUR", "DELHI",
              "DEOGHAR", "GORAKHPUR", "GUWAHATI", "JAMMU", "JODHPUR", "KALYANI",
              "MANGLAGIRI", "NAGPUR", "PATNA", "RAEBARELI", "RAIPUR", "RISHIKESH"}


def fetch_raw() -> None:
    """GCS is canonical; download any raw PDF missing locally."""
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.local_path.relative_to(RAW.parent)} from {rf.gcs_uri}")


def parse(pdf: Path, rnd: int) -> tuple[pd.DataFrame, dict]:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    rows, bad, summary = [], [], {}
    for line in text.splitlines():
        m = LINE.match(line)
        if m:
            inst = m["inst"]
            allotted = inst.startswith("AIIMS ")
            rows.append({
                "year": YEAR, "round": rnd,
                "overall_rank": int(m["rank"]),
                "category": "OBC" if m["cat"] == "OBC-NCL" else m["cat"],
                "pwbd": bool(m["pwbd"]),
                "outcome": "allotted" if allotted else inst,
                "institute": inst if allotted else None,
                "seat_category": m["seat"] if allotted else None,
            })
        elif CANDIDATE.match(line):
            bad.append(line)
        s = SUMMARY.search(line)
        if s:
            vals = s.group(2).split()
            assert len(vals) == 5, line
            summary[s.group(1)] = {c: (None if v == "-" else int(v))
                                   for c, v in zip(SUMMARY_COLS, vals)}
    assert not bad, f"round {rnd}: {len(bad)} unparsed candidate lines, e.g. {bad[:3]}"
    assert set(summary) == {"Excluding PWBD", "PWBD Only"}, f"round {rnd}: summary not found"
    return pd.DataFrame(rows), summary


def check(df: pd.DataFrame, summary: dict, rnd: int) -> None:
    assert df.overall_rank.is_monotonic_increasing and df.overall_rank.is_unique, \
        f"round {rnd}: ranks not strictly increasing"
    a = df[df.outcome == "allotted"]
    bad = set(a.institute.str.removeprefix("AIIMS ")) - INSTITUTES
    assert not bad, f"round {rnd}: unknown institutes {bad}"
    # the PDF's own "last rank allotted" table, per seat category
    for label, pw in [("Excluding PWBD", False), ("PWBD Only", True)]:
        for cat, printed in summary[label].items():
            seat = f"{cat}-PWBD" if pw else cat
            got = a[a.seat_category == seat].overall_rank.max()
            got = None if pd.isna(got) else int(got)
            assert got == printed, f"round {rnd} {seat}: parsed {got}, PDF prints {printed}"


def cutoffs(allot: pd.DataFrame) -> pd.DataFrame:
    a = allot[allot.outcome == "allotted"]
    return (a.groupby(["year", "round", "institute", "seat_category"], as_index=False)
             .agg(opening_rank=("overall_rank", "min"),
                  closing_rank=("overall_rank", "max"),
                  allotted=("overall_rank", "size")))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Parse + report; write nothing")
    args = ap.parse_args()

    fetch_raw()
    frames = []
    for rnd, rf in enumerate(RAW_FILES, start=1):
        df, summary = parse(rf.local_path, rnd)
        check(df, summary, rnd)
        print(f"  round {rnd}: {len(df):,} candidates, {int((df.outcome == 'allotted').sum())} allotted; "
              f"matches the PDF's last-rank table")
        frames.append(df)
    allot = pd.concat(frames, ignore_index=True)
    cut = cutoffs(allot)
    print(f"aiimsnursing_fact_allotments: {len(allot):,} rows")
    print(f"aiimsnursing_fact_cutoffs: {len(cut):,} rows, {cut.institute.nunique()} institutes, "
          f"seat categories {sorted(cut.seat_category.unique())}")
    if args.dry_run:
        return
    CLEAN.mkdir(parents=True, exist_ok=True)
    for t, df in zip(TABLES, [allot, cut]):
        df.to_parquet(t.local_path, index=False)
        print(f"  wrote {t.local_path.relative_to(CLEAN.parent)}")


if __name__ == "__main__":
    main()
