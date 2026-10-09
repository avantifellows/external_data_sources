#!/usr/bin/env python3
"""
Build jeeadv_fact_marks_at_rank from the JIC reports: one row per (year,
rank list, published rank) with the aggregate marks of the candidate at that
rank.

Each section 6.8-6.13 is a table of (rank, score) column pairs, seven pairs
to a row, ranks 1, 101, 201, ... The text layer is read with pdftotext
-layout over the report's first pages.

Quality gates (the build fails on any):
  - every (year, list) table yields rows, starting at rank 1
  - ranks are 1 mod 100 (anything else is a page footer or another table),
    except KNOWN_MISPRINTS, listed by name
  - marks within 0..max_marks
  - within a list, marks never rise as rank falls (a parse slip shows up as
    a rise)
  - a rank printed twice must carry the same marks (2025's CRL table prints
    rank 17301 twice, 99 both times — a misprint, kept once)

Usage:
  python3 scripts/build_clean.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, RAW_FILES, SECTIONS, TABLES

# ranks the report prints off the every-100th pattern, kept as printed
# (2025 CRL: "28402 80" sits where the row's other columns read x401)
KNOWN_MISPRINTS = {(2025, "CRL", 28402)}
HEAD = re.compile(r"^(6\.(?:8|9|10|11|12|13))\s+Aggregate Total Marks with Different Ranks")


def fetch_raw() -> None:
    need = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if need:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_BUCKET)
        for rf in need:
            rf.local_path.parent.mkdir(parents=True, exist_ok=True)
            bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
            print(f"  fetched {rf.name}")


def parse(rf) -> list[dict]:
    text = subprocess.run(["pdftotext", "-f", "1", "-l", "60", "-layout", str(rf.local_path), "-"],
                          capture_output=True, text=True, check=True).stdout
    lines = text.splitlines()
    starts = [(i, m.group(1)) for i, l in enumerate(lines) if (m := HEAD.match(l.strip()))]
    # the table of contents repeats the headings with dot leaders: skip those
    starts = [(i, s) for i, s in starts if ". ." not in lines[i]]
    out = []
    for k, (i, sec) in enumerate(starts):
        end = starts[k + 1][0] if k + 1 < len(starts) else i + 60
        for l in lines[i + 1:end]:
            if not re.match(r"^\s*\d", l) or re.search(r"[A-Za-z]", l):
                if re.match(r"^\s*7\s", l):      # next chapter
                    break
                continue
            nums = [int(x) for x in re.findall(r"\b\d+\b", l)]
            if len(nums) < 2 or len(nums) % 2:
                continue
            for rank, marks in zip(nums[0::2], nums[1::2]):
                if rank % 100 == 1 or (rf.year, SECTIONS[sec], rank) in KNOWN_MISPRINTS:
                    out.append({"exam_year": rf.year, "rank_list": SECTIONS[sec], "rank": rank,
                                "marks": marks, "max_marks": rf.max_marks,
                                "report_section": sec, "source_file": rf.name})
    return out


def check(df: pd.DataFrame) -> pd.DataFrame:
    key = ["exam_year", "rank_list", "rank"]
    conflict = df[df.duplicated(key, keep=False)].groupby(key).marks.nunique()
    assert (conflict <= 1).all(), f"a rank printed twice with different marks:\n{conflict[conflict > 1]}"
    df = df.drop_duplicates(key)
    for rf in RAW_FILES:
        for lst in SECTIONS.values():
            g = df[(df.exam_year == rf.year) & (df.rank_list == lst)].sort_values("rank")
            assert len(g) and g["rank"].iloc[0] == 1, f"{rf.year} {lst}: no table / no rank 1"
            assert g.marks.between(0, rf.max_marks).all(), f"{rf.year} {lst}: marks outside 0-{rf.max_marks}"
            rises = g[g.marks.diff() > 0]
            assert rises.empty, f"{rf.year} {lst}: marks rise as rank falls:\n{rises}"
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fetch_raw()
    df = check(pd.DataFrame([r for rf in RAW_FILES for r in parse(rf)]))
    df = df.sort_values(["exam_year", "rank_list", "rank"]).reset_index(drop=True)
    print(f"jeeadv_fact_marks_at_rank: {len(df)} rows")
    print(df.groupby(["exam_year", "rank_list"]).agg(points=("rank", "size"), last_rank=("rank", "max"),
                                                     top=("marks", "max"), last=("marks", "min")).to_string())
    if a.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(TABLES[0].local_path, index=False)
    print(f"✓ wrote {TABLES[0].local_path}")


if __name__ == "__main__":
    main()
