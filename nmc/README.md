# nmc

Indian MBBS (UG) medical-college seat matrix → BigQuery.

The state-wise list of all ~780 MBBS medical colleges (including AIIMS &
JIPMER) functioning in the country for admission year 2024-25, with each
college's affiliating university, management, year of inception, and **annual
intake of UG seats** (118,190 total). PDF parse (pdfplumber over the NMC seat-
matrix PDF), then parsed parquet → GCS → BQ.

**Source:** National Medical Commission (NMC), *Revised UG Seat Matrix 2024-25*
(as on 31-03-2025), [nmc.org.in](https://www.nmc.org.in/). One PDF, 35 pages.
Not redistributed in git — see *Raw data* below.

## Pipeline at a glance

```
nmc.org.in Revised UG Seat Matrix PDF        (canonical source URL in sources.py)
       │ scripts/fetch.py
       ▼
raw/nmc_mbbs_seat_matrix_2024-25.pdf         (local; gitignored)
       │ scripts/clean_nmc.py                 (parse 35 pages → one fact)
       ▼
clean/mbbs_seats.parquet                     (local; gitignored)
       │ scripts/upload_to_gcs.py   (uploads raw PDF + clean fact)
       ▼
gs://avantifellows-external-data/nmc/raw/<pdf>              (traceability)
gs://avantifellows-external-data/nmc/clean/mbbs_seats.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.nmc_fact_mbbs_seats   (asia-south1)
```

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Table produced

**`nmc_fact_mbbs_seats`** — one row per MBBS medical college. Grain:
`(snapshot, sl_no)`.

| Column | Type | Notes |
|---|---|---|
| `snapshot` | STRING | Constant `"2024-25"`. |
| `sl_no` | INTEGER | Serial number from the PDF (1..780), unique within snapshot. |
| `state` | STRING | State/UT (forward-filled if a cell is blank). |
| `college` | STRING | Name + address of the college (whitespace normalized). |
| `district` | STRING | District. |
| `university` | STRING | Affiliating university. |
| `management_category` | STRING | Normalized bucket of `management`: Government / Private / Trust / Society / Deemed / Other. The clean column for govt-vs-private. |
| `management` | STRING | Raw source text: `Govt.`, `Trust`, `Society`, `Private`, `Govt- Society`, … |
| `year_of_inception` | INTEGER | Year established (nullable). |
| `annual_intake_seats` | INTEGER | Annual UG (MBBS) seat intake. |

Schema: [`schemas/nmc_fact_mbbs_seats.yaml`](schemas/nmc_fact_mbbs_seats.yaml).

**Validation:** 780 college rows; `SUM(annual_intake_seats) = 118,190` (matches
the grand-total footer row in the source PDF, which is excluded from the table).

Management breakdown (colleges / seats):

| `management_category` | Colleges | Seats |
|---|---:|---:|
| Government | 430 | 60,324 |
| Trust / Society / Private | 350 | 57,866 |

(Use `management_category = 'Government'` rather than matching `management` text.)

## GCS layout

```
gs://avantifellows-external-data/
  nmc/raw/nmc_mbbs_seat_matrix_2024-25.pdf   ← source NMC PDF, as-is (traceability)
  nmc/clean/mbbs_seats.parquet               ← the fact; load_bq.py loads this
```

## Raw data

The seat-matrix PDF is gitignored (`raw/*.pdf`) and **fetched from source** by
`scripts/fetch.py` (canonical URL in `scripts/sources.py` → `PDF_URL`) — no
manual download:

| File | Source URL (nmc.org.in/wp-content/uploads/2025/04/) |
|---|---|
| `nmc_mbbs_seat_matrix_2024-25.pdf` | `Revised UG Seat Matrix 2024-25 on 31-03-2025.pdf` |

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for upload + load
```

## Running

```bash
# 0. fetch the raw PDF from source → raw/  (regenerable; no manual download)
.venv/bin/python scripts/fetch.py            # --force to re-download

# 1. parse the PDF → clean/mbbs_seats.parquet
.venv/bin/python scripts/clean_nmc.py

# 2. stage to GCS — uploads raw PDF + the clean fact
.venv/bin/python scripts/upload_to_gcs.py --dry-run   # preview
.venv/bin/python scripts/upload_to_gcs.py             # raw + clean
#   …or just one side: --raw-only / --clean-only

# 3. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run         # preview
.venv/bin/python scripts/load_bq.py
```

`load_bq.py` uses `WRITE_TRUNCATE`, so the load fully replaces the table. Only
the clean fact is loaded to BQ — the raw PDF on GCS is for traceability.

## Caveats — read before analysing

- **`snapshot` is a single point-in-time.** This is the 2024-25 seat matrix as
  revised on 31-03-2025. NMC publishes revised matrices through the cycle;
  re-fetch for a later cut.
- **`management` carries source-text quirks.** Values are whitespace-normalized
  source strings. A couple are truncated by source line-wrap (`Govt. Societ`
  for "Govt. Society"); filter Govt-managed colleges with
  `management LIKE 'Govt%'` rather than exact-matching the variants.
- **The grand-total footer is dropped.** The PDF's last row is an all-India
  total (118,190) with a blank Sl.No; it's skipped by the `Sl.No is a digit`
  filter (use it only as the validation target).
- **`year_of_inception` is the first 4-digit run in the cell.** Two rows have
  the management value wrapping into the year column (`Govt. Societ` | `y 2024`);
  the 4-digit extraction recovers the year cleanly.
