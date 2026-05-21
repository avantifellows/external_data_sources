# board_results

Indian school board examination results (Class X + Class XII) → BigQuery.

Pass figures across all ~41-58 boards (CBSE, CISCE, every state board, open
schools), by year, gender, social category, and Class XII stream. Heavy PDF
parse (pdfplumber over the MoE report PDFs), then parsed parquet → GCS → BQ.

**Source:** Ministry of Education, *Result of Secondary & Higher Secondary
Examination* (RSHSE) annual reports, [education.gov.in](https://www.education.gov.in/).
One PDF per year (2020, 2021, 2022, 2024 — no 2023 edition was published). Not
redistributed in git — see *Raw data* below.

## Pipeline at a glance

```
education.gov.in RSHSE PDFs                  (canonical source URLs in sources.py)
       │ scripts/fetch.py
       ▼
raw/moe_results_secondary_hs_<year>.pdf     (local; gitignored)
       │ scripts/parse_overall.py            (Class X+XII overall)
       │ scripts/parse_class_xii_stream.py   (Class XII by stream/social cat)
       │ scripts/clean_board_results.py      (merges both → one fact)
       ▼
clean/board_results.parquet                 (local; gitignored)
       │ scripts/upload_to_gcs.py   (uploads raw PDFs + clean fact)
       ▼
gs://avantifellows-external-data/board_results/raw/<pdf>             (traceability)
gs://avantifellows-external-data/board_results/clean/board_results.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.board_results_fact_passes   (asia-south1)
```

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Table produced

**`board_results_fact_passes`** — one wide fact. Grain:
`(year, level, state, board, social_category, stream, gender)` → `passed`
(+ `registered`, `appeared`, `pass_percentage` on the overall rows). It unifies
two published cuts; dimensions a cut doesn't break out carry `"All Categories"`
/ `"All Streams"`:

| Cut | Source | Set dimensions | Measures |
|---|---|---|---|
| Class X + XII overall | Sec A/B Table 3 (2020/21), Table 1 (2022/24) | level, state, board | registered, appeared, passed, pass_percentage |
| Class XII stream      | Sec B Tables 13/15/17 (2020/21), 31/33/35 (2022/24) | + social_category, stream | passed only |

`registered` / `appeared` / `pass_percentage` are populated only on the overall
(All Categories, All Streams) rows. **Query by filtering to one slice — don't
`SUM(passed)` across overlapping categories or across stream + All Streams.**

Schema: [`schemas/board_results_fact_passes.yaml`](schemas/board_results_fact_passes.yaml).

**Validation** (all-India sum of board Totals, `passed`, overall rows):

| Year | Class X | Class XII |
|---|---:|---:|
| 2020 | 15,768,194 | 12,155,004 |
| 2021 | 18,973,895 | 14,456,792 |
| 2022 | 15,848,975 | 12,465,635 |
| 2024 | 16,337,153 | 12,929,386 |

(2021's spike is the COVID-era universal-promotion year.)

## GCS layout

```
gs://avantifellows-external-data/
  board_results/raw/<pdf>                      ← source MoE PDFs, as-is (traceability)
  board_results/clean/board_results.parquet    ← the fact; load_bq.py loads this
```

## Raw data

The report PDFs are gitignored (`raw/*.pdf`) and **fetched from source** by
`scripts/fetch.py` (canonical URLs in `scripts/sources.py` → `REPORT_URLS`) — no
manual download:

| File | Source URL (education.gov.in/…/statistics-new/) |
|---|---|
| `moe_results_secondary_hs_2020.pdf` | `Result_Secondary_Higher_Secondary_Examination_2020.pdf` |
| `moe_results_secondary_hs_2021.pdf` | `RSHSE2021.pdf` |
| `moe_results_secondary_hs_2022.pdf` | `RSHSE2022.pdf` |
| `moe_results_secondary_hs_2024.pdf` | `result-2024.pdf` |

(MoE did not publish a 2023 edition.)

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for upload + load
```

## Running

```bash
# 0. fetch the raw PDFs from source → raw/  (regenerable; no manual download)
.venv/bin/python scripts/fetch.py            # --force to re-download, --year YYYY for one

# 1. parse the PDFs and merge → clean/board_results.parquet
.venv/bin/python scripts/clean_board_results.py

# 2. stage to GCS — uploads raw PDFs + the clean fact
.venv/bin/python scripts/upload_to_gcs.py --dry-run   # preview
.venv/bin/python scripts/upload_to_gcs.py             # raw + clean
#   …or just one side: --raw-only / --clean-only

# 3. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run         # preview
.venv/bin/python scripts/load_bq.py
```

`load_bq.py` uses `WRITE_TRUNCATE`, so the load fully replaces the table. Only
the clean fact is loaded to BQ — the raw PDFs on GCS are for traceability.
(`parse_overall.py` and `parse_class_xii_stream.py` are parser modules invoked
by `clean_board_results.py`.)

## Caveats — read before analysing

- **CBSE stream split missing for 2020 & 2021.** The MoE compilation publishes
  CBSE's All-Streams total but blacks out the per-stream split for those years
  (CBSE 2020: 1,126,282; 2021: 1,391,539 students with no stream split). CISCE
  has stream data for all four years. CBSE's own press releases are the fill
  source if needed.
- **Blacked-out cells are dropped, not zero.** A missing stream/category cell
  is omitted from the table rather than recorded as 0. Don't treat absence as 0.
- **Social categories overlap.** SC/ST ⊂ All Categories — never sum across
  `social_category`.
- **2020 PDF parsing is heuristic.** That report's layout makes pdfplumber's
  grid detection unstable; the 2020 stream parser compresses non-empty cells and
  assumes streams in fixed left-to-right order. Correct when all 5 streams (or
  only Vocational missing) are present; can mis-attribute if a non-trailing
  stream is blacked out (rare). Cross-check suspicious 2020 rows against the PDF.
- **Board names vary across years.** The MoE re-types names yearly; fuzzy-join
  on key tokens (CBSE, CISCE, state name) rather than exact string match.
- **Class X has no stream cut** — by design (streams begin in Class XI).
