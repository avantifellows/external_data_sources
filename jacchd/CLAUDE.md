# CLAUDE.md — jacchd

Source-level orientation for the JAC Chandigarh cutoffs pipeline. Read the
top-level `../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

JAC Chandigarh's 2026 round-wise opening/closing ranks for five institutes
(CCET, CCA, UIET Chandigarh, Dr. SSB UICET, UIET Hoshiarpur). Upstream is
a team-transcribed Google Sheet of the JAC portal, exported as CSV
(`raw/jacchd_2026_cutoffs_sheet.csv`, gitignored; GCS is canonical). No
parsing, only labelling — the `iiser/` shape, including fetch-from-GCS-if-
missing (`fetch_raw()` in `build_clean.py`).

## Layout

```
jacchd/
├── scripts/
│   ├── sources.py        # config + RAW_FILES / TABLES (single source of truth)
│   ├── build_clean.py    # fetch_raw() from GCS if missing, normalise -> clean/jacchd_fact_cutoffs.parquet
│   ├── upload_to_gcs.py  # raw CSV + clean parquet -> gs://…/jacchd/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> avantifellows.external_data_sources.jacchd_fact_cutoffs (WRITE_TRUNCATE)
├── schemas/jacchd_fact_cutoffs.yaml
├── raw/     (gitignored; local cache — GCS is canonical)
└── clean/   (gitignored)
```

## The table

`jacchd_fact_cutoffs`, grain `(round, institute, programme_raw, quota,
category_raw)`.

## Gotchas (all handled in build_clean.py)

- `rank_basis`: JEE Main Paper 1 / Paper 2 (CCA B.Arch) / category merit
  list (Defence, Sports). Never compare across.
- " - TFW" is a seat pool → `tfw`; only the EWS fee-waiver category uses it.
- A new category label fails the build until CATEGORY_RULES maps it.
