# CLAUDE.md — naac/

Guidance for Claude Code when working inside the `naac/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths in this file are relative to `naac/` unless otherwise noted.

## What this folder is

Ingestion pipeline for NAAC (National Assessment and Accreditation Council)
accreditation data. NAAC grades Indian higher education institutions (HEIs)
on a 0–4 CGPA scale with letter grades A++ → C. Accreditation is valid for
**5 years per cycle** (7 years for sustained top performers). The cycle number
on each row = how many full accreditation rounds an institution has completed
in its history — Cycle 1 is the first-ever assessment, Cycle 5 means ~25 years
of continuous accreditation.

Source: a single xlsx downloaded from naac.gov.in → Accreditation Status,
dated **14-Aug-2025**. Three sheets, three tables.

This follows the **josaa pattern** — raw xlsx needs real local cleaning before
staging, so there is an explicit `build_clean.py` step:

```
naac/raw/*.xlsx               (committed to repo — 1 MB, already in git)
       │
       │  scripts/build_clean.py   (rename cols, clean text, parse dates)
       ▼
naac/clean/*.parquet           (gitignored; local intermediate)
       │
       │  scripts/upload_to_gcs.py (pure upload — no transform)
       ▼
gs://avantifellows-external-data/naac/*.parquet
       │
       │  scripts/load_bq.py       (load_table_from_uri, WRITE_TRUNCATE)
       ▼
avantifellows.external_data_sources.naac_dim_*    (3 tables, asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).** It
declares `RAW`, `CLEAN`, the GCS bucket/prefix, BQ destination, and the
`TABLES` registry mapping each xlsx sheet → column renames → BQ table →
local parquet path. Everything downstream reads from there.

## Commands

```bash
# Local Python env
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Build clean parquets from the raw xlsx
.venv/bin/python scripts/build_clean.py
.venv/bin/python scripts/build_clean.py --table naac_dim_colleges   # one only
.venv/bin/python scripts/build_clean.py --dry-run                    # validate locally

# 2. Upload clean parquets to GCS
.venv/bin/python scripts/upload_to_gcs.py
.venv/bin/python scripts/upload_to_gcs.py --table naac_dim_colleges
.venv/bin/python scripts/upload_to_gcs.py --dry-run

# 3. Load GCS → BQ
.venv/bin/python scripts/load_bq.py
.venv/bin/python scripts/load_bq.py --table naac_dim_colleges
.venv/bin/python scripts/load_bq.py --dry-run
```

One-time prerequisites:
```bash
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
```

## What lives where

| Path | Committed? | Purpose |
|---|---|---|
| `raw/*.xlsx` | Yes | Source file from naac.gov.in (1 MB; small enough to commit) |
| `clean/*.parquet` | No | Built by `build_clean.py`; authoritative copy on GCS |
| `schemas/naac_dim_*.yaml` | Yes | Per-table column documentation |
| `scripts/sources.py` | Yes | All config: paths, BQ dest, table registry, column renames |
| `scripts/build_clean.py` | Yes | Raw xlsx → clean parquets (rename, text clean, date parse) |
| `scripts/upload_to_gcs.py` | Yes | Uploads `clean/` to GCS — no transformation |
| `scripts/load_bq.py` | Yes | Loads from GCS to BQ with WRITE_TRUNCATE |
| `README.md` | Yes | Setup + pipeline overview |

## BQ schema (what `load_bq.py` produces)

Three tables in `avantifellows.external_data_sources`. Authoritative
column-level docs in [`schemas/*.yaml`](schemas/).

| Table | Rows | Grain | Sheet |
|---|---:|---|---|
| `naac_dim_universities` | 497 | `aishe_id` | Universities |
| `naac_dim_colleges` | 7,566 | `aishe_id` | Colleges |
| `naac_dim_transition_autonomous_colleges` | 290 | `hei_name` | Transition Autonomous Colleges |

All tables carry a `data_as_of` DATE column (2025-08-14) recording the
publication date of the source file.

## Design calls worth knowing before you change them

- **Raw xlsx is committed.** At 1 MB it's small enough for git. Contrast
  with NIRF/JoSAA where raw files are gitignored. If NAAC publishes a new
  release, replace the xlsx and update `DATA_AS_OF` in `sources.py`.
- **Three separate tables, not one combined.** Universities and Colleges
  share 9 columns; Colleges has one extra (`affiliating_university`).
  Transition Autonomous Colleges has a completely different schema — no
  CGPA, no grade, no AISHE-Id — and merging it with the others would
  introduce misleading NULLs. Keep them separate.
- **`build_clean.py` owns all transformation.** `upload_to_gcs.py` is a
  pure uploader — it reads `clean/*.parquet` and pushes to GCS with no
  modification. Never add transformation logic to the upload or load steps.
- **`data_as_of` is a constant, not derived.** It's set in `sources.py`
  as `DATA_AS_OF = datetime.date(2025, 8, 14)` and stamped on every row
  by `build_clean.py`. Update it when loading a newer NAAC release.
- **WRITE_TRUNCATE on every load.** NAAC publishes a fresh snapshot (not
  a delta). Full replace is correct and idempotent.

## Pitfalls

- **Transition Autonomous Colleges have no AISHE-Id or Track-Id.** The
  only join path to other datasets (NIRF, JoSAA) is fuzzy name matching.
  Don't attempt exact joins on `hei_name`.
- **`hei_name` in the Transition sheet embeds the address.** The source
  has no separate address column for this sheet; the full postal address
  follows the institution name after `(Autonomous),`. `build_clean.py`
  collapses embedded newlines but does not split name from address.
- **~61 Transition Autonomous Colleges have already expired** (`extended_validity_upto`
  < 2025-08-14). Filter `WHERE extended_validity_upto >= CURRENT_DATE()`
  for institutions with current accreditation only.
- **`date_of_declaration` staleness.** A grade from 2020 is 5 years old
  even though the file was downloaded in 2025. Use `data_as_of` alongside
  `date_of_declaration` to reason about freshness.
- **Don't compare CGPA across Universities and Colleges directly** without
  noting that NAAC uses different criterion weightages for each type.
- **`aishe_id` format differs by type.** `U-XXXX` = university,
  `C-XXXXX` = college. The prefix is load-bearing if you're joining on it.
