#!/usr/bin/env python3
"""
Fetch the raw MoE board-results PDFs from their canonical source URLs into raw/.

Makes the source files regenerable from scratch — no manual download. URLs are
in sources.py (REPORT_URLS). After fetching, run clean_board_results.py →
upload_to_gcs.py → load_bq.py.

Usage:
  python3 scripts/fetch.py                 # download any missing years
  python3 scripts/fetch.py --force         # re-download all
  python3 scripts/fetch.py --year 2024     # one year
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import RAW, REPORTS, REPORT_URLS

# education.gov.in returns 403 to minimal User-Agents — send full browser headers.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    print(f"  ✓ {dest.name}  ({dest.stat().st_size / 1e6:.1f} MB)  ← {url}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", type=int, default=None, help="Fetch only this report year")
    ap.add_argument("--force", action="store_true", help="Re-download even if the file exists")
    args = ap.parse_args()

    years = [args.year] if args.year else list(REPORT_URLS)
    print(f"board_results fetch → {RAW}")
    for year in years:
        if year not in REPORT_URLS:
            raise SystemExit(f"unknown year {year}; known: {list(REPORT_URLS)}")
        dest = REPORTS[year]
        if dest.exists() and not args.force:
            print(f"  • {dest.name} exists (use --force to re-download)")
            continue
        _download(REPORT_URLS[year], dest)
    print("✓ done.")


if __name__ == "__main__":
    main()
