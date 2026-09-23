# iiser — IISER round-wise closing ranks

The seven IISERs admit to BS-MS / BS / B.Tech through the IISER Aptitude
Test (IAT). This pipeline turns the admissions site's round-wise closing-rank
page into `external_data_sources.iiser_fact_cutoffs` (see
`schemas/iiser_fact_cutoffs.yaml`).

```
python3 scripts/build_clean.py      # fetches the raw PDF from GCS if missing, parses
python3 scripts/upload_to_gcs.py    # raw + clean parquet to gs://avantifellows-external-data/iiser/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

New cycle: save the page as a PDF, drop it in `raw/` under the name in
`scripts/sources.py`, run all three. Needs `pdftotext` (poppler).

Checks built in: no duplicate (round, programme, category); every programme
name ends in an IISER campus. The 2025 load matched Amogh's hand-parsed CSV
cell for cell (495 rows).
