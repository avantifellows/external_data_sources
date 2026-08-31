# apeapcet/

AP EAPCET (Andhra Pradesh, formerly AP EAMCET) consolidated last ranks from
APSCHE — 2025 actuals, replacing the 2022 proxy that futures-v2's state_AP.py
had to use after APSCHE's old URLs rotted. The AP counterpart to `tgeapcet/`
(Telangana kept the same exam after bifurcation; rank spaces NOT comparable).

## Pipeline shape

```
apeapcet/raw/AP_EAPCET_2025_lastranks.pdf     60 pages, 1,609 college-branch rows
       │  scripts/build_clean.py              melt 22 rank columns to long
       ▼
apeapcet/clean/apeapcet_fact_cutoffs.parquet  29,848 rows
       │  scripts/upload_to_gcs.py            raw + clean → GCS
       ▼
gs://avantifellows-external-data/apeapcet/{raw,clean}/
       │  scripts/load_bq.py                  WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.apeapcet_fact_cutoffs   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py)** — including
the refresh drill for the 2026 consolidated file (mid-cycle as of Aug 2026)
and the soft-200 caveat on the CAP portal.

## Grain and quirks (schema YAML has the full story)

- One row per **college × branch × local-area × category × gender**. LAST
  rank only. Private universities publish separate AU and SVU local-area
  rows per branch — local_area is part of the grain.
- **2025 introduced SC sub-classification**: SC-I/II/III replace 2022's
  single SC column. BC-A..BC-E are AP's own BC sub-lists.
- **"Girls are also eligible for Boys seats"** (source footnote): the BOYS
  column is effectively the open-to-all pool; GIRLS is the 33% women's
  reservation.
- college_type from the source's own `type` column: UNIV = government
  university constituent colleges; SF / SS = self-finance / self-supporting
  pools INSIDE those campuses; PVT = private; PU = private university.
- branch_code verbatim (no legend in the source PDF). Full names live in
  [`branch_codes.csv`](branch_codes.csv) — the official EAPCET course list
  (73 codes seen in our data plus a few extras; QC=Quantum Computing and
  CSED=CSE-DevOps verified via the single colleges that offer them).

## Where this surfaces

- **BigQuery**: `external_data_sources.apeapcet_fact_cutoffs`.
- Predictor / open data: see the checklist run (PR #23 thread).
