#!/usr/bin/env python3
"""
Fetch UPTAC's OR-CR ("cut-off matrix") table, every page, as raw HTML.

Source: https://uptac.samarth.edu.in/index.php/cut-off-matrix/index — a
Yii2 grid, all rounds and programmes with no filter, 50 rows per page (the
server ignores larger per-page values). Pages are saved verbatim to
raw/pages/page_NNNN.html; build_clean.py parses them. Polite: one request
per second, retries with backoff.

Checks: the "Showing a-b of N records" total is read on the first and last
page and must agree, and Sr.No must run 1..N with no gaps — a table that
changed mid-scrape fails here, not later.

Usage:
  python3 scripts/fetch_pages.py            # fetch missing pages
  python3 scripts/fetch_pages.py --force    # refetch everything
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BASE_URL, PAGES

UA = "Mozilla/5.0 (compatible; AvantiFellows-open-data; +https://avantifellows.org)"
TOTAL_RE = re.compile(r"Showing\s+[\d,]+-([\d,]+)\s+of\s+([\d,]+)\s+records")


def get(page: int) -> str:
    url = f"{BASE_URL}&page={page}&per-page=50"
    for attempt in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # network blips: back off and retry
            wait = 5 * 2 ** attempt
            print(f"  page {page}: {e!s:.60} — retry in {wait}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"page {page}: failed after retries")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    PAGES.mkdir(parents=True, exist_ok=True)

    first = get(1)
    m = TOTAL_RE.search(first)
    if not m:
        raise SystemExit("no 'Showing … of N records' on page 1")
    total = int(m.group(2).replace(",", ""))
    n_pages = -(-total // 50)
    print(f"{total:,} records -> {n_pages} pages", flush=True)
    (PAGES / "page_0001.html").write_text(first)

    for page in range(2, n_pages + 1):
        out = PAGES / f"page_{page:04d}.html"
        if out.exists() and not args.force:
            continue
        time.sleep(1.0)
        html = get(page)
        mm = TOTAL_RE.search(html)
        if not mm or int(mm.group(2).replace(",", "")) != total:
            raise SystemExit(f"page {page}: record total changed mid-scrape ({mm and mm.group(2)})")
        out.write_text(html)
        if page % 50 == 0:
            print(f"  …{page}/{n_pages}", flush=True)
    print("✓ done.", flush=True)


if __name__ == "__main__":
    main()
