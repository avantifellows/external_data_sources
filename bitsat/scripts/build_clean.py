#!/usr/bin/env python3
"""
Build bitsat_fact_cutoffs from BITS Pilani's BITSAT cut-off page.

One row per (academic year, campus, programme): the final BITSAT cut-off
score and the test's maximum marks that year (450 until 2021-22, 390 from
2022-23). BITS has no category reservation: one cut-off per seat.

Each year sits in <div id="YYYY-YYYY">; the innermost tables carry either
'Degree programme at <Campus> Campus | score | max' (2017-2019) or
'Campus | Program | score | max' (2020 on). The div id is the year: the
2020-21 block repeats the 2019-20 intro sentence, but its numbers differ.

A "Please note" row (2020-21) says ties at the cut-off score are broken on
PCM scores; it is skipped, the README records it.

Gates: every table row is a header, an intro or note sentence, or a parsed row; three
campuses every year; score <= max; no duplicates.

Usage: python3 scripts/build_clean.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, RAW_FILES, TABLES

CAMPUS = {"Pilani": "Pilani", "Goa": "K K Birla Goa", "K K Birla Goa": "K K Birla Goa",
          "Hyderabad": "Hyderabad"}


def program_of(p: str) -> str:
    p = re.sub(r"\s+", " ", p).strip()
    p = p.replace("Electrical and Electronics", "Electrical & Electronics")
    p = re.sub(r"^B\. ?Pharm\.?$", "B.Pharm.", p)
    return p


def fetch_raw() -> None:
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if missing:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_BUCKET)
        for rf in missing:
            rf.local_path.parent.mkdir(parents=True, exist_ok=True)
            bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))


def parse(path: Path) -> pd.DataFrame:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    rows = []
    for d in soup.find_all("div", id=re.compile(r"^20\d\d-20\d\d$")):
        year = d["id"]
        for t in (t for t in d.find_all("table") if not t.find("table")):
            campus = None
            for tr in t.find_all("tr"):
                if tr.find("tr"):  # 2021-22's malformed wrapper row holds the real rows
                    continue
                c = [re.sub(r"\s+", " ", x.get_text(" ", strip=True)) for x in tr.find_all(["td", "th"])]
                if not c or not any(c):
                    continue
                m = re.match(r"Degree programme at (\w+) Campus", c[0])
                if m:
                    campus = m.group(1)
                elif len(c) == 4 and re.fullmatch(r"\d{2,3}", c[2]):
                    rows.append((year, c[0], c[1], int(c[2]), int(c[3])))
                elif len(c) == 3 and re.fullmatch(r"\d{2,3}", c[1]):
                    rows.append((year, campus, c[0], int(c[1]), int(c[2])))
                elif c[0] == "Campus" or c[0].startswith(("The final BITSAT", "Please note")):
                    continue
                else:
                    raise SystemExit(f"{year}: unread row {c}")
    df = pd.DataFrame(rows, columns=["academic_year", "campus_raw", "program_raw", "cutoff_score", "max_score"])
    df.insert(1, "exam_year", df.academic_year.str[:4].astype(int))
    df.insert(3, "campus", df.campus_raw.map(CAMPUS))
    df.insert(5, "program", df.program_raw.map(program_of))
    df["campus_raw"] = df.campus_raw.fillna("")
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fetch_raw()
    df = parse(RAW_FILES[-1].local_path)
    assert df.campus.notna().all(), df[df.campus.isna()]
    assert (df.groupby("academic_year").campus.nunique() == 3).all()
    assert (df.cutoff_score <= df.max_score).all()
    assert not df.duplicated(["academic_year", "campus", "program"]).any()
    assert set(df.max_score) == {390, 450}
    df["source_file"] = RAW_FILES[-1].name
    print(f"bitsat_fact_cutoffs: {len(df)} rows, years {df.academic_year.min()} .. {df.academic_year.max()}")
    print(df.groupby("academic_year").size().to_string())
    if a.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(TABLES[0].local_path, index=False)
    print(f"✓ wrote {TABLES[0].local_path}")


if __name__ == "__main__":
    main()
