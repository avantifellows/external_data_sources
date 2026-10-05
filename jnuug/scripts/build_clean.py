#!/usr/bin/env python3
"""
Build jnuug_fact_cutoffs from JNU's four 2025-26 B.A. (Hons.) cut-off lists.

Each list prints two tables: Code-1 (80% of seats: Class 12 passed this year
or last) then Code-2 (20%: everyone else). Per programme code and category
(UR, SC, ST, PWD, OBC, EWS, FN = foreign nationals): the cut-off rank and
cut-off marks. Marks are JNU's merit score: English + GAT CUET marks (of
500) converted to 100 (Admission Policy 3.2). A blank cell = no offer in that
category in that list (no row).

Gates: every list has exactly one Code-1 and one Code-2 table; every code is
one of the 10 programmes; marks within 0-100; no duplicates.

Usage: python3 scripts/build_clean.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, PROGRAMS, RAW_FILES, TABLES, YEAR

CATS = {"UR": "UR", "SC": "SC", "ST": "ST", "PWD": "PWD", "OBC": "OBC", "EWS": "EWS", "FN": "FN"}


def fetch_raw() -> None:
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if missing:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_BUCKET)
        for rf in missing:
            rf.local_path.parent.mkdir(parents=True, exist_ok=True)
            bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))


def parse(rf) -> list[dict]:
    out = []
    with pdfplumber.open(rf.local_path) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        codes = [int(c) for c in re.findall(r"CODE-(\d)\s+LIST-\d", text)]
        tables = [t for p in pdf.pages for t in p.extract_tables()]
    assert codes == [1, 2] and len(tables) == 2, f"{rf.name}: codes {codes}, {len(tables)} tables"
    for code, t in zip(codes, tables):
        # header can span 1-3 rows: build each column's label from the rows
        # above the first programme row
        first = next(i for i, r in enumerate(t) if r[0] in PROGRAMS)
        labels = [" ".join((t[i][j] or "") for i in range(first)).replace("\n", " ") for j in range(len(t[0]))]
        cols = []
        for j, lab in enumerate(labels[1:], start=1):
            cat = next((c for k, c in CATS.items() if re.search(rf"\b{k}\b", lab)), None)
            kind = "rank" if "Rank" in lab else "marks" if "Marks" in lab else None
            assert cat and kind, f"{rf.name}: column {j} header {lab!r}"
            cols.append((j, cat, kind))
        for r in t[first:]:
            if r[0] not in PROGRAMS:
                assert not any(r), f"{rf.name}: unknown row {r}"
                continue
            vals = {}
            for j, cat, kind in cols:
                if r[j]:
                    vals.setdefault(cat, {})[kind] = float(r[j])
            for cat, v in vals.items():
                assert "marks" in v, f"{rf.name}: {r[0]} {cat} rank without marks"
                out.append({"year": YEAR, "list_no": rf.list_no, "seat_code": code,
                            "program_code": r[0], "program": PROGRAMS[r[0]], "category": cat,
                            "cutoff_rank": int(v["rank"]) if "rank" in v else None,
                            "cutoff_marks": v["marks"], "source_file": rf.name})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fetch_raw()
    df = pd.DataFrame([row for rf in RAW_FILES if rf.role == "list" for row in parse(rf)])
    key = ["list_no", "seat_code", "program", "category"]
    assert not df.duplicated(key).any()
    assert df.cutoff_marks.between(0, 100).all()
    df["cutoff_rank"] = df.cutoff_rank.astype("Int64")
    print(f"jnuug_fact_cutoffs: {len(df)} rows")
    print(df.groupby(["list_no", "seat_code"]).size().unstack().to_string())
    if a.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(TABLES[0].local_path, index=False)
    print(f"✓ wrote {TABLES[0].local_path}")


if __name__ == "__main__":
    main()
