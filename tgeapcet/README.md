# tgeapcet/

TG-EAPCET (Telangana) engineering admission cutoffs — last admitted state rank
for every (institute, branch, category, gender) seat bucket, 2025-26.
20,449 rows across 162 institutes.

New here? Read [`schemas/README.md`](schemas/README.md) — "TG-EAPCET in 60
seconds". **Gender is part of the grain**, which is the easiest way to get a
wrong answer from this table.

## Pipeline shape

```
futures-v2/state_cet/scrape/scripts/state_TG.py   parse the 3 phase PDFs
       │
       ▼
tgeapcet/raw/TG_engg_all_cutoffs_2025.csv           (gitignored)
tgeapcet/raw/TG_engg_closing_ranks_govt_2025.csv    (gitignored)
tgeapcet/raw/TG_engg_consolidated_5cat_govt_2025.csv (gitignored, optional)
tgeapcet/raw/pdfs/*.pdf                             (gitignored, 3 official PDFs)
       │  scripts/build_clean.py   MAX across phases for ALL institute types,
       │                           widen canonical cols, validate
       ▼
tgeapcet/clean/tgeapcet_fact_cutoffs.parquet        (gitignored)
       │  scripts/upload_to_gcs.py
       ▼
gs://avantifellows-external-data/tgeapcet/{raw,clean}/
       │  scripts/load_bq.py       PARQUET, WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.tgeapcet_fact_cutoffs   (asia-south1)
```

## Refresh

```bash
# 1. regenerate the raw CSVs upstream
cd ~/jan2023/futures-v2
#    download the 3 phase PDFs into state_cet/scrape/source/TG/engineering/
#    from https://tgeapcetd.nic.in/files/
python state_cet/scrape/scripts/state_TG.py

# 2. copy raw CSVs + PDFs into tgeapcet/raw/ and rebuild
cd ~/jan2023/external_data_sources/tgeapcet
python scripts/build_clean.py --dry-run   # validates anchors, writes nothing
python scripts/build_clean.py
python scripts/upload_to_gcs.py --with-pdfs
python scripts/load_bq.py
```

`build_clean.py` asserts source anchors (row counts, JNTUH CSE OC_BOYS = 1228,
and a line-wrap regression guard). Those assertions are **expected to fail** on
a genuine refresh — when they do, confirm the change is real and update them in
the same commit as the cause. Never relax an assertion to make a build pass.

## Govt scope is a query

All institute types ship. Government scope is
`college_type IN ('Govt','State-Univ-Dept')` — 1,936 rows across 20 colleges.
Same choice as `kcet/`, `mhtcet/` and `gujcet/`: scope is a query, not a
pipeline decision, so the predictor can show private colleges too.
