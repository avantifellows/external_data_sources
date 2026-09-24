#!/usr/bin/env python3
"""
Parse the NIC OR-CR reports (raw/*.html) into nicorcr_fact_cutoffs.

One row per report row: board x year x round x institute x programme x
quota x category, with opening / closing JEE Main CRL rank.

Labels (same scheme as uptac/, from the U.P. reservation rules):
- category "BC(GIRL)" -> parent OBC + sub-category "Female (UP)"; OPEN ->
  GEN; sub-categories GIRL / AF (defence personnel ward) / FF (freedom
  fighter dependant) / PH (divyangjan); "OPEN (TF)" -> TFW (tuition fee
  waiver). category_raw keeps the printed code.
- quota: 'Home State' (U.P. domicile) or 'All India' — HBTU keeps All
  India seats in every round, unlike UPTAC.
- programme: "(TFW)" (2026) / "(FW)" (2024-25) suffix -> tfw; `programme` readable ("Computer
  Science & Engineering"), printed text in programme_raw.
- report headers vary by year ("Program" vs "Academic Program Name",
  "Opening Rank" vs "Opening CRL Rank"); all are JEE Main CRL ranks.

Checks: every report has its 8 columns; ranks numeric; opening <= closing;
unique grain; every category known.

Usage:
  python3 scripts/build_clean.py            # parse + write parquet
  python3 scripts/build_clean.py --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, GCS_PREFIX, RAW, REPORTS, TABLES

HEADER = {"Sr.No": "sr_no", "Round": "round", "Institute": "institute",
          "Program": "programme_raw", "Academic Program Name": "programme_raw",
          "Quota": "quota", "Category": "category_raw",
          "Opening Rank": "opening_rank", "Opening CRL Rank": "opening_rank",
          "Closing Rank": "closing_rank", "Closing CRL Rank": "closing_rank"}
PARENT = {"OPEN": "GEN", "BC": "OBC", "SC": "SC", "ST": "ST", "EWS": "EWS"}
SUB = {None: None, "GIRL": "Female (UP)", "AF": "Defence personnel ward",
       "FF": "Freedom fighter dependant", "PH": "Divyangjan"}
CAT = re.compile(r"^(OPEN|BC|SC|ST|EWS)\s*(?:\(?\s*(GIRL|AF|FF|PH|TF)\s*\)?)?$")
WORDS = {"ENGG.": "Engineering", "ENGG": "Engineering", "SC.": "Science", "&": "&",
         "AI": "AI", "ML": "ML", "AND": "and", "OF": "of"}


def fetch_raw() -> None:
    missing = [r for r in REPORTS if not (RAW / r.raw_name).exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for r in missing:
        bucket.blob(f"{GCS_PREFIX}/raw/{r.raw_name}").download_to_filename(str(RAW / r.raw_name))
        print(f"  fetched {r.raw_name} from GCS")


def split_category(raw: str) -> tuple[str, str | None]:
    m = CAT.match(raw.strip())
    if not m:
        raise SystemExit(f"unknown category {raw!r}")
    parent, sub = m.group(1), m.group(2)
    if sub == "TF":
        return "TFW", None
    return PARENT[parent], SUB[sub]


def readable(p: str) -> str:
    p = re.sub(r"\s*\((TFW|FW)\)\s*$", "", p).strip()
    out = []
    for w in p.split():
        lead, core, tail = re.match(r"^(\(?)(.*?)(\)?)$", w).groups()
        out.append(lead + (WORDS.get(core) or WORDS.get(core.upper()) or core.capitalize()) + tail)
    return " ".join(out)


def parse() -> pd.DataFrame:
    frames = []
    for rep in REPORTS:
        s = BeautifulSoup((RAW / rep.raw_name).read_text(encoding="utf-8"), "html.parser")
        t = max(s.find_all("table"), key=lambda t: len(t.find_all("tr")))
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in t.find_all("tr")]
        head = [HEADER.get(h) for h in rows[0]]
        if None in head or len(head) != 8:
            raise SystemExit(f"{rep.raw_name}: unexpected header {rows[0]}")
        body = [r for r in rows[1:] if len(r) == 8]
        if len(body) != len(rows) - 1:
            raise SystemExit(f"{rep.raw_name}: {len(rows) - 1 - len(body)} rows without 8 cells")
        df = pd.DataFrame(body, columns=head)
        df.insert(0, "year", rep.year)
        df.insert(0, "programme_level", rep.programme)
        df.insert(0, "board", rep.board)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def build(df: pd.DataFrame) -> pd.DataFrame:
    cat = df.category_raw.map(split_category)
    out = pd.DataFrame({
        "board": df.board, "year": df.year, "programme_level": df.programme_level,
        "round": df["round"], "institute": df.institute,
        "programme_raw": df.programme_raw, "programme": df.programme_raw.map(readable),
        "tfw": df.programme_raw.str.contains(r"\((?:TFW|FW)\)\s*$") | (cat.map(lambda x: x[0]) == "TFW"),
        "quota": df.quota, "category_raw": df.category_raw,
        "parent_category": cat.map(lambda x: x[0]), "sub_category": cat.map(lambda x: x[1]),
        "opening_rank": pd.to_numeric(df.opening_rank, errors="raise"),
        "closing_rank": pd.to_numeric(df.closing_rank, errors="raise"),
        "rank_basis": "JEE Main CRL rank",
    })
    return out


def check(out: pd.DataFrame) -> None:
    grain = ["board", "year", "round", "institute", "programme_raw", "quota", "category_raw"]
    assert not out.duplicated(grain).any(), "duplicate grain rows"
    assert (out.opening_rank <= out.closing_rank).all(), "opening after closing"
    assert set(out.quota) <= {"Home State", "All India"}, set(out.quota)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    fetch_raw()
    out = build(parse())
    check(out)
    print(f"nicorcr_fact_cutoffs: {len(out):,} rows, boards {sorted(out.board.unique())}, "
          f"years {sorted(out.year.unique())}")
    if args.dry_run:
        return
    t = TABLES[0]
    CLEAN.mkdir(parents=True, exist_ok=True)
    out.to_parquet(t.local_path, index=False)
    print(f"  wrote {t.local_path.relative_to(CLEAN.parent)}")


if __name__ == "__main__":
    main()
