#!/usr/bin/env python3
"""
Build cusbug_fact_cutoffs from the Central University of South Bihar's
2025-26 UG cut-off announcements.

Each announcement is one table: programme x UR / OBC / SC / ST / EWS / PwD /
CW (wards of armed-forces personnel) -> cut-off score, "All" (all
registered candidates) or "--" / "-" (no seats offered that round). One row
per printed cell that holds a score or "All"; "--" cells are left out.
Rounds 2-6 print only the cells that re-opened.

Rounds 1, 2, 4, 5 have a text layer and are parsed here; rounds 3, 6 and the
round-1 corrigendum are scans, taken from extracted/manual_transcriptions.csv.

The score is the sum of the CUET papers the programme counts (Annexure I;
see ../cuet, rules CUSB_*): GAT + one subject (of 500), or one paper (of 250).

Quality gates: every text round yields rows; every row names one of the 23
programmes; no duplicates; scores within 0-500; round 1 has all 23
programmes (the full table).

Usage:
  python3 scripts/build_clean.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, MANUAL, MANUAL_GCS, RAW, RAW_FILES, TABLES, YEAR

CATS = ["UR", "OBC", "SC", "ST", "EWS", "PWD", "CW"]
# printed programme -> canonical (first keyword hit; names wrap over lines)
PROGRAMS = [
    (r"B\.A\.\s*B\.Ed", "4 Year Integrated B.A. B.Ed."),
    (r"B\.Sc\.\s*B\.Ed", "4 Year Integrated B.Sc. B.Ed."),
    (r"Agriculture", "4 Year B.Sc. (Hons.) Agriculture"),
    (r"BBA\.?\s*LLB", "5 Year Integrated BBA.LLB"),
    (r"BA\.?\s*LLB", "5 Year Integrated BA.LLB (Hons.)"),
    (r"Commerce", "5 Year Integrated UG-PG in Commerce"),
    (r"Mathematics", "5 Year Integrated UG-PG in Mathematics"),
    (r"Statistics", "5 Year Integrated UG-PG in Statistics"),
    (r"Chemistry", "5 Year Integrated UG-PG in Chemistry"),
    (r"Physics", "5 Year Integrated UG-PG in Physics"),
    (r"Computer", "5 Year Integrated UG-PG in Computer Science"),
    (r"Life Science", "5 Year Integrated UG-PG in Life Science"),
    (r"Geology", "5 Year Integrated UG-PG in Geology"),
    (r"Geography", "5 Year Integrated UG-PG in Geography"),
    (r"English", "5 Year Integrated UG-PG in English"),
    (r"Hindi", "5 Year Integrated UG-PG in Hindi"),
    (r"History", "5 Year Integrated UG-PG in History"),
    (r"Sociology", "5 Year Integrated UG-PG in Sociology"),
    (r"Political", "5 Year Integrated UG-PG in Political Science and International Relations"),
    (r"Economics", "5 Year Integrated UG-PG in Economics"),
    (r"Psychology", "5 Year Integrated UG-PG in Psychology"),
    (r"Journalism", "5 Year Integrated UG-PG in Journalism and Mass Communication"),
    (r"Pharmacy", "2 Year Diploma in Pharmacy"),
]
CELL = r"(\d+(?:\.\d+)?|All|--?|–)"
ROW = re.compile(r"^\s*(?:\d+\.?\s+)?(?P<prog>\S.*?)?\s+" + r"\s+".join([CELL] * 7) + r"\s*$")


def fetch_raw() -> None:
    need = [(rf.local_path, rf.gcs_path) for rf in RAW_FILES if not rf.local_path.exists()]
    if not MANUAL.exists():
        need.append((MANUAL, MANUAL_GCS))
    if need:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_BUCKET)
        for local, path in need:
            local.parent.mkdir(parents=True, exist_ok=True)
            bucket.blob(path).download_to_filename(str(local))
            print(f"  fetched {local.name}")


def canon(text: str) -> str | None:
    return next((p for pat, p in PROGRAMS if re.search(pat, text)), None)


def parse(rf) -> list[dict]:
    text = subprocess.run(["pdftotext", "-layout", str(rf.local_path), "-"],
                          capture_output=True, text=True, check=True).stdout
    m = re.search(r"Date:\s*(\d{2})\.(\d{2})\.(\d{4})", text)
    notice = date(int(m[3]), int(m[2]), int(m[1])) if m else None
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        r = ROW.match(line)
        if not r:
            continue
        # the programme name can wrap onto the next line(s), or start on
        # the line above (the serial number then sits below)
        here = r["prog"] or ""
        nxt = lines[i + 1] if i + 1 < len(lines) and not ROW.match(lines[i + 1]) else ""
        prev = lines[i - 1] if i and not ROW.match(lines[i - 1]) else ""
        prog = canon(here) or canon(f"{here} {nxt}") or canon(f"{prev} {here}")
        if prog is None:
            raise SystemExit(f"{rf.name}: no programme for {line!r}")
        for cat, cell in zip(CATS, r.groups()[1:]):
            if cell in ("--", "-", "–"):
                continue
            out.append({"round": rf.round, "notice_date": notice, "program": prog,
                        "category": cat, "cutoff": None if cell == "All" else float(cell),
                        "all_admitted": cell == "All", "source_file": rf.name,
                        "extraction": "text"})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fetch_raw()
    rows = []
    for rf in RAW_FILES:
        if rf.role == "text":
            got = parse(rf)
            assert got, f"{rf.name}: no rows"
            rows += got
    m = pd.read_csv(MANUAL)
    assert set(m.file) == {rf.name for rf in RAW_FILES if rf.role == "manual"}
    assert set(m.program) <= {p for _, p in PROGRAMS}, set(m.program) - {p for _, p in PROGRAMS}
    m = m.assign(notice_date=pd.to_datetime(m.notice_date).dt.date,
                 all_admitted=m.all_admitted.astype(str).str.lower() == "true",
                 extraction="manual").rename(columns={"file": "source_file"})
    df = pd.concat([pd.DataFrame(rows), m.drop(columns="note")], ignore_index=True)
    df.insert(0, "year", YEAR)
    df["round"] = df["round"].astype(int)
    key = ["round", "program", "category", "source_file"]
    assert not df.duplicated(key).any(), df[df.duplicated(key, keep=False)]
    assert df.cutoff.dropna().between(0, 500).all()
    r1 = df[(df["round"] == 1) & (df.extraction == "text")].program.nunique()
    assert r1 == len(PROGRAMS), f"round 1 has {r1} programmes, expected {len(PROGRAMS)}"
    df = df.sort_values(["program", "round", "category"]).reset_index(drop=True)
    print(f"cusbug_fact_cutoffs: {len(df)} rows, {df.program.nunique()} programmes, rounds {sorted(df['round'].unique())}")
    print(df.groupby("round").size().to_string())
    if a.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(TABLES[0].local_path, index=False)
    print(f"✓ wrote {TABLES[0].local_path}")


if __name__ == "__main__":
    main()
