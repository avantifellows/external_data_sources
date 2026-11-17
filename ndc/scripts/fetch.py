#!/usr/bin/env python3
"""
Save NDC's BDS college list and every college's details page into
raw/<today>/ (list.html, details/<row>.html, index.json: row -> details id).

Each details link is an ASP.NET postback on the list page; the server answers
with a redirect to the details page, which is then fetched. Resumable: pages
already saved are skipped.

Usage:
  python3 scripts/fetch.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import DETAILS_URL, LIST_URL, PAUSE_S, RAW

HEADERS = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")}


def main() -> None:
    out = RAW / dt.date.today().isoformat()
    (out / "details").mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update(HEADERS)

    r = s.get(LIST_URL, timeout=120)
    r.raise_for_status()
    (out / "list.html").write_text(r.text, encoding="utf-8")
    soup = BeautifulSoup(r.text, "lxml")
    form = {i["name"]: i.get("value", "") for i in soup.find_all("input", type="hidden") if i.get("name")}
    buttons = [i["name"] for i in soup.find_all("input") if str(i.get("name", "")).endswith("imgbtnEdit1")]
    total = re.search(r"Total Records\s*:?\s*(\d+)", soup.get_text(" "))
    print(f"list: {len(buttons)} colleges (page says {total.group(1) if total else '?'})")

    idx_file = out / "index.json"
    index = json.loads(idx_file.read_text()) if idx_file.exists() else {}
    for n, btn in enumerate(buttons, 1):
        row = re.search(r"\$ctl(\d+)\$", btn).group(1)
        page = out / "details" / f"{row}.html"
        if page.exists() and row in index:
            continue
        p = s.post(LIST_URL, data={**form, btn + ".x": "5", btn + ".y": "5"},
                   timeout=120, allow_redirects=False)
        loc = p.headers.get("Location", "")
        m = re.search(r"Id=([^&]+)", loc)
        if p.status_code != 302 or not m:
            raise SystemExit(f"row {row}: no details redirect (HTTP {p.status_code})")
        cid = unquote(m.group(1))
        time.sleep(PAUSE_S)
        d = s.get(DETAILS_URL.format(id=m.group(1)), timeout=120)
        d.raise_for_status()
        page.write_text(d.text, encoding="utf-8")
        index[row] = cid
        idx_file.write_text(json.dumps(index, indent=1))
        time.sleep(PAUSE_S)
        if n % 25 == 0:
            print(f"  {n}/{len(buttons)}")
    print(f"saved {len(index)} details pages → {out}")


if __name__ == "__main__":
    main()
