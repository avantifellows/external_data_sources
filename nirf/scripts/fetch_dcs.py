"""
Fetch NIRF first-party sources: ranking pages + per-institute DCS PDFs.

Two things come off nirfindia.org, both official:

1. RANKING PAGES (Engineering 2016-2025, Medical 2018-2025, + rank-band
   pages 101-150/151-200 from 2020 and 201-300 from 2024). Saved verbatim
   under raw/dcs/pages/, then parsed into extracted/nirf_rankings_official.csv
   by parse_dcs.py. These replace the Dataful-sourced rankings rows for the
   disciplines/years we cover.

2. DCS PDFs — "Data Submitted by Institution", one small PDF per institute
   per edition, hosted on the CDN at a deterministic URL:
       https://www.nirfindia.org/nirfpdfcdn/{year}/pdf/{disc}/{IR-id}.pdf
   The CDN serves 2019-2025 only (2018-and-earlier 404 on this path), and
   hosts PDFs for MORE institutes than the ranking pages link: rank-band and
   formerly-ranked institutes have live-but-unlinked PDFs (verified: PEC,
   NIT Uttarakhand, NIT Sikkim all 404 on every page yet serve 2025 PDFs).
   So discovery is: harvest every IR-id ever linked on any page, union in
   the extra seed lists (historical BQ ids + Amogh's AISHE-matched list),
   then PROBE the CDN for every (candidate, year) with a 4-byte range GET —
   206 means the PDF exists, 404 means it doesn't. Unranked participants
   (the ~1,585-name "ALL" page carries no ids or links) are out of scope.

Probe etiquette: ~16 concurrent range GETs, full download only on a 206.
Everything is idempotent — existing valid files are skipped, so re-running
after a network hiccup only fills the holes.

Usage:
  python3 scripts/fetch_dcs.py                 # pages + probe + download, all
  python3 scripts/fetch_dcs.py --discipline Medical
  python3 scripts/fetch_dcs.py --pages-only
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "raw" / "dcs" / "pages"
PDFS = ROOT / "raw" / "dcs" / "pdf"
SEEDS = ROOT / "raw" / "dcs" / "seeds"

BASE = "https://www.nirfindia.org"
UA = {"User-Agent": "Mozilla/5.0 (compatible; AvantiFellows data pipeline)"}

# page name, CDN dir and IR prefix per discipline; ranking-page years vs CDN
# years differ (pages go back further than the PDF CDN).
DISCIPLINES = {
    "Engineering": {
        "page": "EngineeringRanking",
        "cdn_dir": "Engineering",
        "prefix": "IR-E",
        "page_years": range(2016, 2026),
        "cdn_years": range(2019, 2026),
    },
    "Medical": {
        "page": "MedicalRanking",
        "cdn_dir": "Medical",
        "prefix": "IR-D",
        "page_years": range(2018, 2026),
        "cdn_years": range(2019, 2026),
    },
}
# band-page suffixes to try per year; absent ones 404 and are skipped
BAND_SUFFIXES = ["100", "150", "200", "250", "300"]

# modern (2019+) id letters seen in the wild: U, C, I, N (AIIMS), S
ID_RE = re.compile(r"IR-[A-Z]-[UCINS]{1,2}-\d+")


def _get(url: str, timeout: int = 30) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def _probe(url: str, timeout: int = 20) -> bool:
    """4-byte range GET; the CDN answers 206 for PDFs that exist, 404 not.
    (HEAD is not supported — it 404s even for URLs a GET serves.)"""
    req = urllib.request.Request(url, headers={**UA, "Range": "bytes=0-3"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 206 and r.read(4) == b"%PDF"
    except Exception:
        return False


def fetch_pages(disc: str) -> None:
    cfg = DISCIPLINES[disc]
    outdir = PAGES / disc
    outdir.mkdir(parents=True, exist_ok=True)
    for year in cfg["page_years"]:
        for suffix in [""] + BAND_SUFFIXES + ["ALL"]:
            name = f"{cfg['page']}{suffix}.html"
            out = outdir / f"{year}_{name}"
            if out.exists() and out.stat().st_size > 0:
                continue
            status, body = _get(f"{BASE}/Rankings/{year}/{name}")
            if status == 200 and body:
                out.write_bytes(body)
                print(f"  page  {year} {disc} {suffix or 'main'}  {len(body):,}B")
            time.sleep(0.2)


def candidate_ids(disc: str) -> list[str]:
    """Every IR-id ever seen on a saved page for this discipline, plus any
    extra seed files (raw/dcs/seeds/{disc}_*.txt, one bare code per line,
    e.g. 'U-0080'). Provenance of the seed files is recorded in sources.py."""
    cfg = DISCIPLINES[disc]
    ids: set[str] = set()
    for f in (PAGES / disc).glob("*.html"):
        for m in ID_RE.findall(f.read_text(errors="ignore")):
            if m.startswith(cfg["prefix"] + "-"):
                ids.add(m)
    for f in SEEDS.glob(f"{disc}_*.txt") if SEEDS.exists() else []:
        for line in f.read_text().splitlines():
            code = line.strip()
            if re.fullmatch(r"[UCINS]{1,2}-\d+", code):
                ids.add(f"{cfg['prefix']}-{code}")
    return sorted(ids)


def _canary_ok(disc: str, year: int) -> bool:
    """The CDN rate-limits aggressive clients by answering 404 to EVERYTHING
    (verified: page-linked, previously-200 URLs go 404 during a block). Before
    each year's sweep, probe one URL we know exists — a PDF the ranking page
    itself links. If the canary fails, wait it out rather than recording a
    year of false misses."""
    cfg = DISCIPLINES[disc]
    for f in sorted((PAGES / disc).glob("*.html"), reverse=True):
        m = re.search(rf"nirfpdfcdn/(\d{{4}})/pdf/{cfg['cdn_dir']}/({ID_RE.pattern})\.pdf",
                      f.read_text(errors="ignore"))
        if m:
            return _probe(f"{BASE}/nirfpdfcdn/{m.group(1)}/pdf/{cfg['cdn_dir']}/{m.group(2)}.pdf")
    return True  # no known-good URL to test with


def fetch_pdfs(disc: str, workers: int = 6) -> None:
    cfg = DISCIPLINES[disc]
    cands = candidate_ids(disc)
    if not cands:
        sys.exit(f"no candidate ids for {disc} — run pages first")
    print(f"{disc}: {len(cands)} candidate institute ids")
    for year in cfg["cdn_years"]:
        waited = 0
        while not _canary_ok(disc, year):
            if waited >= 3600:
                sys.exit("CDN still rate-limiting after an hour — try later")
            print("  canary 404s (rate-limited) — sleeping 5 min", flush=True)
            time.sleep(300)
            waited += 300
        outdir = PDFS / disc / str(year)
        outdir.mkdir(parents=True, exist_ok=True)

        def one(ir_id: str) -> tuple[str, str]:
            out = outdir / f"{ir_id}.pdf"
            if out.exists() and out.read_bytes()[:4] == b"%PDF":
                return ir_id, "have"
            url = f"{BASE}/nirfpdfcdn/{year}/pdf/{cfg['cdn_dir']}/{ir_id}.pdf"
            if not _probe(url):
                return ir_id, "miss"
            status, body = _get(url)
            if status == 200 and body[:4] == b"%PDF":
                out.write_bytes(body)
                return ir_id, "new"
            return ir_id, "err"

        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(one, cands))
        counts = {k: sum(1 for _, v in results if v == k)
                  for k in ("have", "new", "miss", "err")}
        print(f"  {year}: {counts['have']+counts['new']} pdfs "
              f"({counts['new']} new, {counts['miss']} not on cdn"
              + (f", {counts['err']} ERRORS — rerun" if counts["err"] else "")
              + ")")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discipline", choices=list(DISCIPLINES), default=None)
    ap.add_argument("--pages-only", action="store_true")
    args = ap.parse_args()
    discs = [args.discipline] if args.discipline else list(DISCIPLINES)
    for d in discs:
        fetch_pages(d)
    if not args.pages_only:
        for d in discs:
            fetch_pdfs(d)


if __name__ == "__main__":
    main()
