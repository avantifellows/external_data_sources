# nicorcr — OR-CR from NIC-hosted university counsellings

Some universities run their own counselling on NIC's "Online Counselling
System" instead of a state board: HBTU Kanpur (and MMMUT Gorakhpur) admit
B.Tech on the JEE Main CRL rank outside UPTAC. Each publishes opening /
closing ranks as one HTML report per programme and year. This pipeline
turns them into `external_data_sources.nicorcr_fact_cutoffs` (see
`schemas/nicorcr_fact_cutoffs.yaml`).

```
python3 scripts/fetch_reports.py    # each report in sources.REPORTS -> raw/<board>_<programme>_<year>.html
python3 scripts/build_clean.py      # parse + label (fetches raw from GCS if missing)
python3 scripts/upload_to_gcs.py    # raw HTML + clean parquet -> gs://avantifellows-external-data/nicorcr/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

A report only opens when followed from the board's portal (session cookie
+ Referer); `fetch_reports.py` does that. Add a board = one `Report` line in
`scripts/sources.py`.

## What to know before querying

- Ranks are JEE Main CRL ranks for every category.
- `quota`: HBTU keeps 'All India' seats in every round next to 'Home State'
  (U.P. domicile) ones — unlike UPTAC, where only the special round is open
  to non-U.P. students.
- Categories follow the U.P. scheme (see `uptac/`): parent + GIRL / AF / FF /
  PH sub-category, TF = tuition fee waiver.
- Round names change by year ('Additional Round 1/2' in 2026, '2nd Phase
  Round 1' in 2025).
- **MMMUT is not in yet**: every MMMUT report returned HTTP 500 on
  2026-09-25, in a browser too.
