"""
NIRF "Data Submitted by Institution" PDFs that institutes publish on their
OWN websites — the ones nirfindia.org never hosts.

Why: fetch_dcs.py gets the DCS PDF of every institute NIRF lists (ranked,
banded, ex-ranked), probing the CDN by IR-id. Everyone else — most state
government engineering colleges (Jabalpur, Rewa, Ujjain, SATI Vidisha …) —
submits the same form but NIRF hosts nothing: their CDN URLs 404 for every
edition. NIRF does require each participant to publish its submission on its
own website, and those copies are the identical DCS PDF (same layout, same
"[IR-E-C-36192]" id = AISHE code). parse_dcs.py reads them unchanged.
Institutes also post the current edition before NIRF publishes it (2026
submissions were up in Oct 2026 while nirfindia.org had none).

The manifest — nirf/institute_website_pdfs.csv, committed — is the record:
one row per PDF with the URL, what page 1 says (IR-id, discipline, edition),
how it was found (crawl / search / manual), fetch date and sha256. PDFs land
in raw/dcs/website/<Discipline>/<edition>/<IR-id>.pdf (gitignored; GCS is
canonical via upload_to_gcs.py --dcs-raw).

Rules:
  - A PDF is accepted only if page 1 is a DCS page with an IR-id.
  - Gap-filling only: an institute NIRF's CDN hosts in a discipline (any
    edition) is skipped, so ranked institutes keep one consistent NIRF
    series. parse_dcs.py also skips any website copy NIRF hosts.
  - An edition later than the current year is a misprint: rejected.
  - Edition: "Submitted Institute Data for NIRF'2026'" on page 1. Older
    layouts (2019-2023) don't print it; then edition = end year of the latest
    graduating academic year + 1 (a 2023 submission reports grads up to
    2021-22), and edition_inferred = True.

Usage:
  python3 scripts/fetch_website_dcs.py discover --state "Madhya Pradesh"
      crawl the websites (from AISHE) of the state's government, aided and
      university engineering colleges; append the DCS PDFs found
  python3 scripts/fetch_website_dcs.py add URL [URL ...] [--found-by search]
      validate and append PDFs found by hand
  python3 scripts/fetch_website_dcs.py fetch
      download every manifest PDF missing locally, check its sha256
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import hashlib
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_PROJECT, DCS_RAW, WEBSITE_MANIFEST, WEBSITE_PDFS

CDN_PDFS = DCS_RAW / "pdf"
FIELDS = ["url", "institute_id", "discipline", "edition_year", "edition_inferred",
          "state", "found_by", "fetched_on", "sha256", "note"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
# college sites routinely serve broken or mismatched certificates (Jabalpur
# EC's cert names another domain); these are public documents, read-only
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

ID_RE = re.compile(r"\b(IR-[A-Z]-[A-Z]{1,2}-\d+)\b")
DISC_RE = re.compile(r"Data Capturing System:\s*([A-Za-z ]+?)\s*$", re.M)
EDITION_RE = re.compile(r"NIRF\W{0,3}(20\d\d)")
AY_RE = re.compile(r"\b(20\d\d)-(\d\d)\b")
# NIRF's discipline names → the directory names fetch_dcs.py uses
DISCIPLINES = {"engineering": "Engineering", "medical": "Medical", "university": "University",
               "college": "College", "law": "Law"}


def _get(url: str, limit: int = 15_000_000, timeout: int = 30) -> tuple[str, bytes]:
    try:
        req = urllib.request.Request(url.replace(" ", "%20"), headers=UA)
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.geturl(), r.read(limit)
    except Exception:
        return url, b""


def read_page1(pdf: bytes) -> dict | None:
    """What page 1 of a DCS PDF says, or None if it isn't one."""
    if pdf[:4] != b"%PDF":
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(pdf)
        f.flush()
        p1 = subprocess.run(["pdftotext", "-l", "1", f.name, "-"],
                            capture_output=True, text=True).stdout
        allp = subprocess.run(["pdftotext", "-l", "3", f.name, "-"],
                              capture_output=True, text=True).stdout
    ir, disc = ID_RE.search(p1), DISC_RE.search(p1)
    if not ir or not disc:
        return None
    d = DISCIPLINES.get(disc.group(1).strip().lower())
    if d is None:
        return {"skip": f"discipline {disc.group(1).strip()!r} not parsed"}
    ed = EDITION_RE.search(p1)
    inferred = ed is None
    if ed:
        edition = int(ed.group(1))
    else:
        years = [int(a) + 1 for a, _ in AY_RE.findall(allp)]
        if not years:
            return None
        edition = max(years) + 1
    return {"institute_id": ir.group(1), "discipline": d, "edition_year": edition,
            "edition_inferred": inferred}


