# kcet/

KCET (Karnataka Common Entrance Test) engineering seat-allotment cutoffs —
closing ranks for every (college, course, category) seat bucket. 13,604 rows,
229 colleges, 2025 Third Round.

## Pipeline shape

```
futures-v2/.../parse_KA_2025.py        scrape + parse KEA PDFs
       │
       ▼
kcet/raw/KA_engg_2025_all_cutoffs_R3.csv          (gitignored)
kcet/raw/KA_engg_2025_GEN_R3.pdf                  (gitignored, official source)
kcet/raw/KA_engg_2025_HK_R3.pdf                   (gitignored, official source)
kcet/raw/KA_engg_2025_draft_seat_matrix.pdf       (gitignored, type source)
       │  scripts/build_college_type_map.py       audited code→type derivation
       ▼
kcet/codemaps/college_type_2025.csv                (committed, 229 codes)
       │  scripts/build_clean.py                  validate + add provenance
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

College classification source (draft seat matrix, notification dated 13 Jun
2025):
- `https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/UG_Seat_Matrix_2025english.pdf`

The seat matrix classifies institutions by annexure: Government,
Government-Aided, Private Unaided, Private Unaided Minority, and Private
University. It does not print KCET college codes, so
`scripts/build_college_type_map.py` joins headings to the code-bearing cutoff
CSV only by exact normalized name containment. Seven aided/unaided split-code
cases are disambiguated by their distinct KEA course lists. UVCE is classified
from the cutoff's explicit `State Autonomous Public University` label, and
UBDT is a verified spelling/name variant of its Government Annexure A entry.

The audit produces exactly one classification row for each of 229 codes:
24 Govt, 3 Govt-Aided, 174 Private, and 28 Unknown. Unknown is intentional for
codes that the June draft omitted or did not identify uniquely. No private
classification is inferred merely from absence. The optional 2024
government-scope CSV remains archived for historical reference but is not used
to classify 2025 rows because five strict 2025 matches conflict with it.

## Commands

```bash
# 1. Copy parsed CSV and the two official PDFs from futures-v2
cp /path/to/futures-v2/state_cet/scrape/extracted_data/KA_engg_2025_all_cutoffs_R3.csv raw/
cp /path/to/futures-v2/state_cet/scrape/source/KA/engineering/KA_engg_2025_{GEN,HK}_R3.pdf raw/
# Download the official 2025 draft seat matrix above into raw/

# 2. Reproduce/check the committed code-level type map
python3 scripts/build_college_type_map.py --check

# 3. Build clean parquet
python3 scripts/build_clean.py --dry-run
python3 scripts/build_clean.py

# 4. Upload all required raw files and clean parquet to GCS
python3 scripts/upload_to_gcs.py --dry-run
python3 scripts/upload_to_gcs.py

# 5. Replace the BigQuery table
python3 scripts/load_bq.py --dry-run
python3 scripts/load_bq.py
```

## Tables

| Table | Grain | Rows | Clustering |
|---|---|---:|---|
| `kcet_fact_cutoffs` | (college_code, course_name, domicile_pool, category_code, year, round) | 13,604 | year, domicile_pool, category_code, college_code |

Column docs: [`schemas/kcet_fact_cutoffs.yaml`](schemas/kcet_fact_cutoffs.yaml).
