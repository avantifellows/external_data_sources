#!/usr/bin/env python3
"""
Stage the UDISE+ DSP microdata: portal zips -> GCS -> BigQuery staging tables.

The DSP release is ~1.7 GB of zips / ~12 GB of CSV across five academic years, so
nothing is ever loaded into pandas. Each CSV member is streamed straight out of its
zip through gzip and into GCS, then loaded into a raw, unreshaped BigQuery staging
table — one per (year, file group). All the reshaping happens afterwards in SQL
(scripts/dsp_build_bq.py), where the data already lives.

Three steps, run in this order (the default runs stage + load):

  --raw     upload the untouched portal zips to gs://.../udise/raw/dsp/<year>/
            This is the source of record: the DSP portal has no static download
            URL, so if these zips are lost the data cannot be re-fetched.
  --stage   zip member -> gzip -> gs://.../udise/staging/dsp/<year>/<group>/
  --load    that GCS prefix -> avantifellows.udise_dsp_staging.<group>_<year>

Staging tables are transient and carry a default expiry; drop them with
`dsp_build_bq.py --drop-staging` once the finished tables are built.

Column names are taken from each CSV's own header, so a new edition that adds
columns stages without a code change. The observed header of every file is written
to schemas/dsp_layouts.json, which IS committed — that is what makes a silent
upstream schema change show up as a git diff rather than as wrong numbers.

Usage:
  python3 scripts/dsp_stage.py --raw
  python3 scripts/dsp_stage.py                       # stage + load, default groups
  python3 scripts/dsp_stage.py --years 2025-26 --groups profile_data_1
  python3 scripts/dsp_stage.py --load-only
  python3 scripts/dsp_stage.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (
    BQ_LOCATION,
    BQ_PROJECT,
    DSP_GROUP_YEARS,
    DSP_GROUPS,
    DSP_STAGING_DATASET,
    DSP_STAGING_EXPIRY_DAYS,
    DSP_YEARS,
    GCS_BUCKET,
    GCS_DSP_RAW,
    GCS_DSP_STAGING,
    ROOT,
    dsp_members,
    dsp_staging_table,
    dsp_zip,
)

# The groups this ingest covers today. teacher_data / facility_data / safety are
# downloaded and registered but not yet modelled — pass them with --groups to stage
# them anyway; nothing here is group-specific except the type rule below.
DEFAULT_GROUPS = ("profile_data_1", "profile_data_2", "enrolment_data_1", "enrolment_data_2")

LAYOUTS_JSON = ROOT / "schemas" / "dsp_layouts.json"
GZ_DIR = ROOT / "raw" / "dsp" / "_staged"   # gitignored; regenerable from the zips

# The source spells the school key `psuedocode` in the 2020-21 edition and
# `pseudocode` from 2022-23 on. That one typo is fixed at the staging boundary so
# every downstream query can say `pseudocode`. Every other source spelling —
# `managment`, `urinla_girls`, `class_taugt_pre_primary_only` — is kept exactly as
# published and renamed on the way out, in dsp_build_bq.py.
RENAME_AT_STAGING = {"psuedocode": "pseudocode"}

# Counts load as INT64 so a malformed row fails the load loudly instead of landing
# as a string nobody notices. Everything else — including every DCF code — loads as
# STRING: the codes are categorical, and STRING is what stops '01' becoming 1.
INT_PREFIXES = ("cpp_", "c1_", "c2_", "c3_", "c4_", "c5_", "c6_", "c7_",
                "c8_", "c9_", "c10_", "c11_", "c12_")


def run(cmd: list[str], *, dry_run: bool, stdin=None, stdout=None) -> None:
    if dry_run:
        print(f"    [dry-run] {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True, stdin=stdin, stdout=stdout)


def read_header(zip_path: Path, member: str) -> list[str]:
    """First line of a zip member, as normalized column names."""
    proc = subprocess.Popen(["unzip", "-p", str(zip_path), member], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    raw = proc.stdout.readline().decode("utf-8-sig")
    proc.stdout.close()
    proc.wait()
    if not raw:
        raise SystemExit(f"empty or missing member: {zip_path}::{member}")
    cols = [c.strip().strip('"').lower() for c in raw.rstrip("\r\n").split(",")]
    return [RENAME_AT_STAGING.get(c, c) for c in cols]


def bq_schema(columns: list[str]) -> str:
    """BigQuery schema string: counts as INT64, everything else STRING."""
    fields = []
    for c in columns:
        is_count = any(c.startswith(p) for p in INT_PREFIXES) and c.split("_")[-1] in ("b", "g", "t")
        fields.append(f"{c}:{'INT64' if is_count else 'STRING'}")
    return ",".join(fields)


def upload_raw(years: list[str], groups: list[str], dry_run: bool) -> None:
    print(f"Raw zips → gs://{GCS_BUCKET}/{GCS_DSP_RAW}/")
    for year in years:
        for group in groups:
            if year not in DSP_GROUP_YEARS[group]:
                continue
            z = dsp_zip(year, group)
            dest = f"gs://{GCS_BUCKET}/{GCS_DSP_RAW}/{year}/{z.name}"
            print(f"  {z.name} ({z.stat().st_size / 1e6:.0f} MB) → {dest}")
            run(["gcloud", "storage", "cp", str(z), dest], dry_run=dry_run)


def stage_group(year: str, group: str, dry_run: bool, upload: bool = True) -> list[str]:
    """zip members -> local .csv.gz -> GCS. Returns the observed header.

    The gzip half needs no credentials, so `--gzip-only` can run it ahead of time
    (it is the slow, CPU-bound half) and `--load-only` can pick up afterwards.
    """
    z = dsp_zip(year, group)
    members = dsp_members(year, group)
    header = read_header(z, members[0])

    for member in members[1:]:
        other = read_header(z, member)
        if other != header:
            raise SystemExit(
                f"{z.name}: member {member} has a different header than {members[0]}.\n"
                f"  {members[0]}: {header}\n  {member}: {other}\n"
                "Shards of the same group must share a layout — stage them separately."
            )

    out_dir = GZ_DIR / year / group
    out_dir.mkdir(parents=True, exist_ok=True)
    for member in members:
        gz = out_dir / (Path(member).name + ".gz")
        if gz.exists() and gz.stat().st_size > 0:
            print(f"    · {gz.name} already staged locally, reusing")
        else:
            print(f"    · {member} → {gz.name}")
            if not dry_run:
                unzip = subprocess.Popen(["unzip", "-p", str(z), member], stdout=subprocess.PIPE)
                with gz.open("wb") as fh:
                    gzip_proc = subprocess.Popen(["gzip", "-3", "-c"], stdin=unzip.stdout, stdout=fh)
                    assert unzip.stdout is not None
                    unzip.stdout.close()
                    if gzip_proc.wait() != 0 or unzip.wait() != 0:
                        gz.unlink(missing_ok=True)
                        raise SystemExit(f"failed to extract {z}::{member}")

    if upload:
        dest = f"gs://{GCS_BUCKET}/{GCS_DSP_STAGING}/{year}/{group}/"
        print(f"    → {dest}")
        local = sorted(str(p) for p in out_dir.glob("*.csv.gz"))
        if not local and not dry_run:
            raise SystemExit(f"nothing staged under {out_dir}")
        run(["gcloud", "storage", "cp", *local, dest], dry_run=dry_run)
    return header


def ensure_staging_dataset(dry_run: bool) -> None:
    probe = subprocess.run(
        ["bq", f"--project_id={BQ_PROJECT}", "show", "--format=none", f"{BQ_PROJECT}:{DSP_STAGING_DATASET}"],
        capture_output=True,
    )
    if probe.returncode == 0:
        return
    print(f"  creating dataset {BQ_PROJECT}:{DSP_STAGING_DATASET} ({BQ_LOCATION})")
    run(["bq", f"--project_id={BQ_PROJECT}", "mk",
         f"--location={BQ_LOCATION}",
         f"--default_table_expiration={DSP_STAGING_EXPIRY_DAYS * 86400}",
         "--description=Transient raw DSP CSV loads. Built by udise/scripts/dsp_stage.py, "
         "consumed by dsp_build_bq.py, safe to delete.",
         f"{BQ_PROJECT}:{DSP_STAGING_DATASET}"], dry_run=dry_run)


def load_group(year: str, group: str, header: list[str], dry_run: bool) -> None:
    table = dsp_staging_table(year, group).replace(f"{BQ_PROJECT}.", f"{BQ_PROJECT}:", 1)
    uri = f"gs://{GCS_BUCKET}/{GCS_DSP_STAGING}/{year}/{group}/*.csv.gz"
    print(f"    {uri} → {table}")
    run(["bq", f"--project_id={BQ_PROJECT}", f"--location={BQ_LOCATION}", "load",
         "--replace", "--source_format=CSV", "--skip_leading_rows=1",
         "--allow_quoted_newlines=false", "--max_bad_records=0",
         table, uri, bq_schema(header)], dry_run=dry_run)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default=",".join(DSP_YEARS))
    ap.add_argument("--groups", default=",".join(DEFAULT_GROUPS))
    ap.add_argument("--raw", action="store_true", help="upload the source zips to GCS raw/ and exit")
    ap.add_argument("--stage-only", action="store_true", help="stage to GCS but do not load")
    ap.add_argument("--gzip-only", action="store_true",
                    help="only do the credential-free zip->gzip half, no GCS, no BQ")
    ap.add_argument("--load-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    years = [y.strip() for y in args.years.split(",") if y.strip()]
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    for y in years:
        if y not in DSP_YEARS:
            raise SystemExit(f"unknown year {y!r}; known: {', '.join(DSP_YEARS)}")
    for g in groups:
        if g not in DSP_GROUPS:
            raise SystemExit(f"unknown group {g!r}; known: {', '.join(DSP_GROUPS)}")

    if args.raw:
        upload_raw(years, groups, args.dry_run)
        return

    layouts = json.loads(LAYOUTS_JSON.read_text()) if LAYOUTS_JSON.exists() else {}
    if not args.load_only and not args.gzip_only:
        ensure_staging_dataset(args.dry_run)

    for year in years:
        for group in groups:
            if year not in DSP_GROUP_YEARS[group]:
                print(f"  – {year} {group}: not published this year, skipping")
                continue
            key = f"{year}/{group}"
            print(f"  {key}")
            if args.load_only:
                if key not in layouts:
                    raise SystemExit(f"no staged layout for {key}; run without --load-only first")
                header = layouts[key]
            else:
                header = stage_group(year, group, args.dry_run, upload=not args.gzip_only)
                layouts[key] = header
                LAYOUTS_JSON.write_text(json.dumps(layouts, indent=2, sort_keys=True) + "\n")
            if not args.stage_only and not args.gzip_only:
                load_group(year, group, header, args.dry_run)

    print("✓ done.")


if __name__ == "__main__":
    main()
