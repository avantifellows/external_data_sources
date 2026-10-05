#!/usr/bin/env python3
"""
Build allahabadug_fact_cutoffs from the University of Allahabad's 2025-26
UG cut-off notices.

One row per (year, programme, round, category, notice): the CUET-UG
computed marks printed for that category in that round. `cutoff` is the
low end of a printed range ("362 - 371" is the band admitted that round),
the number of "378 & Above", or NULL with all_admitted = TRUE when the
notice prints "All" / "Last Candidate".

Sources (sources.RAW_FILES): role 'text' notices are parsed
(parse_notices.py); role 'manual' notices come from the reviewed
transcription extracted/manual_transcriptions.csv (scanned pages, and
B.P.A. notices that print a round per category).

Rounds: the printed ordinal; B.Sc. (Maths) notices print none and are
numbered by notice date. Year: from "CUET-UG-20xx" in each notice, per row
(the 2026 cycle's first notices sit on the same index pages).

Quality gates (the build fails on any):
  - every 'text' notice yields rows, and names a programme and a year
  - no duplicate (year, programme, round, category, file)
  - every cutoff between 0 and 750 (three papers of 250)
  - within a programme and category, cutoffs never rise from one round to
    the next by more than a printed range allows (a parse slip shows up as
    a jump)

Usage:
  python3 scripts/build_clean.py            # build + write parquet
  python3 scripts/build_clean.py --dry-run  # build + report only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_notices import parse
from sources import (CLEAN, GCS_BUCKET, MANUAL, MANUAL_GCS, RAW, RAW_FILES,
                     TABLES)

# notice -> year, where the notice misprints it (none so far). Note:
# "DisasterEnvironmentalStudies--Notice_3rd.pdf" prints 2026-27 and IS a
# 2026 notice (the 2026 cycle's pages share the 2025 index): its OBC / SC /
# ST cut-offs sit above 2025's 2nd round, which a later 2025 round can't do.
YEAR_FIX: dict[str, int] = {}
# programmes whose notices print no round number: numbered by notice date
ROUND_BY_DATE = {"B.Sc. (Maths)"}
MAX_SCORE = 750


def fetch_raw() -> None:
    """GCS is canonical; download any raw file missing locally."""
    need = [(rf.local_path, rf.gcs_path) for rf in RAW_FILES if not rf.local_path.exists()]
    if not MANUAL.exists():
        need.append((MANUAL, MANUAL_GCS))
    if not need:
        return
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_BUCKET)
    for local, path in need:
        local.parent.mkdir(parents=True, exist_ok=True)
        bucket.blob(path).download_to_filename(str(local))
        print(f"  fetched {local.name} from gs://{GCS_BUCKET}/{path}")


def from_text() -> pd.DataFrame:
    rows = []
    for rf in RAW_FILES:
        if rf.role != "text":
            continue
        p = parse(rf.local_path)
        year = YEAR_FIX.get(rf.name, p["year"])
        if not p["program"] or not year or not p["rows"]:
            raise SystemExit(f"{rf.name}: programme {p['program']!r}, year {year}, "
                             f"{len(p['rows'])} rows — fix the parser or move it to manual")
        for r in p["rows"]:
            rows.append({"year": year, "program": p["program"],
                         "round_printed": p["round_printed"], "notice_date": p["date"],
                         "category": r["category"], "category_raw": r["category"],
                         "cutoff": r["low"], "cutoff_high": r["high"],
                         "all_admitted": r["all"], "source_file": rf.name,
                         "extraction": "text"})
    df = pd.DataFrame(rows)
    # B.Sc. (Maths): no printed round; number the notices by date
    for prog in ROUND_BY_DATE:
        m = df.program == prog
        dates = sorted(df.loc[m, "notice_date"].unique())
        assert all(dates), f"{prog}: a notice without a date"
        df.loc[m, "round_printed"] = df.loc[m, "notice_date"].map({d: i + 1 for i, d in enumerate(dates)})
    missing = df[df.round_printed.isna()]
    if len(missing):
        raise SystemExit("notices without a round:\n" + missing.source_file.drop_duplicates().to_string())
    return df.rename(columns={"round_printed": "round"})


def from_manual() -> pd.DataFrame:
    m = pd.read_csv(MANUAL)
    manual_files = {rf.name for rf in RAW_FILES if rf.role == "manual"}
    assert set(m.file) == manual_files, (set(m.file) ^ manual_files)
    m["notice_date"] = pd.to_datetime(m.notice_date).dt.date
    m["all_admitted"] = m.all_admitted.astype(str).str.lower() == "true"
    return m.rename(columns={"file": "source_file", "cutoff_low": "cutoff"}).assign(extraction="manual")[
        ["year", "program", "round", "notice_date", "category", "category_raw",
         "cutoff", "cutoff_high", "all_admitted", "source_file", "extraction"]]


def check(df: pd.DataFrame) -> None:
    key = ["year", "program", "round", "category", "source_file"]
    dup = df[df.duplicated(key, keep=False)]
    assert dup.empty, f"duplicate rows:\n{dup}"
    bad = df[(df.cutoff < 0) | (df.cutoff > MAX_SCORE)]
    assert bad.empty, f"cutoffs outside 0-{MAX_SCORE}:\n{bad}"
    # a later round's cut-off sits at or below the earlier one, give or take
    # the band an earlier range printed
    jumps = []
    for (_, prog, cat), g in df[df.cutoff.notna()].groupby(["year", "program", "category"]):
        g = g.sort_values(["round", "notice_date"])
        prev = None
        for r in g.itertuples():
            if prev is not None and r.cutoff > (prev.cutoff_high if pd.notna(prev.cutoff_high) else prev.cutoff) + 0.01:
                jumps.append((prog, cat, prev.round, prev.cutoff, r.round, r.cutoff, r.source_file))
            prev = r
    if jumps:
        print("  cut-offs that rise round to round (review):")
        for j in jumps:
            print("   ", j)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fetch_raw()
    df = pd.concat([from_text(), from_manual()], ignore_index=True)
    df["round"] = df["round"].astype(int)
    df["year"] = df["year"].astype(int)
    check(df)
    df = df.sort_values(["year", "program", "round", "category"]).reset_index(drop=True)
    print(f"allahabadug_fact_cutoffs: {len(df)} rows from {df.source_file.nunique()} notices")
    print(df.groupby("program").agg(rounds=("round", "max"), rows=("round", "size"),
                                    manual=("extraction", lambda s: (s == "manual").sum())).to_string())
    if args.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(TABLES[0].local_path, index=False)
    print(f"✓ wrote {TABLES[0].local_path}")


if __name__ == "__main__":
    main()
