# CLAUDE.md — icarug

Source-level orientation for the ICAR-UG (CUET) cutoffs pipeline. Read the
top-level `../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

ICAR's 2025 ICAR-UG counselling cut-off list: 72 agricultural universities,
13 courses, 5 rounds. Raw = ICAR's PDF + the team's CSV extraction
(gitignored; GCS canonical, `fetch_raw()` in `build_clean.py`).

## Layout

```
icarug/
├── scripts/
│   ├── sources.py        # config + RAW_FILES / TABLES (single source of truth)
│   ├── build_clean.py    # CSV -> clean/icarug_fact_cutoffs.parquet, checked against the PDF
│   ├── upload_to_gcs.py  # raw PDF + CSV + clean parquet -> gs://…/icarug/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> BigQuery (WRITE_TRUNCATE)
├── schemas/icarug_fact_cutoffs.yaml
├── raw/     (gitignored)
└── clean/   (gitignored)
```

## Gotchas (handled in build_clean.py)

- The PDF check: tokenise `pdftotext -raw`, drop the ICAR/IC/AR watermark
  fragments (sometimes glued to a number), match (category, 4 numbers)
  groups in order; the only tolerated extras are rows repeated next to
  themselves at page breaks.
- A new university string fails the build until UNIVERSITIES maps it.
- Ranks are stream-wise, not one list: use marks.
