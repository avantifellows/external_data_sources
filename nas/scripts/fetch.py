#!/usr/bin/env python3
"""
Fetch the NAS 2021 raw source into raw/.

Upstream is the community CSV mirror gsidhu/NAS-2021-data — a tidy CSV form of
NCERT's published NAS 2021 (National Achievement Survey) results. There is no
single downloadable file; the data ships as a git repo of CSVs. This script
shallow-clones it into raw/, so the source CSVs land at:

    raw/NAS-2021-data/csv_data/

clean_nas.py reads from there (sources.SOURCE_CSV_DIR).

Usage:
  python3 scripts/fetch.py
  python3 scripts/fetch.py --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import RAW, SOURCE_CSV_DIR, SOURCE_REPO


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    dest = RAW / "NAS-2021-data"
    cmd = ["git", "clone", "--depth", "1", SOURCE_REPO, str(dest)]
    print(f"clone {SOURCE_REPO} → {dest}")
    if args.dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
        return

    if dest.exists():
        raise SystemExit(f"{dest} already exists — remove it to re-fetch.")
    RAW.mkdir(parents=True, exist_ok=True)
    subprocess.run(cmd, check=True)

    if not SOURCE_CSV_DIR.exists():
        raise SystemExit(f"clone succeeded but {SOURCE_CSV_DIR} is missing — upstream layout changed?")
    print(f"✓ csv_data at {SOURCE_CSV_DIR}")


if __name__ == "__main__":
    main()
