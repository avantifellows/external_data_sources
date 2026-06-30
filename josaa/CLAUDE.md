# CLAUDE.md — josaa/

Guidance for Claude Code when working inside the `josaa/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

All paths relative to `josaa/` unless noted.

## What this folder is

A **light-parse** ingestion pipeline for JoSAA engineering counselling cutoffs
(IIT/NIT/IIIT/GFTI), 2016 → latest, all rounds, all seat buckets. The raw is
already tabular (per-round CSVs from the JoSAA portal), so `build_clean.py`
only unions them, normalises column names to snake_case, parses the
preparatory-rank encoding, and types the columns.

## The neutral-fact principle (read before adding columns)

This source carries **only what JoSAA publishes**. It was deliberately kept
separate from any Avanti analytical layer:

| Stays in `josaa/` (neutral fact) | Stays in downstream enrichment (Avanti domain) |
|---|---|
| institute (as published), program, quota, seat_type, gender | canonical `college_id`, canonical name, state |
| opening/closing rank, prep flags, year, round | `salary_tier`, `college_type`, NIRF salary, top-200 flags |

Do not add salary tiers, college_type, or canonical-id columns here. If an
analysis needs them, join this fact to the College DB / AISHE data downstream.

## Upstream

Raw `<year>_R<round>.csv` files come from two scraper scripts in the
`avantifellows/futures-v2` repo (`josaa/scrape/scripts/01_scrape_archive.py`
and `02_scrape_current.py`). Those scripts hit the public JoSAA portal
directly — no auth needed. On a new JoSAA cycle: run the scrapers, copy
their `extracted_data/raw/*.csv` into `josaa/raw/` here, rebuild + reload.

## Commands

See [README.md](README.md). Quick path:
`build_clean.py` → `upload_to_gcs.py` → `load_bq.py`. Each takes `--dry-run`.

## BQ output

One table in `avantifellows.external_data_sources`:

| Table | Rows | Grain | Clustering |
|---|---:|---|---|
| `josaa_fact_cutoffs` | 464,496 | (institute, program, quota, seat_type, gender, year, round) | year, round, seat_type |

Authoritative column docs: [`schemas/josaa_fact_cutoffs.yaml`](schemas/josaa_fact_cutoffs.yaml).

## Design decisions worth knowing before changing them

- **All rounds, not just final.** The fact is the full per-round union (464,496
  rows) with `round` as a real dimension. Final-round / MAX-closing views are
  analyst derivations computed downstream, not extra tables here.
- **Ranks are INTEGER, prep is a flag.** JoSAA's trailing-`P` preparatory
  encoding is split into (integer rank, `*_is_preparatory` bool). Never store
  the raw `'50P'` string — it breaks numeric comparison. Prep and main-list
  ranks are different scales; never threshold across them.
- **`institute` is the raw portal string, not a canonical id.** It varies
  across years. A `josaa_dim_institute` (canonical id + institute_type + state,
  no Avanti opinion) is a sensible follow-up table — ship it separately.
- **WRITE_TRUNCATE, overwrite-in-place.** A new cycle replaces the whole
  table. JoSAA archives historical cycles unchanged, so re-running is safe.

## Pitfalls

- **Don't commit `raw/` or `clean/`.** `.gitignore` enforces it; GCS is the
  authoritative copy.
- **Don't mix rank spaces.** IITs = JEE Advanced; NITs/IIITs/GFTIs = JEE
  Main. The institute determines which. Documented in the schema.
- **Don't sum across `round`.** Each (year, round) is a full snapshot.
- **Don't equality-match `institute`.** Names drift across years — use
  keyword LIKE/REGEXP.
- **Don't load to BQ without an explicit go.** Stage parquet to GCS first;
  load to BQ only post-approval / post-merge.
