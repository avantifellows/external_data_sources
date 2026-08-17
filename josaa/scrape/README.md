# josaa/scrape/ — upstream scraper (copied from College DB)

Verbatim copy of the JoSAA scrape pipeline from the `College DB` repo
(`josaa-ranks/`), brought over so this source owns the full scrape→load chain.

- **`scripts/`** (committed) — the scraper code.
- **`source/`** (gitignored, in the handoff bundle, belongs in GCS) — reference PDFs.

## ⚠️ Copied as-is — not yet decoupled

These scripts were written for the College DB repo layout. They have not been
re-pathed for `external_data_sources` and **will not run unmodified here**:

- `run_all.py` references the sibling `../CoE Selection DB` repo and `../tiers.csv`
  (Avanti state-lookup + tier inputs). That dependency does not exist in this repo.
- Paths point at College DB's `extracted_data/` layout.

Decoupling (fix paths, vendor the state lookup) is a follow-up task. Until then,
the **authoritative way to refresh** is still: run the pipeline in College DB,
then copy its `extracted_data/raw/*.csv` into `josaa/raw/`.

## What produces the neutral fact

For `josaa_fact_cutoffs` you only need the **scrape** steps:

- `01_scrape_archive.py`, `02_scrape_current.py` → per-(year,round) CSVs = `josaa/raw/`
- `03_consolidate.py` → per-year final-round files (not used by our build_clean,
  which reads the raw per-round files directly)

**Avanti-domain — NOT part of this neutral source** (kept only for completeness;
their outputs belong in College DB, not external_data_sources):

- `04_enrich.py` — adds salary_tier, college_type, NIRF salary
- `nit_hs_closing_ranks.py`, `nit_hs_closing_ranks_all_categories.py` — NCST methodology outputs
