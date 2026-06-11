# Handoff — College DB counselling sources → external_data_sources

**From:** Akshay · **To:** Amogh · **Date:** 2026-06-02

Four counselling-data sources migrated out of the `College DB` repo into
`external_data_sources`. The **pipelines are written and locally verified**;
they are **not yet loaded to GCS/BQ and not yet in git**. Your job: drop them
into a clean clone, stage the data, create the BQ tables, and open the PRs —
**one dataset at a time, one PR per table** (the team's review process).

Nothing here has been pushed to any branch. There is no scaffold branch. You
own all the git history for these tables.

## What you're getting — a single bundle

`college_sources_handoff.zip`. Unzip it at the ROOT of a fresh
`external_data_sources` clone:

```bash
git clone https://github.com/avantifellows/external_data_sources.git
cd external_data_sources
unzip ~/Downloads/college_sources_handoff.zip -d .
```

It contains, landing in place:

| What | Path | Goes to git? |
|---|---|---|
| 4 load pipelines (code) | `<source>/{scripts,schemas,codemaps}`, READMEs, CLAUDE.md | YES — you commit these, per-table PR |
| The data | each `<source>/raw/` + `<source>/clean/` | **NO — gitignored.** GCS is their home. |
| Upstream scraper code | each `<source>/scrape/scripts/` (the per-state parsers etc., copied from College DB) | YES — committed (code) |
| Upstream source archives | each `<source>/scrape/source/` (~250 MB of cutoff PDFs/HTML) | **NO — gitignored.** Belongs in GCS. |
| The skill (runbook) | `.claude/skills/external-datasets/SKILL.md` | optional (see note below) |
| This doc | `COLLEGE_SOURCES_HANDOFF.md` | your call |

**The `raw/`, `clean/`, and `scrape/source/` files are deliberately gitignored**
by each `<source>/.gitignore` and the root `.gitignore`. Do not force them into
git — they go to `gs://avantifellows-external-data/<source>/` via the upload
script. The `scrape/scripts/` code IS committable.

### About the scrapers (`<source>/scrape/`)

The full upstream scrape pipeline from College DB rides in the bundle so this
repo owns the whole scrape→load chain (per Akshay's call). **Caveat: the
scrapers are copied verbatim and are NOT yet decoupled** — they reference College
DB's layout and (for josaa) the sibling `../CoE Selection DB` repo + `../tiers.csv`.
**They will not run unmodified in this repo.** Re-pathing them is a follow-up.
Until then, the working refresh path is still: run the pipeline in College DB,
copy its output CSV into `<source>/raw/`. Each `<source>/scrape/README.md` spells
out exactly which scripts produce the neutral raw vs which are Avanti-domain.

**This does NOT block the immediate job** — `build_clean.py` reads the raw CSVs
already in the bundle, so you can load all 4 tables today without touching the
scrapers.

## Read this first — the skill

`.claude/skills/external-datasets/SKILL.md` is the authoritative runbook for
GCS staging, the BQ load, the one-table-per-PR rule, the paired bq-assistant
PR, and commit hygiene. Open it in a Claude session inside the repo.

> Note: the repo's root `.gitignore` ignores `.claude/`. The skill in this
> bundle works locally as-is. If you also want it committed so it travels with
> the repo, change the root `.gitignore` line `.claude/` to:
> ```
> .claude/*
> !.claude/skills/
> ```
> (keeps personal Claude state ignored, commits only the skill.)

## The four tables

| Source | BQ table | Rows | Local anchor (verified) |
|---|---|---:|---|
| `josaa/` | `josaa_fact_cutoffs` | ~523k | MANIT Materials HS OPEN GN 2025 R6 = 51,350; IIT-B CSE AI OPEN GN final = 59–68 |
| `state_cet/` | `state_cet_fact_closing_ranks` | ~7.8k | WBJEE Jadavpur CSE GEN 2025 = 238; KEAM Tvm CSE GEN 2025 = 343 |
| `mcc/` | `mcc_fact_closing_ranks` | ~3.1k | AIIMS New Delhi MBBS Open-Seat-Quota Open R1 = 48 |
| `state_medical/` | `state_medical_fact_closing_ranks` | ~2.9k | 2,160 NEET-AIR rows + 703 state-native; 108 third-party |

## Design decisions baked in (don't undo without discussing)

Guiding principle: **external_data_sources = neutral published fact only.**
Avanti opinion (salary tiers, college_type, canonical college_id, "closing =
MAX across rounds" derivation) stays in `College DB`.

- **josaa** — JoSAA's untouched table. All rounds (not the final-round subset),
  `round` a real dimension. Prep ranks (`50P`) split to int + `is_preparatory`.
  Dropped all Avanti enrichment (used `josaa_<year>.csv`, NOT `_enriched`).
- **state_cet** — ships a **curated** product (govt-scope + 5-cat + final-round),
  documented as such in the schema. Not raw — transparent about it.
- **mcc** — **full** AIQ allotment (NOT govt-filtered). Used
  `closing_ranks_aiq_r1_2025.csv`. `quota='All India'` = the govt 15% pool.
  Distinct from regulator source `nmc/` — keep separate.
- **state_medical** — sharpest call: **neutral projection** of
  `national_closing_ranks_unified_AIR_2025.csv`. **Dropped** the Avanti modeling
  (`air_unified` estimate, `tier`, `multiplier_applied`, `estimated_R3_closing_rank`).
  Kept `rank_space` (NEET-AIR vs state-native), `conversion_method`,
  `source_quality`, `is_estimated`. Cost: ~25% of rows aren't cross-state
  comparable here (the estimate stays in College DB). If a comparable-AIR is
  wanted in BQ later, make it a SEPARATE, clearly-marked derived table — do not
  fold it back into this neutral fact.

## Runbook — per source

Do these one source at a time. Each `<source>/` is self-contained; commands run
from inside the source folder.

```bash
cd josaa/                                            # repeat for each source
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# 1. Regenerate clean from raw (don't trust the shipped parquet — rebuild it)
.venv/bin/python scripts/build_clean.py --dry-run    # check rowcount/summary
.venv/bin/python scripts/build_clean.py              # writes clean/

# 2. Stage raw + clean to GCS (canonical copy)
.venv/bin/python scripts/upload_to_gcs.py --raw --dry-run
.venv/bin/python scripts/upload_to_gcs.py --raw

# 3. Load GCS → BQ (WRITE_TRUNCATE, idempotent)
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py

# 4. Verify — rowcount vs the table above + the documented anchor
#    (anchors are in each schemas/<table>.yaml + schemas/README.md)
```

Prereq (one-time, if not already there): the dataset must exist —
`bq --location=asia-south1 mk --dataset avantifellows:external_data_sources`.

## Opening the PRs (one table per PR + paired bq-assistant PR)

The files are already in your working tree from the unzip. For each source, off
`main`, following the repo's `add-<source>` branch convention:

```bash
git checkout main && git checkout -b add-josaa
git add josaa/                                       # just this source's code (raw/clean gitignored)
# add this source's row to the README.md sources table
git -c user.name="<you>" -c user.email="<you>@avantifellows.org" \
    commit -m "Add JoSAA source: josaa_fact_cutoffs"
git push -u origin add-josaa
# open PR → external_data_sources, get it reviewed dataset-by-dataset
```

Then the **paired bq-assistant PR** for that table (the skill details this):
copy `<source>/schemas/<table>.yaml` to
`bq-assistant/docs/schemas/external_data_sources/<table>.yaml`, add the
analysis-intent block to `docs/analyses/external_data_sources.yaml`, and
regenerate `CLAUDE.md` via `scripts/regen_claude_md.py`.

**Commit hygiene:** clean messages, **no "Co-Authored-By: Claude" / AI
trailers**, git identity inline (never modify git config). Confirm
`git status` shows no `raw/` or `clean/` files before every commit.

## Notes

- **Upstream refresh:** each source's `CLAUDE.md` documents where the raw comes
  from in the `College DB` repo and how to re-land it on a new cycle. The raw is
  scraper output from College DB — we reference, not duplicate, those scrapers.
- **`College DB` is untouched.** Its downstream consumer (`CoE Selection DB`)
  hardcodes `../College DB` paths, so nothing moved — these are copies.
- **Adjacent, not your scope:** `nmc/` has data (`clean/mbbs_seats.parquet`) but
  no pipeline scripts/schema — a separate half-built source, ignore for this work.
