# CLAUDE.md — uptac

Source-level orientation for the UPTAC OR-CR pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

UPTAC's public OR-CR grid (Samarth portal), 2026 counselling, 27,047 rows.
Raw = the grid's HTML pages, zipped to GCS (gitignored locally).
`fetch_pages.py` is polite (1 req/s, backoff) and refuses a table whose
record count changes mid-scrape.

## Layout

```
uptac/
├── scripts/
│   ├── sources.py        # config (URL, GCS, BQ, TABLES)
│   ├── fetch_pages.py    # grid pages -> raw/pages/page_NNNN.html
│   ├── build_clean.py    # parse + label -> clean/uptac_fact_cutoffs.parquet
│   ├── upload_to_gcs.py  # pages zip + parquet -> gs://…/uptac/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> BigQuery (WRITE_TRUNCATE)
├── schemas/uptac_fact_cutoffs.yaml
├── raw/     (gitignored)
└── clean/   (gitignored)
```

## Gotchas

- `rank_basis` separates JEE Main ranks from UPTAC's own round merit lists.
- The grain includes `exam`: B.Arch rows split by NATA vs JEE Paper 2.
- Category codes: EWS must be matched before E…; see README.
- Institute display names: ACRONYMS in build_clean.py holds acronyms that
  contain vowels (ABES, KIET, AKTU…); vowel-less ones are caught by rule.
