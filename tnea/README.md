# tnea/

TNEA (Tamil Nadu Engineering Admissions) cutoffs — end to end.

| table | rows | grain |
|---|---|---|
| `tnea_fact_cutoffs` | 14,910 | college × branch × community, 2025 final round |

Two metrics per row, opposite directions: `cutoff_mark` (TNEA composite /200, higher =
harder) and `closing_rank` (TN state merit rank, lower = harder). Both come straight from
the official portal, pulled with `scrape/scripts/tn_console_extract.js`.

## Pipeline

```
portal pulls (raw/, via the console extractor)
   │  scripts/build_clean.py     joins marks+ranks, melts 7 communities, classifies
   ▼                             college_type by the official DOTE code list
clean/tnea_fact_cutoffs.parquet
   │  scripts/upload_to_gcs.py → gs://avantifellows-external-data/tnea/{raw,clean}/
   │  scripts/load_bq.py       → external_data_sources.tnea_fact_cutoffs
```

Government classification is **code-based, never name-based** — the code sets live in
`scrape/scripts/state_TN.py` (imported from futures-v2 #12, sakshi1755; +2 constituent
UCEs found in review) and `build_clean.py` lifts them from there so exactly one copy
exists. TN's 7 communities (OC/BC/BCM/MBC/SC/SCA/ST — no EWS) are kept verbatim in
`category_raw` with a canonical rollup in `category`.

`(SS)` branches are Self-Supporting sections — costlier self-financed streams *inside*
government/aided colleges. Flagged, never silently mixed: the seat-vs-college lesson again.
