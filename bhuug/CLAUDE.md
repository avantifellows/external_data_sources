# CLAUDE.md — bhuug

Source-level orientation for the BHU UG (CUET) cutoffs pipeline. Read the
top-level `../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

BHU UG admission 2025: Round 1 and Spot Round 2 allocation summaries (15
faculties/colleges, 351 programmes). Raw = BHU's PDFs + the team's CSV
(gitignored; GCS canonical, `fetch_raw()` in `build_clean.py`).

## Layout

```
bhuug/
├── scripts/
│   ├── sources.py        # config + RAW_FILES / TABLES (single source of truth)
│   ├── build_clean.py    # CSV -> clean/bhuug_fact_cutoffs.parquet, checked against both PDFs
│   ├── upload_to_gcs.py  # raw + clean -> gs://…/bhuug/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> BigQuery (WRITE_TRUNCATE)
├── schemas/bhuug_fact_cutoffs.yaml
├── raw/     (gitignored)
└── clean/   (gitignored)
```

## Gotchas (handled in build_clean.py)

- PDF check: the programme and college columns sometimes run together in
  `pdftotext -layout`, so the college is found as the longest known college
  name ending the text before the quota.
- A new faculty/college string fails the build until UNITS maps it.
- Scores are per-programme scales; `fee_type` splits paid/special seats.
