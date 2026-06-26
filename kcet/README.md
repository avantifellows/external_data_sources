# kcet/

KCET (Karnataka Common Entrance Test) engineering seat-allotment cutoffs —
closing ranks for every (college, course, category) seat bucket. 13,357 rows,
227 colleges, 2025 Third Round.

## Pipeline shape

```
futures-v2/.../parse_KA_2025.py        scrape + parse KEA PDFs
       │
       ▼
kcet/raw/KA_engg_2025_all_cutoffs_R3.csv          (gitignored)
kcet/raw/KA_engg_closing_ranks_govt_2024.csv      (gitignored, for college_type join)
       │  scripts/build_clean.py                  join college_type + add constants
       ▼
kcet/clean/kcet_fact_cutoffs.parquet              (gitignored)
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/kcet/clean/kcet_fact_cutoffs.parquet
       │  scripts/load_bq.py                      WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.kcet_fact_cutoffs   (asia-south1)
```

## Upstream — where the raw CSV comes from

Raw CSV is produced by `parse_KA_2025.py` in the `avantifellows/futures-v2`
repo (`state_cet/scrape/scripts/parse_KA_2025.py`). That script downloads
PDFs from the KEA website and parses them into a tall CSV.

URLs (2025 Third Round, published 11 Sep 2025):
- GEN: `https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_E_R_11092025english.pdf`
- HK:  `https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_E_H_11092025english.pdf`

## Commands

```bash
# 1. Copy raw files from futures-v2 scraper output
cp /path/to/futures-v2/state_cet/scrape/extracted_data/KA_engg_2025_all_cutoffs_R3.csv raw/
cp /path/to/futures-v2/state_cet/scrape/extracted_data/KA_engg_closing_ranks_govt_2024.csv raw/

# 2. Build clean parquet
python3 scripts/build_clean.py --dry-run
python3 scripts/build_clean.py

# 3. Upload to GCS
python3 scripts/upload_to_gcs.py --dry-run
python3 scripts/upload_to_gcs.py

# 4. Load to BigQuery
python3 scripts/load_bq.py --dry-run
python3 scripts/load_bq.py
```

## Tables

| Table | Grain | Rows | Clustering |
|---|---|---:|---|
| `kcet_fact_cutoffs` | (college_code, course_name, domicile_pool, category_code, year, round) | 13,357 | year, domicile_pool, college_type |

Column docs: [`schemas/kcet_fact_cutoffs.yaml`](schemas/kcet_fact_cutoffs.yaml).
