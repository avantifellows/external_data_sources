# bitsat — BITSAT cut-off scores (BITS Pilani, Goa, Hyderabad)

BITS admits to B.E., B.Pharm. and integrated M.Sc. at its three campuses on
the BITSAT score alone (no category reservation). BITS publishes every
year's final cut-offs on one page; this pipeline turns it into
`external_data_sources.bitsat_fact_cutoffs` (2017-18 to 2026-27, 402 rows).

```
python3 scripts/build_clean.py      # fetches the snapshot from GCS if missing; BeautifulSoup
python3 scripts/upload_to_gcs.py
python3 scripts/load_bq.py
```

## What to know before querying

- **Scale changed**: maximum marks 450 until 2021-22, 390 from 2022-23
  (`max_score`). Compare years as cutoff_score / max_score, never raw.
- **No categories**: one cut-off per campus and programme.
- **Ties**: when more candidates share the cut-off score than seats remain,
  BITS breaks the tie on PCM scores (note on the page, 2020-21 and 2021-22).
- **New programmes appear**: Mathematics & Computing, Environmental &
  Sustainability, Electronics & Computer, Semiconductor & Nanoscience,
  Pharmaceutical Engg. in recent years.
- The 2020-21 block repeats the 2019-20 intro sentence; its numbers are
  2020-21's (the year comes from each block's id).

## Refresh

Save the page again as `raw/bitsat_cutoffs_page_<date>.html`, add it to
`RAW_FILES` (newest last), rebuild, upload, load. The build fails on any
row it cannot read.
