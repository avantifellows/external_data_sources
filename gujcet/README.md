# gujcet/

Gujarat ACPC admission cutoffs — last admitted rank + percentile-equivalent
composite score for every (institute, course, category) seat bucket.
2,487 rows across 2 streams.

New here? Read [`schemas/README.md`](schemas/README.md) — "ACPC Gujarat in 60
seconds". The two streams are **different admission years**, which is the
easiest way to get a wrong answer from this table.

## Pipeline shape

```
futures-v2/state_cet/scrape/scripts/state_GJ.py   parse the two ACPC PDFs
       │
       ▼
gujcet/raw/GJ_engg_all_cutoffs_2025.csv            (gitignored)
gujcet/raw/GJ_engg_closing_ranks_govt_2025.csv     (gitignored)
gujcet/raw/GJ_pharm_all_cutoffs_2024.csv           (gitignored)
gujcet/raw/GJ_pharm_closing_ranks_govt_2024.csv    (gitignored)
gujcet/raw/pdfs/*.pdf                              (gitignored, 2 official PDFs)
       │  scripts/build_clean.py   union streams, widen canonical cols, validate
       ▼
gujcet/clean/gujcet_fact_cutoffs.parquet           (gitignored)
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/gujcet/{raw,clean}/
       │  scripts/load_bq.py       PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.gujcet_fact_cutoffs   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).**

## Upstream / provenance

| stream | year | source | rows | institutes |
|---|---|---|---:|---:|
| engineering | **2025**-26 | ACPC final closure PDF (`CLOSURE_BE`) | 1,954 | 133 |
| pharmacy | **2024**-25 | ACPC pharmacy closure PDF | 533 | 118 |

> **The two streams are different admission cycles.** Pharmacy is a year behind
> because that is the latest closure ACPC has published in the wide
> rank+percentile format. A 2025-26 pharmacy file exists but is **Round-2 only
> and rank-only** (no percentile) — deliberately not used; final-closure with a
> percentile is the better source. Re-check the portal for a 2025-26 *closure*.

Parser lives in **[`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2)**
(`state_cet/scrape/scripts/state_GJ.py`) — we reference, not duplicate, it.
`build_clean.py` imports its `classify_gj_college` / `normalise_category`
directly so classification can never drift between the two repos; point
`GJ_PARSER_DIR` at that scripts directory.

Both official PDFs are mirrored to
`gs://avantifellows-external-data/gujcet/raw/pdfs/`, so any number here traces
back to its page without re-scraping ACPC.

> **All institute types ship**, with `college_type` as a column — government
> scope is a query (`college_type IN ('Govt','Govt-Aided','State-Univ-Dept')`
> → 696 rows / 34 institutes), not a pipeline decision. Same choice as
> [`kcet/`](../kcet/) and [`mhtcet/`](../mhtcet/).

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 1. Land the parsed CSVs + the 2 source PDFs from futures-v2
cp /path/to/futures-v2/state_cet/scrape/extracted_data/GJ_{engg,pharm}_*.csv raw/
cp /path/to/futures-v2/state_cet/scrape/source/GJ/*/*.pdf raw/pdfs/

# 2. Build clean parquet (validates anchors + declared grain)
export GJ_PARSER_DIR=/path/to/futures-v2/state_cet/scrape/scripts
.venv/bin/python scripts/build_clean.py --dry-run
.venv/bin/python scripts/build_clean.py

# 3. Stage to GCS (add --with-pdfs to also mirror the source PDFs)
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py --with-pdfs

# 4. Load GCS → BQ
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## Tables

| Table | Grain | Rows | Clustering |
|---|---|---:|---|
| `gujcet_fact_cutoffs` | (stream, college_name, branch_name, category_raw, year) | 2,487 | year, stream, category, college_name |

Column docs: [`schemas/gujcet_fact_cutoffs.yaml`](schemas/gujcet_fact_cutoffs.yaml).

## Refresh checklist

`build_clean.py` hard-asserts per-stream row/institute counts, the L.D. College
CSE anchor (rank 646, read off page 3 of the engineering PDF), and that no PPP
college leaks into govt scope. Those assertions are **meant** to fail on a
refresh — when they do, confirm the change is real, then update the expected
values in the same commit as the cause. Never relax one to make a build pass.
