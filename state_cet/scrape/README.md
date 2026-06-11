# state_cet/scrape/ — upstream scraper (copied from College DB)

Verbatim copy of the state-CET scrape pipeline from the `College DB` repo
(`state-cet-scrape/`), brought over so this source owns the full scrape→load chain.

- **`scripts/`** (committed) — 18 per-state download + parse scripts +
  `consolidate_all.py`.
- **`source/`** (gitignored, ~117 MB in the bundle, belongs in GCS) — the raw
  cutoff PDFs/HTML per state.

## ⚠️ Copied as-is — not yet decoupled

Written for the College DB layout; paths point at that repo's `source/<XX>/` and
`extracted_data/`. **Will not run unmodified here** without re-pathing. Until
decoupled, refresh by running the pipeline in College DB and copying its
`extracted_data/ALL_STATES_consolidated_5cat_govt.csv` into `state_cet/raw/`.

## Chain that produces the neutral fact

Per-state `state_<XX>.py` / `download_<XX>.py` parse each authority's PDFs →
`consolidate_all.py` unions + applies the govt-scope + 5-cat harmonization →
`ALL_STATES_consolidated_5cat_govt.csv` = `state_cet/raw/` (what our
`build_clean.py` reads). The harmonization is the "curated product" this source
intentionally ships (see ../CLAUDE.md).
