# mhtcet/

Maharashtra CAP state-quota admission cutoffs — closing ranks for every
(college, branch, quota pool, category) seat bucket across four streams.
59,380 rows, 943 colleges, 2025-26 cycle.

New here? Read [`schemas/README.md`](schemas/README.md) — "MHT-CET in 60
seconds" — before querying. The reservation codes are not self-explanatory and
one of them is easy to get backwards.

## Pipeline shape

```
futures-v2/state_cet/scrape/scripts/download_MH.py        fetch CET Cell PDFs
                                    download_MH_arch.py
                                    state_MH.py           parse + aggregate
                                    state_MH_arch.py
       │
       ▼
mhtcet/raw/MH_engg_state_quota_closing_ranks_2025.csv       (gitignored)
mhtcet/raw/MH_pharm_state_quota_closing_ranks_2025.csv      (gitignored)
mhtcet/raw/MH_arch_state_quota_closing_ranks_2025.csv       (gitignored)
mhtcet/raw/MH_bdesign_state_quota_closing_ranks_2025.csv    (gitignored, optional)
       │  scripts/build_clean.py    union streams, type, validate anchors
       ▼
mhtcet/clean/mhtcet_fact_cutoffs.parquet                    (gitignored)
       │  scripts/upload_to_gcs.py  stage raw + clean to GCS
       ▼
gs://avantifellows-external-data/mhtcet/{raw,clean}/
       │  scripts/load_bq.py        load_table_from_uri, PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.mhtcet_fact_cutoffs     (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).**

## Upstream / provenance

The State CET Cell runs ~10 parallel CAPs, each on its own portal subdomain.
Four publish per-college cutoffs as parseable PDFs and are covered here:

| stream | portal | rows | source shape |
|---|---|---:|---|
| engineering | `fe2025.mahacet.org` | 46,662 | 4 CAP round PDFs (state quota) + 4 (all-India) |
| pharmacy | `ph2025.mahacet.org` | 11,716 | same layout as engineering |
| architecture | `arch2025.mahacet.org.in` | 983 | 234 per-institute × per-round PDFs (SPA portal) |
| bdesign | `bdesigncap2025.mahacet.org` | 19 | 3 private institutes, no govt seats |

Parsers live in **[`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2)**
(`state_cet/scrape/scripts/`) — we reference, not duplicate, them. Streams not
covered: agriculture (MCAER publishes no per-college closing ranks), 5-yr LL.B
and B.HMCT (no batch-downloadable source).

> **Scope: every college type ships.** Unlike the older `state_cet/` product,
> this table is not pre-filtered to government colleges. `college_type` is a
> column, so government scope is a query
> (`college_type IN ('Govt','Govt-Aided','State-Univ-Dept')` → 3,726 rows,
> 38 colleges). Private/minority/deemed institutes are the remaining ~56k rows.

## Commands

```bash
brew install poppler   # the upstream parsers shell out to `pdftotext -layout`

python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. Land the parsed per-stream CSVs from futures-v2
cp /path/to/futures-v2/state_cet/scrape/extracted_data/MH_{engg,pharm,arch,bdesign}_state_quota_closing_ranks_2025.csv raw/

# 2. Build clean parquet (validates anchors + declared grain)
.venv/bin/python scripts/build_clean.py --dry-run
.venv/bin/python scripts/build_clean.py

# 3. Stage to GCS
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py

# 4. Load GCS → BQ
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## Tables

| Table | Grain | Rows | Clustering |
|---|---|---:|---|
| `mhtcet_fact_cutoffs` | (stream, college_code, branch_code, quota, category_raw, college_type, year) | 59,380 | year, stream, category, college_code |

Column docs: [`schemas/mhtcet_fact_cutoffs.yaml`](schemas/mhtcet_fact_cutoffs.yaml).

## Refresh checklist

`build_clean.py` hard-asserts row counts per stream and two named anchors
(VJTI CSE 103/119; college 03016 retaining both funding pools). Those
assertions are **meant** to fail on a refresh — when they do, confirm the
change is real (CET Cell republished, or an upstream parser fix) and update the
expected values in the same commit, never silently.