def load_manifest() -> list[dict]:
    if not WEBSITE_MANIFEST.exists():
        return []
    with open(WEBSITE_MANIFEST, newline="") as fh:
        return list(csv.DictReader(fh))


def save_manifest(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda r: (r["state"], r["institute_id"], r["discipline"],
                                       int(r["edition_year"])))
    with open(WEBSITE_MANIFEST, "w", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS)
        w.writeheader()
        w.writerows(rows)


def local_path(r: dict, root: Path = WEBSITE_PDFS) -> Path:
    return root / r["discipline"] / str(r["edition_year"]) / f"{r['institute_id']}.pdf"


def accept(url: str, pdf: bytes, state: str, found_by: str, manifest: list[dict]) -> str:
    """Validate one downloaded PDF and append it; returns what happened."""
    info = read_page1(pdf)
    if info is None:
        return "not a DCS PDF"
    if "skip" in info:
        return info["skip"]
    key = (info["institute_id"], info["discipline"], str(info["edition_year"]))
    if any((r["institute_id"], r["discipline"], r["edition_year"]) == key for r in manifest):
        return "already in manifest"
    row = {"url": url, **{k: str(v) for k, v in info.items()}, "state": state,
           "found_by": found_by, "fetched_on": date.today().isoformat(),
           "sha256": hashlib.sha256(pdf).hexdigest(), "note": ""}
    if info["edition_year"] > date.today().year:
        return f"edition {info['edition_year']} is in the future: misprint, check by hand"
    # gap-filling only: an institute NIRF hosts in this discipline keeps its
    # NIRF series, even where its website has a newer edition — a 2026 copy
    # for a few ranked institutes would leave the rest on 2025
    if any(CDN_PDFS.glob(f"{info['discipline']}/*/{info['institute_id']}.pdf")):
        return "NIRF hosts this institute already"
    dest = local_path(row)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(pdf)
    manifest.append(row)
    return f"added {key}"


# ── discovery ────────────────────────────────────────────────────────────────

def _links(base: str, html: bytes):
    for href, text in re.findall(rb'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        yield (urllib.parse.urljoin(base, href.decode("latin1").strip()),
               re.sub(rb"<[^>]+>", b" ", text).decode("latin1"))


def crawl(site: str) -> list[str]:
    """PDF links reachable from the homepage within two hops of anything
    mentioning NIRF (plus the usual /nirf paths)."""
    if not site or site.strip() in ("-", "NA"):
        return []
    s = site.strip()
    s = s if s.startswith("http") else "http://" + s.lower()
    base, html = _get(s, 2_000_000)
    if not html:
        return []
    queue = [(u, t) for u, t in _links(base, html)
             if re.search(r"nirf|mandatory|disclosure|ranking", u + t, re.I)]
    queue += [(urllib.parse.urljoin(base + "/", g), "") for g in ("nirf", "NIRF", "nirf.php", "nirf.html")]
    seen, pdfs = set(), []
    for _ in range(2):
        nxt = []
        for u, _t in queue[:12]:
            if u in seen:
                continue
            seen.add(u)
            if u.lower().split("?")[0].endswith(".pdf"):
                pdfs.append(u)
                continue
            b2, h2 = _get(u, 2_000_000)
            for x, tx in _links(b2, h2):
                if x.lower().split("?")[0].endswith(".pdf") and re.search(r"nirf|engg|engineering|dcs|20\d\d", x + tx, re.I):
                    pdfs.append(x)
                elif re.search(r"nirf", x + tx, re.I):
                    nxt.append((x, tx))
        queue = nxt
    return list(dict.fromkeys(pdfs))[:25]


