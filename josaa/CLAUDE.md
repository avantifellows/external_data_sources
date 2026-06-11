# CLAUDE.md — josaa/

Guidance for Claude Code when working inside the `josaa/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions and
[`schemas/README.md`](schemas/README.md) for the JoSAA domain primer.

All paths relative to `josaa/` unless noted.

## What this folder is

A **light-parse** ingestion pipeline for JoSAA engineering counselling
cutoffs (IIT/NIT/IIIT/GFTI), 2016 → latest, all rounds, all seat buckets.
Contrast: [`nirf/`](../nirf/) is pure pass-through (no transform);
[`plfs/`](../plfs/) is a heavy parse. JoSAA sits between — the raw is already
tabular, so `build_clean.py` only unions per-round CSVs, normalizes names,
parses the preparatory-rank encoding, and types the columns.

## The raw/domain split (read before adding columns)

This source carries **only what JoSAA publishes**. It was deliberately
forked off the College DB `josaa-ranks` pipeline to separate the neutral
public fact from Avanti's analytical opinion:

| Stays in `josaa/` (neutral fact) | Stays in College DB `josaa-ranks/` (Avanti domain) |
|---|---|
| institute (as published), program, quota, seat_type, gender | canonical `college_id`, canonical college_name, state |
| opening/closing rank, prep flags, year, round | `salary_tier`, `college_type`, `top_200_nirf`, NIRF salary |
| — | "final closing rank = MAX(closing) across main rounds" derivation |
| — | NIT home-state methodology outputs (`nit_hs_closing_ranks_*`) |

**Do not** add salary tiers, college_type, or canonical-id columns here. If
an analysis needs them, it joins this fact to the College DB enrichment
downstream. Keeping `external_data_sources` opinion-free is the whole point.

## Upstream

Raw `<year>_R<round>.csv` files come from the College DB scraper
(`josaa-ranks/scripts/01_scrape_archive.py`, `02_scrape_current.py`). We
reference, not duplicate, that scraper — same model as `nirf/` (whose parquet
is built in the dashboards repo). On a new JoSAA cycle: run the College DB
scraper, copy its `extracted_data/raw/*.csv` into `raw/`, rebuild + reload.

## Commands

See [README.md](README.md). Quick path: `build_clean.py` →
`upload_to_gcs.py --raw` → `load_bq.py`. Each takes `--dry-run`.

## BQ output

One table in `avantifellows.external_data_sources`:

| Table | Rows | Grain | Clustering |
|---|---:|---|---|
| `josaa_fact_cutoffs` | ~523k | (institute, program, quota, seat_type, gender, year, round) | year, round, seat_type |

Authoritative column docs: [`schemas/josaa_fact_cutoffs.yaml`](schemas/josaa_fact_cutoffs.yaml).

## Design calls worth knowing before you change them

- **All rounds, not just final.** The fact is the full per-round union (~523k
  rows), with `round` as a real dimension — NOT the per-year final-round
  subset (`josaa_<year>.csv`, ~85k). The final-round / MAX-closing views are
  analyst derivations, computed downstream, not extra tables here.
- **Ranks are INTEGER, prep is a flag.** JoSAA's trailing-`P` preparatory
  encoding is split into (integer rank, `*_is_preparatory` bool) in
  `build_clean.py`. Don't store the raw `'50P'` string — it breaks numeric
  comparison. Prep and main-list ranks are different scales; never threshold
  across them.
- **institute is the raw scrape string, not a canonical id.** It varies
  across years. A `josaa_dim_institute` (canonical id + institute_type +
  state, no Avanti opinion) is a sensible *second* table/PR if joins get
  painful — but ship it separately, one table per PR (team rule).
- **WRITE_TRUNCATE, overwrite-in-place.** A new cycle replaces the whole
  table. JoSAA archives historical cycles unchanged, so re-running is safe.

## Pitfalls

- **Don't commit `raw/` or `clean/`.** `.gitignore` enforces it; GCS is the
  authoritative copy. (College DB already hit GitHub's 100 MB limit on the
  union files — that's why nothing data-sized lives in git here.)
- **Don't mix rank spaces.** IITs = JEE Advanced rank; NITs/IIITs/GFTIs =
  JEE Main rank. The institute determines which. Documented in the schema.
- **Don't sum across `round`.** Each (year, round) is a full snapshot.
- **Don't equality-match `institute`.** Names drift; use keyword LIKE/REGEXP.
