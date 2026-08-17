# mcc/scrape/ — upstream scraper (copied from College DB)

Verbatim copy of the medical-national scrape pipeline from the `College DB` repo
(`medical-national-ranks/`), brought over so this source owns the full
scrape→load chain.

- **`scripts/`** (committed) — 5 PDF parsers + `run_all.py`.
- **`source/`** (gitignored, ~30 MB in the bundle, belongs in GCS) — NMC/DCI/MCC
  R1/R2/R3 source PDFs.

## ⚠️ Copied as-is — not yet decoupled

Written for the College DB layout (`source/`, `extracted_data/`). **Will not run
unmodified here** without re-pathing. Until decoupled, refresh by running the
pipeline in College DB and copying its
`extracted_data/closing_ranks_aiq_r1_2025.csv` into `mcc/raw/`.

## Chain that produces the neutral fact

`05_parse_r1_closing_ranks.py` parses MCC's ~1,100-page R1 allotment PDF →
`closing_ranks_aiq_r1_2025.csv` = `mcc/raw/` (what our `build_clean.py` reads).
The other parsers (`01_parse_nmc_mbbs`, `02_parse_dci_bds`,
`03_combine_govt_colleges`, `04_parse_mcc_seat_matrix`) build the govt-scoped
college list + seat matrix — useful context, but the neutral `mcc_fact_closing_ranks`
comes from the full AIQ allotment, not the govt cut.

> Seat-matrix parsing here overlaps with the separate `nmc/` regulator source —
> keep the two distinct (counselling cutoffs vs regulator seat registry).
