#!/usr/bin/env python3
"""
Fetch the raw AISHE Final Reports from their canonical source URLs into raw/.

Makes the source files regenerable from scratch — no manual download. Two
editions, and they are not interchangeable:

  PDF   (sources.PDF_REPORT_URLS)  2012-13 … 2023-24, all fetchable from the MoE
                                   CDN. Parsed by parse_report_pdf.py.
  Excel (sources.REPORT_URLS)      2019-20 … 2021-22, and NOT fetchable upstream:
                                   every he.nic.in workbook URL 404s and the
                                   "(Excel)" links on aishe.gov.in go to a
                                   JavaScript viewer with no static file path.
                                   Parsed by clean_aishe.py.

**GCS is the durable source of record.** Publisher URLs for Indian government
data rot — the Excel workbooks above are the live proof, and the PDF CDN paths
are opaque hashes that a site rebuild can reassign. Every raw file this pipeline
has ever used is mirrored to gs://avantifellows-external-data/aishe/raw/, so
`--from-gcs` restores raw/ regardless of what upstream is doing today. For the
Excel workbooks it is the ONLY way to get them, which makes it the default
fallback rather than a convenience: a from-scratch checkout runs
`--from-gcs` and gets a complete raw/.

Usage:
  python3 scripts/fetch.py                    # download any missing PDFs
  python3 scripts/fetch.py --force            # re-download all
  python3 scripts/fetch.py --year 2018-19     # one report
  python3 scripts/fetch.py --timeseries       # the GER / GPI series PDFs
  python3 scripts/fetch.py --from-gcs         # restore raw/ from the GCS mirror
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (BQ_PROJECT, GCS_BUCKET, GCS_PREFIX,
                     INSTITUTION_DIRECTORY_RAW_FILES, PDF_REPORT_URLS,
                     PDF_REPORTS, RAW, REPORT_URLS, REPORTS, TIMESERIES_URLS)

# Some gov.in hosts return 403 to minimal User-Agents — send full browser headers.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/pdf,application/vnd.openxmlformats-officedocument."
              "spreadsheetml.sheet,*/*",
}

# First bytes of the formats we accept. A gov.in host that has quietly moved a
# file often answers 200 with an HTML error page, which would otherwise be saved
# as a .pdf and fail much later inside the parser with a confusing message.
_MAGIC = {".pdf": b"%PDF", ".xlsx": b"PK\x03\x04"}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read()
    magic = _MAGIC.get(dest.suffix.lower())
    if magic and not body.startswith(magic):
        head = body[:200].decode("utf-8", "replace").replace("\n", " ")
        raise SystemExit(
            f"{url}\n  returned {len(body):,} bytes that are not a "
            f"{dest.suffix} file (expected to start with {magic!r}).\n"
            f"  starts with: {head!r}\n"
            f"  The URL has probably moved — check aishe.gov.in and correct it "
            f"in sources.py. Nothing was written."
        )
    dest.write_bytes(body)
    print(f"  ✓ {dest.name}  ({len(body) / 1e6:.2f} MB)  ← {url}")


def _fetch(urls: dict[str, str], paths: dict[str, Path], keys: list[str],
           force: bool) -> None:
    for key in keys:
        if key not in urls:
            raise SystemExit(f"unknown key {key!r}; known: {list(urls)}")
        dest = paths[key]
        if dest.exists() and not force:
            print(f"  • {dest.name} exists (use --force to re-download)")
            continue
        _download(urls[key], dest)


def _fetch_from_gcs(force: bool) -> None:
    """Restore raw/ from the GCS mirror — the durable copy of every raw file."""
    from google.cloud import storage

    client = storage.Client(project=BQ_PROJECT)
    bucket = client.bucket(GCS_BUCKET)
    prefix = f"{GCS_PREFIX}/raw/"
    got = 0
    for blob in client.list_blobs(bucket, prefix=prefix):
        rel = blob.name[len(prefix):]
        # Source files only. The per-sheet parquet under raw/<year>/ is
        # traceability output derived from these, not an input.
        if not rel or not rel.endswith((".xlsx", ".pdf")):
            continue
        # The institution-directory workbooks are mirrored twice — once at the top
        # of raw/ and once under raw/institution_directory/. Take the nested copy,
        # which is where sources.DirectoryTable.raw_path looks; keeping the
        # top-level one too would re-download 37 MB to a path nothing reads.
        if "/" not in rel and rel in INSTITUTION_DIRECTORY_RAW_FILES:
            continue
        dest = RAW / rel
        if dest.exists() and not force:
            print(f"  • {rel} exists (use --force to overwrite)")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        blob.download_to_filename(dest)
        got += 1
        print(f"  ✓ {rel}  ({dest.stat().st_size / 1e6:.2f} MB)  ← gs://{GCS_BUCKET}/{blob.name}")
    if not got:
        print("  (nothing new)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--year", default=None,
                    help="Fetch only this report year (e.g. 2018-19)")
    ap.add_argument("--force", action="store_true",
                    help="Re-download even if the file exists")
    ap.add_argument("--timeseries", action="store_true",
                    help="Fetch the GER / GPI time-series PDFs instead")
    ap.add_argument("--from-gcs", action="store_true",
                    help="Restore raw/ from the GCS mirror instead of upstream "
                         "(the only way to get the Excel workbooks)")
    args = ap.parse_args()

    print(f"AISHE fetch → {RAW}")
    if args.from_gcs:
        _fetch_from_gcs(args.force)
        print("✓ done.")
        return

    if args.timeseries:
        paths = {k: RAW / f"aishe_timeseries_{k}_2011_projection.pdf"
                 for k in TIMESERIES_URLS}
        _fetch(TIMESERIES_URLS, paths, list(TIMESERIES_URLS), args.force)
        print("✓ done.")
        return

    years = [args.year] if args.year else list(PDF_REPORT_URLS)
    _fetch(PDF_REPORT_URLS, PDF_REPORTS, years, args.force)

    # Only reachable if someone finds the real workbook endpoint and fills the
    # dict in; today it is empty and this loop does nothing.
    if REPORT_URLS:
        excel = [y for y in years if y in REPORT_URLS]
        _fetch(REPORT_URLS, REPORTS, excel, args.force)
    print("✓ done.")


if __name__ == "__main__":
    main()
