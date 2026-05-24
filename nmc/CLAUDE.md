# CLAUDE.md — nmc

Source-level orientation for the NMC MBBS seat-matrix pipeline. Read the
top-level `../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

The NMC (National Medical Commission) UG (MBBS) seat matrix — the state-wise
list of all MBBS medical colleges (including AIIMS & JIPMER) functioning in the
country, with each college's affiliating university, management, year of
inception, and annual intake of UG seats. Upstream is one report PDF
(`raw/*.pdf`, gitignored, ~780 colleges over 35 pages). PDF parsing (pdfplumber),
so this follows the `board_results/` heavy-parse shape for cleaning and the
`nirf/`/`board_results/` shape for loading (clean parquet → GCS → BQ).

## Layout

```
nmc/
├── scripts/
│   ├── sources.py          # config + Table/RawFile registries + PDF_URL (single source of truth)
│   ├── fetch.py            # download raw PDF from PDF_URL -> raw/ (regenerable)
│   ├── clean_nmc.py        # parse the PDF -> clean/mbbs_seats.parquet (one fact)
│   ├── upload_to_gcs.py    # raw PDF (as-is) + clean fact -> gs://…/nmc/{raw,clean}/
│   └── load_bq.py          # GCS clean/ -> avantifellows.external_data_sources.nmc_fact_mbbs_seats
├── schemas/                # one YAML per BQ table (just nmc_fact_mbbs_seats)
├── raw/                    # source PDF (gitignored)
└── clean/                  # parsed parquet (gitignored)
```

**One denormalized fact**, `nmc_fact_mbbs_seats` — one row per college, grain
`(snapshot, sl_no)`. `clean_nmc.py` exposes a `build_df()` and writes the single
parquet. Add/change tables in `scripts/sources.py` (the `TABLES` registry); the
loader and uploader iterate over it.

## Parsing notes

- **Uniform layout.** Every page (`page.extract_tables()`) yields exactly one
  8-column table: Sl.No | State | College | District | University | Management |
  Year of Inception | Annual Intake (Seats). Column positions are constants in
  `clean_nmc.py`.
- **Row filter.** Keep rows whose `Sl.No` is a digit — this drops the page-0
  title row, the repeated column-header row, and the grand-total footer row
  (blank Sl.No, seats = 118,190, used only as the validation target).
- **Whitespace.** Every text cell is `\s+`-collapsed to single spaces, because
  the source wraps long college / university / district names across multiple
  lines inside a cell.
- **State forward-fill.** State is carried forward when a row's State cell is
  blank (a safety net; this PDF happens to repeat it on every row).
- **Year recovery.** `year_of_inception` = first `\d{4}` run in the cell. Two
  rows have the management value wrapping into the year column
  (`Govt. Societ` | `y 2024`); the 4-digit extraction absorbs the stray `y`.
- **Nullable ints.** `sl_no`, `year_of_inception`, `annual_intake_seats` are
  pandas nullable `Int64`.

## Refreshing for a new release

1. Update `PDF_URL` (and the `raw/` filename if it changes) in `sources.py`.
2. `fetch.py` → `clean_nmc.py` → `upload_to_gcs.py` → `load_bq.py`. Loads are
   `WRITE_TRUNCATE`. If the snapshot year changes, bump `SNAPSHOT` in
   `sources.py`.
3. Confirm the 8-column layout still holds — if NMC changes the report format,
   the column-index constants in `clean_nmc.py` need revisiting.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't `SUM(annual_intake_seats)` together with the grand-total footer — it's
  excluded from the table; the per-college rows already sum to 118,190.
- Don't exact-match `management` for Govt colleges — filter
  `management_category = 'Government'` (the derived bucket already folds the
  `Govt`, `Govt.`, `Govt- Society`, `Govt. Societ` variants together).
