#!/usr/bin/env python3
"""
Save NMC's live "List of College Teaching MBBS" into raw/, dated.

The list on nmc.org.in (sources.LIVE_PAGE) is filled from a JSON endpoint
(sources.LIVE_URL); one request with a large per_page returns every college.
The response is saved as-is, as raw/nmc_mbbs_colleges_<YYYY-MM-DD>.json, so a
later fetch never overwrites an earlier one. Then run clean_live.py →
upload_to_gcs.py → load_bq.py.

Usage:
  python3 scripts/fetch_live.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import LIVE_PAGE, LIVE_URL, RAW

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": LIVE_PAGE,
}


def main() -> None:
    req = urllib.request.Request(LIVE_URL, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=120) as resp:
        body = resp.read()
    d = json.loads(body)
    rows, pag = d.get("data") or [], d.get("pagination") or {}
    # one page must hold the whole list, or the file is a fragment
    if not d.get("success") or len(rows) != pag.get("total") or pag.get("last_page") != 1:
        raise SystemExit(f"incomplete response: {len(rows)} rows, pagination {pag}")
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"nmc_mbbs_colleges_{dt.date.today().isoformat()}.json"
    dest.write_bytes(body)
    print(f"  ✓ {dest.name}: {len(rows)} colleges, {d.get('total_seats')} seats  ← {LIVE_URL}")


if __name__ == "__main__":
    main()
