#!/usr/bin/env python3
"""
Build jamiaug_fact_cutoffs from JMI's 2025-26 CUET UG selection lists.

Each list ends with a "Category-wise cut-off marks" table (S.No., CATEGORY,
Cut-off). Cut-offs are CUET marks (of 250) in the one paper the programme
counts (sources.PROGRAMS). Categories are JMI's own reservation scheme:
GENERAL (open), MUSLIM, MUSLIM OBC/MUSLIM ST, MUSLIM WOMEN, JAMIA (internal
JMI students), PWD, KASHMIRI MIGRANTS, CANDIDATES FROM JAMMU & KASHMIR.

Gates: every list has the table; categories in the known set; 0-250; no
duplicates.

Usage: python3 scripts/build_clean.py [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, PROGRAMS, RAW_FILES, TABLES, YEAR

CATEGORY = {"GENERAL": "GENERAL", "MUSLIM": "MUSLIM", "MUSLIM OBC/MUSLIM ST": "MUSLIM_OBC_ST",
            "MUSLIM WOMEN": "MUSLIM_WOMEN", "JAMIA": "JAMIA_INTERNAL", "PWD": "PWD",
            "KASHMIRI MIGRANTS": "KASHMIRI_MIGRANT", "CANDIDATES FROM JAMMU & KASHMIR": "JK_CANDIDATE"}


def fetch_raw() -> None:
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if missing:
        from google.cloud import storage
        bucket = storage.Client().bucket(GCS_BUCKET)
        for rf in missing:
            rf.local_path.parent.mkdir(parents=True, exist_ok=True)
            bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))


def cutoff_table(rf) -> list[list[str]]:
    with pdfplumber.open(rf.local_path) as pdf:
        for pg in pdf.pages:
            if "cut-off marks" in (pg.extract_text() or "").lower():
                for t in pg.extract_tables():
                    if t and t[0][:2] == ["S.No.", "CATEGORY"]:
                        return t[1:]
    raise SystemExit(f"{rf.name}: no cut-off table")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    fetch_raw()
    rows = []
    for rf in RAW_FILES:
        if rf.role != "list":
            continue
        for r in cutoff_table(rf):
            raw = r[1].replace("\n", " ").strip()
            rows.append({"year": YEAR, "program_code": rf.code, "program": PROGRAMS[rf.code][0],
                         "cuet_paper": PROGRAMS[rf.code][1], "list_no": rf.list_no,
                         "category_raw": raw, "category": CATEGORY[raw],
                         "cutoff": float(r[2]), "source_file": rf.name})
    df = pd.DataFrame(rows)
    assert not df.duplicated(["program_code", "list_no", "category"]).any()
    assert df.cutoff.between(0, 250).all()
    print(f"jamiaug_fact_cutoffs: {len(df)} rows, {df.program_code.nunique()} programmes, {df.source_file.nunique()} lists")
    print(df.groupby("category").size().to_string())
    if a.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(TABLES[0].local_path, index=False)
    print(f"✓ wrote {TABLES[0].local_path}")


if __name__ == "__main__":
    main()
