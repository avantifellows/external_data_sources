# state_medical/scrape/ — upstream scraper (copied from College DB)

Verbatim copy of the state-medical-counselling scrape pipeline from the
`College DB` repo (`medical-state-counselling/`), brought over so this source
owns the full scrape→load chain.

- **`scripts/`** (committed) — 35 per-state parsers (`state_<XX>.py`) +
  `_thirdparty_pipeline.py`, `normalize_round_depth.py`, `run_all.py`.
- **`source/`** (gitignored, ~102 MB in the bundle, belongs in GCS) — per-state
  raw allotment PDFs/HTML.

## ⚠️ Copied as-is — not yet decoupled

Written for the College DB layout (`source/<XX>/`, `extracted_data/`). **Will not
run unmodified here** without re-pathing. Until decoupled, refresh by running the
pipeline in College DB and copying its
`extracted_data/national_closing_ranks_unified_AIR_2025.csv` into `state_medical/raw/`.

## Chain that produces the neutral fact

35 `state_<XX>.py` parsers handle each state's own format (22 distinct schemas) →
national consolidation harmonizes them → `national_closing_ranks_unified_AIR_2025.csv`
= `state_medical/raw/` (what our `build_clean.py` reads).

**Important:** the consolidation step ALSO computes the Avanti modeling our
`build_clean.py` deliberately drops — the estimated unified AIR, salary tier,
round multiplier, estimated-R3 rank. Those are NOT part of this neutral source
(see ../CLAUDE.md). The per-state parsers themselves are scrape/parse code and are
fine to keep here.