def targets(state: str) -> list[tuple[str, str, str]]:
    """(aishe_code, name, website) for the state's government, aided and
    university engineering colleges and the universities that teach
    engineering, from AISHE."""
    from google.cloud import bigquery
    q = f"""
    SELECT aishe_code, name, website FROM `{BQ_PROJECT}.external_data_sources.aishe_dim_colleges`
    WHERE state = @state
      AND management IN ('State Government', 'Private Aided (Government Aided)', 'University',
                         'Central Government', 'Local Body')
      AND REGEXP_CONTAINS(LOWER(name), r'engineering|institute of technology|technological|technology (&|and) science')
      AND NOT REGEXP_CONTAINS(LOWER(name), r'polytechnic|pharm|architecture|management|nursing|agricultur|diploma')
    UNION ALL
    SELECT aishe_code, name, website FROM `{BQ_PROJECT}.external_data_sources.aishe_dim_universities`
    WHERE state = @state
      AND university_type IN ('State Public University', 'Central University', 'Deemed University-Government',
                              'Deemed University-Government Aided', 'Institute under State Legislature Act',
                              'Institute of National Importance')"""
    job = bigquery.Client(project=BQ_PROJECT).query(
        q, job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("state", "STRING", state)]))
    return [(r.aishe_code, r.name, r.website) for r in job.result()]


def discover(state: str) -> None:
    manifest = load_manifest()
    t = targets(state)
    print(f"{len(t)} candidate institutes in {state} (AISHE)")
    with cf.ThreadPoolExecutor(8) as ex:
        found = dict(zip([c for c, _, _ in t], ex.map(lambda x: crawl(x[2]), t)))
    urls = list(dict.fromkeys(u for v in found.values() for u in v))
    print(f"{len(urls)} PDF links to check")
    with cf.ThreadPoolExecutor(8) as ex:
        bodies = list(ex.map(_get, urls))
    added = 0
    for url, (_, pdf) in zip(urls, bodies):
        what = accept(url, pdf, state, "crawl", manifest)
        if what.startswith("added"):
            added += 1
            print(f"  {what}  {url}")
    save_manifest(manifest)
    print(f"{added} added; manifest now {len(manifest)} PDFs")


def add(urls: list[str], state: str, found_by: str) -> None:
    manifest = load_manifest()
    for url in urls:
        _, pdf = _get(url)
        print(f"  {accept(url, pdf, state, found_by, manifest)}  {url}")
    save_manifest(manifest)


def fetch() -> None:
    """Download every manifest PDF missing locally; a changed file is
    reported, not overwritten (the manifest's sha256 is what was parsed)."""
    for r in load_manifest():
        dest = local_path(r)
        if dest.exists():
            continue
        _, pdf = _get(r["url"])
        if hashlib.sha256(pdf).hexdigest() != r["sha256"]:
            print(f"  ✗ {r['institute_id']} {r['edition_year']}: the file at {r['url']} changed or "
                  f"is gone — restore from gs://…/nirf/raw/dcs/ (upload_to_gcs.py --dcs-raw)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(pdf)
        print(f"  fetched {dest.relative_to(DCS_RAW)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--state", required=True)
    a = sub.add_parser("add")
    a.add_argument("urls", nargs="+")
    a.add_argument("--state", required=True)
    a.add_argument("--found-by", default="search", choices=["search", "manual", "crawl"])
    sub.add_parser("fetch")
    args = ap.parse_args()
    if args.cmd == "discover":
        discover(args.state)
    elif args.cmd == "add":
        add(args.urls, args.state, args.found_by)
    else:
        fetch()


if __name__ == "__main__":
    main()
