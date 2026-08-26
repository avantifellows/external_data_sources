"""
Fetch the CLAT 2026 allotment-list pages (via Wayback) and every UG per-NLU
PDF (direct from the consortium's still-live S3). Idempotent — existing valid
files are skipped.

Usage:  python3 scripts/fetch_lists.py
"""
from __future__ import annotations

import re
import time
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import LISTS, RAW, S3_BASE

UA = {"User-Agent": "Mozilla/5.0 (compatible; AvantiFellows data pipeline)"}
# Wayback snapshots of the five list pages (the live site rotated to CLAT 2027)
WAYBACK_PAGES = {
    1: "https://web.archive.org/web/20260107075633/https://consortiumofnlus.ac.in/clat-2026/first-list.html",
    2: "https://web.archive.org/web/2026/https://consortiumofnlus.ac.in/clat-2026/second-list.html",
    3: "https://web.archive.org/web/2026/https://consortiumofnlus.ac.in/clat-2026/third-list.html",
    4: "https://web.archive.org/web/20260606163256/https://consortiumofnlus.ac.in/clat-2026/fourth-list.html",
    5: "https://web.archive.org/web/20260606161537/https://consortiumofnlus.ac.in/clat-2026/fifth-list.html",
}
ORDINAL = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}


def get(url: str, timeout: int = 60) -> bytes | None:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA),
                                    timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def main() -> None:
    pages = RAW / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    for n, url in WAYBACK_PAGES.items():
        out = pages / f"2026_{ORDINAL[n]}-list.html"
        if not out.exists():
            body = get(url)
            if body:
                out.write_bytes(body)
                print(f"  page list{n}  {len(body):,}B")
            else:
                print(f"  page list{n}  UNAVAILABLE on wayback")
            time.sleep(1)

    for n in LISTS:
        outdir = RAW / "pdf" / f"list{n}"
        outdir.mkdir(parents=True, exist_ok=True)
        # UG pdf names are harvested from whichever list pages we hold —
        # the S3 naming is stable across lists for the same college/program.
        names: set[str] = set()
        for f in pages.glob("*.html"):
            names |= set(re.findall(r"list\d/(UG-[A-Za-z0-9]+-2026\.pdf)",
                                    f.read_text(errors="ignore")))
        got = miss = 0
        for name in sorted(names):
            out = outdir / name
            if out.exists() and out.read_bytes()[:4] == b"%PDF":
                got += 1
                continue
            body = get(f"{S3_BASE}/list{n}/{name}", timeout=45)
            if body and body[:4] == b"%PDF":
                out.write_bytes(body)
                got += 1
            else:
                miss += 1
        print(f"  list{n}: {got} pdfs ({miss} not published under this list)")


if __name__ == "__main__":
    main()
