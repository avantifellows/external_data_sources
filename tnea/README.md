# tnea/

TNEA (Tamil Nadu Engineering Admissions) cutoffs — the seed of this source's pipeline.

**Status: scraper only.** `scrape/scripts/state_TN.py` (with `tn_console_extract.js`, a
browser-console extractor for the TNEA portal) parses the official data and carries a
code-based government-college classification. The rest of the house shape — `schemas/`,
`scripts/` (clean → GCS → BQ), and a `tnea_fact_cutoffs` table — lands when this source
ships end to end, following the same one-source-at-a-time pattern as `kcet/`, `mhtcet/`,
`gujcet/` and `tgeapcet/`.

Imported from futures-v2 PR #12 (sakshi1755) as part of the ongoing migration of the
counselling pipelines into this repo (see PR #23 for the running list). Raw data goes to
`gs://avantifellows-external-data/tnea/{raw,extracted}/` — pending the org's GCP billing
restoration, like everything else this week.
