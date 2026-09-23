#!/usr/bin/env python3
"""
Parse the IISER round-wise closing-rank PDF into iiser_fact_cutoffs.

Layout (pdftotext -layout): nine "Round N: Closing Ranks" sections, each a
table with ten numeric columns — UR, UR-PwD, EWS, EWS-PwD, OBC-NCL,
OBC-NCL-PwD, SC, SC-PwD, ST, ST-PwD — where "--" means no seat was offered
in that cell that round. A long programme name wraps around its values
line: "BS-MS (Computational and Data Sciences) IISER" / <values> / "Kolkata".

Output grain: one row per (round, program, category) with a published
closing rank. "--" cells are dropped, never written as 0.

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

CATEGORIES = ["UR", "UR-PwD", "EWS", "EWS-PwD", "OBC-NCL", "OBC-NCL-PwD",
              "SC", "SC-PwD", "ST", "ST-PwD"]
ROUND_RE = re.compile(r"Round\s+(\d+):\s+Closing Ranks")
VALUE = r"(?:\d+|--)"
VALUES_RE = re.compile(r"^(?P<name>.*?)\s*(?P<vals>(?:" + VALUE + r"\s+){9}" + VALUE + r")\s*$")
NEW_PROGRAM = re.compile(r"^(BS-MS|BS\b|BS \(|B\.Tech|B\.S\.)")
NOISE = ("IISER Admissions", "Closing Ranks", "Kindly note", "Unreserved",
         "Academic Program", "Important Updates", "Admission to", "options,",
         "made under", "Round ", "•")


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


def institute_of(program: str) -> str:
    m = re.search(r"IISER\s+([A-Z][A-Za-z]+)\s*$", program)
    return f"IISER {m.group(1)}" if m else program


def parse(pdf: Path) -> pd.DataFrame:
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    rows, rnd = [], None
    pending_name = None      # a name line whose values sit on the next line
    open_row = None          # last row's program, awaiting a wrapped tail
    for raw in text.splitlines():
        line = raw.strip()
        # the page number sometimes lands at the end of a table line
        # ("… 50055   --   3"): eleven trailing tokens -> drop the last
        toks = line.split()
        if len(toks) >= 11 and all(re.fullmatch(VALUE, t) for t in toks[-11:]) \
                and re.search(r"\s{2,}\d{1,2}$", raw.rstrip()):
            line = line[: line.rstrip().rfind(" ")].rstrip()
        m = ROUND_RE.search(line)
        if m:
            rnd, pending_name, open_row = int(m.group(1)), None, None
            continue
        if rnd is None or not line:
            continue
        v = VALUES_RE.match(line)
        if v:
            name = v.group("name").strip() or pending_name or ""
            vals = v.group("vals").split()
            open_row = {"name": name, "vals": vals, "round": rnd}
            rows.append(open_row)
            # a values line with no name of its own may still get a tail
            if v.group("name").strip():
                open_row = None
            pending_name = None
            continue
        if any(line.startswith(n) for n in NOISE) or re.fullmatch(r"[A-Z\- ]+", line):
            continue
        if NEW_PROGRAM.match(line):
            pending_name, open_row = line, None
            continue
        if open_row is not None:          # wrapped tail: "Kolkata", "Bhopal"
            open_row["name"] = f"{open_row['name']} {line}".strip()
            open_row = None
    out = []
    for r in rows:
        prog = re.sub(r"\s+", " ", r["name"]).strip()
        for cat, val in zip(CATEGORIES, r["vals"]):
            if val == "--":
                continue
            out.append({"year": YEAR, "round": r["round"], "program_name": prog,
                        "institute": institute_of(prog), "category": cat,
                        "closing_rank": int(val),
                        "rank_basis": "IAT overall rank"})
    return pd.DataFrame(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    fetch_raw()
    df = parse(RAW_FILES[0].local_path)
    dup = df.duplicated(subset=["round", "program_name", "category"]).sum()
    assert dup == 0, f"{dup} duplicate (round, program, category) rows"
    bad = df[~df.program_name.str.contains(r"IISER [A-Z]", regex=True)]
    assert bad.empty, f"unparsed programme names: {bad.program_name.unique()[:5]}"
    print(f"  {len(df):,} rows, {df.program_name.nunique()} programmes, "
          f"{df.institute.nunique()} IISERs, rounds {sorted(df['round'].unique())}")
    t = TABLES[0]
    if args.dry_run:
        print(f"  [dry-run] would write {t.local_path}")
        return
    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(t.local_path, index=False)
    print(f"✓ wrote {t.local_path} ({len(df):,} rows)")


if __name__ == "__main__":
    main()
