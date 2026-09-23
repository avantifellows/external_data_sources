# CLAUDE.md — aiimsnursing

Source-level orientation for the AIIMS B.Sc. (Hons.) Nursing allocation
pipeline. Read the top-level `../CLAUDE.md` for cross-cutting repo
conventions first.

## What this source is

AIIMS New Delhi's B.Sc. (Hons.) Nursing seat-allocation result
notifications (2025: Round 1 No. 117, Round 2 No. 132), one line per
eligible candidate in rank order, for 18 AIIMS. Raw PDFs gitignored; GCS
is canonical (`fetch_raw()` in `build_clean.py`, the `iiser/` shape).

## Layout

```
aiimsnursing/
├── scripts/
│   ├── sources.py        # config + RAW_FILES / TABLES (single source of truth)
│   ├── build_clean.py    # pdftotext -layout parse -> clean/aiimsnursing_fact_{allotments,cutoffs}.parquet
│   ├── upload_to_gcs.py  # raw PDFs + clean parquets -> gs://…/aiimsnursing/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> BigQuery (WRITE_TRUNCATE)
├── schemas/aiimsnursing_fact_cutoffs.yaml   # both tables
├── raw/     (gitignored)
└── clean/   (gitignored)
```

## Gotchas (handled in build_clean.py)

- Roll numbers are dropped at parse time. Don't add them back.
- Round 1 prints OBC-NCL, Round 2 OBC: normalised to OBC.
- The PwBD column is usually blank; only "PWBD" appears.
- The build asserts against each PDF's own last-rank table — if a new
  session's layout changes, that check fails first.
