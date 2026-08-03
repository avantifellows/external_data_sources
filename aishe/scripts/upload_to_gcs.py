#!/usr/bin/env python3
"""
Upload AISHE data to GCS.

Uploads:
  - Source reports as-is — the durable mirror (see below)
      gs://avantifellows-external-data/aishe/raw/aishe_<year>_final_report.{xlsx,pdf}
  - Raw Final Report sheets → parquet (for traceability; NOT loaded to BQ)
      gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet
  - Raw institution directory xlsx files (as-is, for archival)
      gs://avantifellows-external-data/aishe/raw/institution_directory/<file>.xlsx
  - Clean parquets → GCS (these are what load_bq.py loads)
      gs://avantifellows-external-data/aishe/clean/<table>.parquet

**Why the source reports are uploaded, not just their parsed sheets.** Publisher
URLs for Indian government data rot: every he.nic.in Excel URL this pipeline
once used now 404s, and the PDF CDN paths are opaque hashes a site rebuild can
reassign. The bucket copy is therefore the source of record, and
`fetch.py --from-gcs` restores raw/ from exactly these paths. Uploading only the
derived parquet would leave the originals unrecoverable — which is the situation
the 2019-22 workbooks were already in.

Run clean_aishe.py / build_institution_directory.py first to produce
clean/*.parquet before uploading clean files.

Note: a partial build (clean_aishe.py --allow-missing-excel) writes
higher_ed.partial.parquet, which is not in TABLES and so can never be uploaded.

Usage:
  python3 scripts/upload_to_gcs.py                 # sources + raw + clean
  python3 scripts/upload_to_gcs.py --sources-only  # just mirror the reports
  python3 scripts/upload_to_gcs.py --raw-only
  python3 scripts/upload_to_gcs.py --clean-only
  python3 scripts/upload_to_gcs.py --dry-run       # show plan only
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (GCS_BUCKET, GCS_PREFIX, INSTITUTION_DIRECTORY_RAW_FILES,
                     PDF_REPORTS, PDF_TABLES, RAW, RAW_SHEETS, REPORTS, TABLES,
                     RawSheet, Table)


def _resolve_sheet(rs: RawSheet) -> str:
    """Find the actual sheet name (AISHE sheet names vary by trailing space)."""
    if not rs.workbook.exists():
        raise SystemExit(f"missing raw workbook: {rs.workbook}")
    want = rs.stem
    for name in pd.ExcelFile(rs.workbook).sheet_names:
        if name.replace(" ", "").lower() == want:
            return name
    raise SystemExit(f"sheet {rs.sheet!r} not found in {rs.workbook.name}")


def upload_raw(client, dry_run: bool) -> None:
    print("Raw → gs://{}/aishe/raw/ ...".format(GCS_BUCKET))
    for rs in RAW_SHEETS:
        actual = _resolve_sheet(rs)
        df = pd.read_excel(rs.workbook, sheet_name=actual, header=None, dtype=str)
        msg = f"{rs.year}/{actual} ({len(df):,}x{len(df.columns)}) → {rs.gcs_uri}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        client.bucket(GCS_BUCKET).blob(rs.gcs_path).upload_from_file(
            buf, content_type="application/octet-stream"
        )
        print(f"  ✓ {msg}")


def upload_source_reports(client, dry_run: bool) -> None:
    """Mirror the source report files themselves to GCS, byte-for-byte.

    These paths are what fetch.py --from-gcs reads back, so the naming here and
    there must stay in step.
    """
    print(f"Source reports → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/ ...")
    wanted = list(REPORTS.values()) + list(PDF_REPORTS.values()) + sorted(
        RAW.glob("aishe_timeseries_*.pdf"))
    for path in wanted:
        if not path.exists():
            print(f"  [skip] {path.name} not in raw/ — "
                  f"run fetch.py (or fetch.py --from-gcs) first")
            continue
        gcs_path = f"{GCS_PREFIX}/raw/{path.name}"
        msg = (f"{path.name} ({path.stat().st_size / 1e6:.2f} MB) → "
               f"gs://{GCS_BUCKET}/{gcs_path}")
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_filename(str(path))
        print(f"  ✓ {msg}")


def upload_pdf_tables(client, dry_run: bool) -> None:
    """Parsed PDF tables → raw/<year>/<label>.parquet, for traceability.

    The PDF counterpart of upload_raw: it records what the parser actually read
    out of each report, so a later disagreement can be traced to the extraction
    without re-running it.
    """
    print(f"PDF table extracts → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/<year>/ ...")
    import pdfplumber

    import parse_report_pdf

    by_year: dict[str, list] = {}
    for t in PDF_TABLES:
        by_year.setdefault(t.year, []).append(t)
    for year, tables in sorted(by_year.items()):
        if not PDF_REPORTS[year].exists():
            print(f"  [skip] {year} PDF not in raw/")
            continue
        with pdfplumber.open(PDF_REPORTS[year]) as pdf:
            for t in tables:
                pages = parse_report_pdf._find_pages(pdf, t.title_re, year)
                rows = parse_report_pdf.READERS[t.cut](
                    pdf, year, pages, t.metric, False)
                gcs_path = f"{GCS_PREFIX}/raw/{year}/{t.label.lower()}.parquet"
                msg = f"{year}/{t.label} ({len(rows):,} rows) → gs://{GCS_BUCKET}/{gcs_path}"
                if dry_run:
                    print(f"  [dry-run] {msg}")
                    continue
                buf = io.BytesIO()
                pd.DataFrame(rows).to_parquet(buf, index=False)
                buf.seek(0)
                client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_file(
                    buf, content_type="application/octet-stream")
                print(f"  ✓ {msg}")


def upload_institution_directory_raw(client, dry_run: bool) -> None:
    print(f"Institution directory raw xlsx → gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/institution_directory/ ...")
    for filename in INSTITUTION_DIRECTORY_RAW_FILES:
        path = RAW / "institution_directory" / filename
        if not path.exists():
            print(f"  [skip] {filename} not found in raw/institution_directory/ — download from dashboard first")
            continue
        size_kb = path.stat().st_size // 1024
        gcs_path = f"{GCS_PREFIX}/raw/institution_directory/{filename}"
        msg = f"{filename} ({size_kb} KB) → gs://{GCS_BUCKET}/{gcs_path}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        client.bucket(GCS_BUCKET).blob(gcs_path).upload_from_filename(str(path))
        print(f"  ✓ {msg}")


def upload_clean(client, dry_run: bool, strict: bool = False) -> None:
    print("Clean → gs://{}/aishe/clean/ ...".format(GCS_BUCKET))
    for t in TABLES:
        if not t.local_path.exists():
            if strict:
                raise SystemExit(
                    f"{t.parquet} not found — run the relevant build script first.\n"
                    f"Use --clean-only to upload a partial set."
                )
            print(f"  [skip] {t.parquet} not found — run the relevant build script first")
            continue
        size_mb = t.local_path.stat().st_size / 1e6
        msg = f"{t.parquet} ({size_mb:.2f} MB) → {t.gcs_uri}"
        if dry_run:
            print(f"  [dry-run] {msg}")
            continue
        client.bucket(GCS_BUCKET).blob(t.gcs_path).upload_from_filename(
            str(t.local_path), content_type="application/octet-stream"
        )
        print(f"  ✓ {msg}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--raw-only", action="store_true", help="Upload only the Final Report raw sheets")
    group.add_argument("--clean-only", action="store_true", help="Upload only the clean tables")
    group.add_argument("--institution-directory-raw-only", action="store_true",
                       help="Upload only the institution directory xlsx files")
    group.add_argument("--sources-only", action="store_true",
                       help="Upload only the source report files (the durable mirror)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan; don't upload")
    args = ap.parse_args()

    client = None
    if not args.dry_run:
        from google.cloud import storage
        client = storage.Client()

    if args.raw_only:
        upload_raw(client, args.dry_run)
        upload_pdf_tables(client, args.dry_run)
        upload_institution_directory_raw(client, args.dry_run)
    elif args.clean_only:
        upload_clean(client, args.dry_run)
    elif args.institution_directory_raw_only:
        upload_institution_directory_raw(client, args.dry_run)
    elif args.sources_only:
        upload_source_reports(client, args.dry_run)
    else:
        upload_source_reports(client, args.dry_run)
        upload_raw(client, args.dry_run)
        upload_pdf_tables(client, args.dry_run)
        upload_institution_directory_raw(client, args.dry_run)
        upload_clean(client, args.dry_run, strict=True)
    print("✓ done.")


if __name__ == "__main__":
    main()
