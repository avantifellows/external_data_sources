#!/usr/bin/env python3
"""
Fetch the raw NMC UG (MBBS) seat-matrix PDF from its canonical source URL into
raw/.

Makes the source file regenerable from scratch — no manual download. The URL is
in sources.py (PDF_URL). After fetching, run clean_nmc.py → upload_to_gcs.py →
load_bq.py.

Usage:
  python3 scripts/fetch.py              # download if missing
  python3 scripts/fetch.py --force      # re-download even if present
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import PDF, PDF_URL, RAW

# nmc.org.in (like most gov sites) returns 403 to minimal User-Agents —
# send full browser headers.
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
    ap.add_argument("--force", action="store_true", help="Re-download even if the file exists")
    args = ap.parse_args()

    print(f"nmc fetch → {RAW}")
    if PDF.exists() and not args.force:
        print(f"  • {PDF.name} exists (use --force to re-download)")
    else:
        _download(PDF_URL, PDF)
    print("✓ done.")


if __name__ == "__main__":
    main()
