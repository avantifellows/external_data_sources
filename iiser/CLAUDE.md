# CLAUDE.md — iiser

Source-level orientation for the IISER closing-ranks pipeline. Read the
top-level `../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

The seven IISERs' BS-MS / BS / B.Tech admissions (IISER Aptitude Test).
Upstream is one "Round Wise Closing Ranks" page on the IISER Admissions site,
captured as a PDF (`raw/iiser_round_wise_closing_ranks_2025.pdf`, gitignored;
no stable per-round URL). Light parsing with `pdftotext -layout`, single
build step — the `ducuet/` shape, including its fetch-from-GCS-if-missing
convention (`fetch_raw()` in `build_clean.py`).

## Layout

```
iiser/
├── scripts/
│   ├── sources.py        # config + RAW_FILES / TABLES (single source of truth)
│   ├── build_clean.py    # fetch_raw() from GCS if missing, parse -> clean/iiser_fact_cutoffs.parquet
│   ├── upload_to_gcs.py  # raw PDF + clean parquet -> gs://…/iiser/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> avantifellows.external_data_sources.iiser_fact_cutoffs (WRITE_TRUNCATE)
├── schemas/iiser_fact_cutoffs.yaml
├── raw/     (gitignored; local cache — GCS is canonical)
└── clean/   (gitignored)
```

## The table

`iiser_fact_cutoffs`, grain `(round, program_name, category)`. Closing ranks
are IAT **overall** ranks for every category (the page says so). `--` cells
are dropped, never stored as 0.

## Parsing gotchas (all handled in build_clean.py)

- Long programme names wrap around their values line:
  `BS-MS (Computational and Data Sciences) IISER` / values / `Kolkata`.
- The page number sometimes lands at the end of a table line
  (`… 50055   --   3`) — eleven trailing tokens, drop the last.
- Built-in asserts: no duplicate (round, programme, category); every
  programme resolves to an IISER campus.

## Refreshing for a new admission cycle

Save the page as a PDF, name it per `scripts/sources.py` (bump `YEAR` and
the filename), put it in `raw/`, then `upload_to_gcs.py --raw-only`,
`build_clean.py`, `upload_to_gcs.py --clean-only`, `load_bq.py`.
