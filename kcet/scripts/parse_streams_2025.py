#!/usr/bin/env python3
"""
KEA 2025 Third Round cut-off ranks for the KCET streams other than
engineering → raw/KA_streams_2025_cutoffs_R3.csv.

Same KEA layout as engineering (futures-v2 parse_KA_2025.py, now archived):
one table per college under a "College: <code> <name>" line, a column per
category code, a closing rank per (course, category). Two files per stream,
one per seat pool: _R_ = Rest of Karnataka, _H_ = 371(j) Kalyana-Karnataka.

Streams (KEA course code → stream):
  B  B-Pharma                  Pharma
  H  Pharm-D                   Pharma
  N  Agri(BSc)(Theory)         Agriculture
  F  Food Sci(Theory)          Agriculture
  V  Veter Sci(Theory)         Agriculture
  S  Agricultural Engineering  Agriculture
The "(Pract.)" lists (P, Q, T) rank on KEA's separate practical exam (the
farmers' quota), not on the KCET rank, so they're not parsed.

The category header is read from each table (agriculture lists carry GMP;
the Kalyana-Karnataka files carry the H codes) and every code must be a known
KEA code. Ranks can be halves (845.5: a tie KEA broke). Checks: every table
has a college heading, no duplicate (college, course, pool, category).

Source URLs: https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/
  PROF_CODE_<code>_<R|H>_11092025english.pdf  (Third Round, 11 Sep 2025)

Usage:
  python3 scripts/parse_streams_2025.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
OUT = RAW / "KA_streams_2025_cutoffs_R3.csv"
URL = "https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_{code}_{pool}_11092025english.pdf"

STREAMS = {"B": ("Pharma", "B-Pharma"), "H": ("Pharma", "Pharm-D"),
           "N": ("Agriculture", "Agri(BSc)(Theory)"), "F": ("Agriculture", "Food Sci(Theory)"),
           "V": ("Agriculture", "Veter Sci(Theory)"), "S": ("Agriculture", "Agricultural Engineering")}
POOLS = {"R": "GEN", "H": "HK"}

BASE = ["1", "2A", "2B", "3A", "3B", "GM", "SC", "ST"]
KNOWN = ({f"{v}{h}" for v in BASE for h in ("G", "K", "R")}
         | {f"{v}{h}H" for v in BASE for h in ("", "K", "R")}
         | {"GM", "GMP", "GMPH", "GMH", "NRI", "OPN", "OTH"})
COLLEGE_RE = re.compile(r"College:\s*([A-Z]\d+)\s+(.*)")


def clean(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def rank(v):
    # narrow columns wrap a long rank: "105579.\n5" is 105579.5
    v = re.sub(r"(?<=\d)\s+(?=[\d.])|(?<=\.)\s+(?=\d)", "", str(v or "")).strip()
    if not v or v in ("--", "-"):
        return None
    try:
        return float(v)
    except ValueError:
        raise ValueError(f"unreadable rank {v!r}")


def parse(path: Path, stream: str, pool: str) -> list[dict]:
    rows, current = [], (None, None)
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            heads = [COLLEGE_RE.match(l.strip()) for l in (page.extract_text() or "").split("\n")]
            heads = [(m.group(1), clean(m.group(2))) for m in heads if m]
            tables = [t for t in page.extract_tables() if t and len(t) >= 2]
            if heads and not tables:
                if len(heads) != 1:
                    raise ValueError(f"{path.name} p{page.page_number}: {len(heads)} headings, no table")
                current = heads[0]
                continue
            if heads and len(heads) != len(tables):
                raise ValueError(f"{path.name} p{page.page_number}: {len(heads)} headings for {len(tables)} tables")
            for i, t in enumerate(tables):
                if heads:
                    current = heads[i]
                if current[0] is None:
                    raise ValueError(f"{path.name} p{page.page_number}: table with no college heading")
                cats = [clean(c) for c in t[0][1:]]
                unknown = [c for c in cats if c not in KNOWN]
                if unknown:
                    raise ValueError(f"{path.name} p{page.page_number}: unknown category codes {unknown}")
                for r in t[1:]:
                    course = clean(r[0])
                    if not course or course == "Course Name":
                        continue
                    for j, cat in enumerate(cats, start=1):
                        v = rank(r[j] if j < len(r) else None)
                        if v is not None:
                            rows.append({"college_code": current[0], "college_name": current[1],
                                         "stream": stream, "course_name": course,
                                         "domicile_pool": pool, "category_code": cat,
                                         "closing_rank": v, "year": 2025, "round": 3})
            page.close()
    return rows


def main() -> None:
    rows = []
    for code, (stream, label) in STREAMS.items():
        for p, pool in POOLS.items():
            path = RAW / f"KA_{code}_2025_{p}_R3.pdf"
            if not path.exists():
                sys.exit(f"missing {path.name}: download {URL.format(code=code, pool=p)}")
            got = parse(path, stream, pool)
            print(f"  {label:26} {pool}: {len(got):5} ranks, {len({r['college_code'] for r in got})} colleges")
            rows += got
    df = pd.DataFrame(rows)
    grain = ["college_code", "course_name", "domicile_pool", "category_code"]
    dup = df[df.duplicated(grain, keep=False)]
    if not dup.empty:
        raise SystemExit(f"duplicate cutoff grain:\n{dup.head(10).to_string(index=False)}")
    df.to_csv(OUT, index=False)
    print(f"→ {OUT.name}: {len(df):,} rows, {df.college_code.nunique()} colleges, "
          f"{df.course_name.nunique()} courses")
    print(df.groupby(["stream", "course_name"]).size().to_string())


if __name__ == "__main__":
    main()
