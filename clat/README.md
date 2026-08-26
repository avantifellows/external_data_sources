# clat

CLAT 2026 UG counselling cutoffs — 26 NLUs × 5 programmes × every published
reservation category, derived FIRST-PARTY from the Consortium of NLUs'
per-university allotment PDFs.

```
raw/pages/*.html     the five allotment-list pages (via Wayback — the live
                     site rotates each cycle and now serves CLAT 2027)
raw/pdf/list{1..5}/  184 per-NLU candidate-level PDFs (the consortium's S3
                     stays live: files2026.consortiumofnlus.ac.in)
       │ scripts/parse_lists.py
       ▼
extracted/clat_cutoff_tables_2026.csv   the PDFs' own "Cut-Off Rank Table"
extracted/clat_admitted_2026.csv        candidate-level rows (audits only)
       │ scripts/build_clean.py         ← decomposition + anchors
       ▼
clean/clat_cutoffs.parquet → gs://avantifellows-external-data/clat/ → BQ
avantifellows.external_data_sources.clat_fact_cutoffs   (454 rows)
```

## What we learned the hard way (read before touching)

- **The authoritative numbers are the PDFs' own Cut-Off Rank Tables**, not an
  aggregation of the candidate rows. The consortium attributes overlay admits
  (PwD / Women / NCC / CAP…) to the OVERLAY row — a naive max-AIR-per-vertical
  disagrees with the official table by construction (DSNLU OBC: official
  2,731; naive derivation 43,433 because a PwD admit sat in the OBC vertical).
- A hand-me-down CSV of these cutoffs (~/jan2023) matched the official tables
  on ~90% of rows but carried PRE-5th-round values for several NLUs (CNLU BBA
  General 1235 vs the final 1368). Vintage matters; ours is pinned to the 5th
  (final) list of 2026-05-20.
- `**` in the source = seats exist, no cutoff published (unfilled or filled
  purely via overlays). 46 rows; kept as NULL, never imputed.
- Category codes fuse WHO with WHERE (BC-A-AP, SC-AP-G2, GC-KA). The clean
  table decomposes them into (category_canonical, domicile_state, subgroup,
  is_women_row, is_pwd_row, special_quota) — 76% roll to the five canonical
  categories; special quotas keep canonical NULL honestly.
- PDFs carry AIRs + admit-card numbers (no names). Raw stays in the private
  bucket; extracted/clean carry no candidate identifiers except AIRs in the
  audit extract.
