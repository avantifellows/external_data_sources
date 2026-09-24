#!/usr/bin/env python3
"""
Fetch each NIC OR-CR report in sources.REPORTS as raw HTML.

A report link only works when followed from the board's portal: open the
portal (session cookie), find the link by its exact title, request it with
the portal as Referer. Saved verbatim to raw/<board>_<programme>_<year>.html.

Usage:
  python3 scripts/fetch_reports.py            # fetch missing
  python3 scripts/fetch_reports.py --force
"""
from __future__ import annotations

import argparse
import http.cookiejar
import sys
import time
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import RAW, REPORTS

UA = "Mozilla/5.0 (compatible; AvantiFellows-open-data; +https://avantifellows.org)"


def fetch(rep) -> str:
    for attempt in range(4):
        try:
            jar = http.cookiejar.CookieJar()
            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
            op.addheaders = [("User-Agent", UA)]
            portal = BeautifulSoup(op.open(rep.portal, timeout=60).read().decode("utf-8", "ignore"), "html.parser")
            links = [a.get("href") for a in portal.find_all("a") if a.get_text(" ", strip=True) == rep.title]
            if not links:
                raise SystemExit(f"{rep.title!r} not linked on {rep.portal}")
            req = urllib.request.Request(links[0], headers={"Referer": rep.portal})
            with op.open(req, timeout=120) as r:
                if "errmsg" in r.geturl():
                    raise RuntimeError("redirected to NIC error page")
                return r.read().decode("utf-8", "ignore")
        except SystemExit:
            raise
        except Exception as e:
            wait = 10 * 2 ** attempt
            print(f"  {rep.raw_name}: {e!s:.70} — retry in {wait}s", flush=True)
            time.sleep(wait)
    raise SystemExit(f"{rep.raw_name}: failed after retries")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    for rep in REPORTS:
        out = RAW / rep.raw_name
        if out.exists() and not args.force:
            continue
        html = fetch(rep)
        out.write_text(html)
        print(f"  {rep.raw_name}: {len(html)/1e3:.0f} kB", flush=True)
        time.sleep(2)
    print("✓ done.")


if __name__ == "__main__":
    main()
