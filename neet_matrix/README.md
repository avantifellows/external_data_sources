# neet_matrix

NEET-2026 **minimum-marks matrix** → BigQuery.

For each state/UT and category, the minimum NEET marks that realistically win a
**government** MBBS (B1a) / BDS (B1b) seat, plus B2b (the national qualifying floor).
370 rows = 37 tracks × 10 categories — all 36 states/UTs plus "All India" (the 15%
All-India-Quota track).

It answers **"what is the bar?"** — one floor per (state, category) — as against the
per-college closing ranks a college predictor needs.

## Pipeline

```
~30 official documents (state cutoff PDFs, allotment lists, merit lists,
and one admitted-student register published as 10 page images)
       │  parsers + builders live in futures-v2/neet/matrix_2026/
       ▼
neet_2026_matrix_all.csv
       │  scripts/build_parquet.py     (splits data_status, ints become nullable)
       ▼
clean/neet_marks_matrix_2026.parquet
       │  scripts/upload_to_gcs.py     (raw + extracted + clean)
       ▼
gs://avantifellows-external-data/neet_matrix/{raw,extracted,clean}/
       │  scripts/load_bq.py
       ▼
avantifellows.external_data_sources.neet_dim_marks_matrix_2026   (asia-south1)
```

`scripts/sources.py` is the single source of truth for paths, GCS URIs and the BQ target.

## Three GCS tiers

- **`raw/`** — the source documents themselves, including
  `raw/mizoram-zmch-2025-admitted/p1..p10.png` (ZMCH publishes its NMC admitted-student
  return as scans, not a table). Traceability only; never loaded to BQ. This tier is what
  makes the pipeline reproducible by someone other than its author.
- **`extracted/`** — parser output: per-college allotments, closings, and the 5,817-pair
  Odisha state-rank↔AIR bridge. Kept so a reviewer can diff a parse against its source PDF
  without re-running OCR.
- **`clean/`** — the deliverable parquet.

Raw, extracted and clean are **gitignored** — data lives in GCS, only code in git.

## Reading the table

`state` is a **track label, not a place**: "All India" is the 15% AIQ door, everything else
is that state's 85% domicile door. A student competes in both, and the two are not
comparable within a category. `source_round` matters for the same reason — round depth
differs by state, so a Round-1 state looks harsher than a mop-up state at identical reality.

`data_status` distinguishes a real cutoff from an absent one. `N_A_NO_QUOTA` means the state
does not run that category at all (Punjab/Haryana have no ST quota; Tamil Nadu has no EWS) —
those rows previously showed the qualifying floor, which read as a genuine cutoff.

Full method and per-state provenance:
`futures-v2/neet/matrix_2026/docs/NEET_2026_HOW_WE_BUILT_IT.md`
