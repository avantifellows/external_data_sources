# josaa/

JoSAA (Joint Seat Allocation Authority) engineering seat-allotment cutoffs —
opening and closing ranks for every IIT/NIT/IIIT/GFTI seat bucket, every
counselling round, 2016 → latest. 464,496 rows.

New here? Read [`schemas/README.md`](schemas/README.md) — "JoSAA in 60 seconds"
— before querying. Pipeline orientation for editing is in [`CLAUDE.md`](CLAUDE.md).

## Pipeline shape

This is a **light-parse** source: the raw is already tabular (per-round CSVs
from the JoSAA portal), so the pipeline unions, normalises, and types them.

```
josaa/raw/<year>_R<round>.csv         (scraper output, gitignored)
       │  scripts/build_clean.py       union + snake_case + parse prep ranks + type
       ▼
josaa/clean/josaa_fact_cutoffs.parquet (gitignored)
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/josaa/clean/josaa_fact_cutoffs.parquet
       │  scripts/load_bq.py           WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.josaa_fact_cutoffs   (asia-south1)
```

Single source of truth for bucket, prefix, BQ destination, column renames:
[`scripts/sources.py`](scripts/sources.py).

## Upstream — where the raw CSVs come from

The raw per-`(year, round)` CSVs are scraped from the JoSAA portal's public
OpRank pages. Two scraper scripts live in the `avantifellows/futures-v2` repo
under `josaa/scrape/scripts/`:

- `01_scrape_archive.py` — JoSAA portal archive endpoint, 2016–2024
- `02_scrape_current.py` — current-cycle endpoint (2025 onwards)

Run those, then copy the output CSVs (`extracted_data/raw/*.csv`) into
`josaa/raw/` here before running `build_clean.py`.

> Raw CSVs carry only what JoSAA publishes: institute, program, quota,
> seat_type, gender, opening/closing rank, year, round. No Avanti enrichment
> (salary tier, college_type, canonical college_id) is added in this pipeline.

## Commands

```bash
# Set up local Python env
python3 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery google-cloud-storage

# 1. Copy scraper output into raw/ (filenames must match <year>_R<round>.csv)
#    cp /path/to/futures-v2/josaa/scrape/extracted_data/raw/*.csv raw/

# 2. Build clean parquet
.venv/bin/python scripts/build_clean.py --dry-run   # validate + row counts, no write
.venv/bin/python scripts/build_clean.py             # writes clean/josaa_fact_cutoffs.parquet

# 3. Upload to GCS
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py

# 4. Load to BigQuery (post-approval only — see top-level CLAUDE.md)
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py
```

## Tables

| Table | Grain | Rows | Clustering |
|---|---|---:|---|
| `josaa_fact_cutoffs` | (institute, program, quota, seat_type, gender, year, round) | 464,496 | year, round, seat_type |

Column docs: [`schemas/josaa_fact_cutoffs.yaml`](schemas/josaa_fact_cutoffs.yaml).
