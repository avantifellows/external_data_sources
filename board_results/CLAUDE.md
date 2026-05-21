# CLAUDE.md — board_results

Source-level orientation for the board-results pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

Indian school board exam results (Class X + Class XII) from the MoE *Result of
Secondary & Higher Secondary Examination* (RSHSE) PDFs. Upstream is one report
PDF per year (`raw/*.pdf`, gitignored). Heavy PDF parsing (pdfplumber), so this
follows the `plfs/` heavy-parse shape for cleaning and the `nirf/`/`jnv/` shape
for loading (clean parquet → GCS → BQ).

## Layout

```
board_results/
├── scripts/
│   ├── sources.py                  # config + Table/RawFile registries + REPORT_URLS (single source of truth)
│   ├── fetch.py                    # download raw PDFs from REPORT_URLS -> raw/ (regenerable)
│   ├── parse_overall.py            # build_df(): Sec A/B overall tables (Class X+XII)
│   ├── parse_class_xii_stream.py   # build_df(): Sec B stream tables (Class XII)
│   ├── clean_board_results.py      # merge both build_df() -> clean/board_results.parquet (one fact)
│   ├── upload_to_gcs.py            # raw PDFs (as-is) + clean fact -> gs://…/board_results/{raw,clean}/
│   └── load_bq.py                  # GCS clean/ -> avantifellows.external_data_sources.board_results_fact_passes
├── schemas/                        # one YAML per BQ table (just board_results_fact_passes)
├── raw/                            # source PDFs (gitignored)
└── clean/                          # parsed parquet (gitignored)
```

**One denormalized fact**, `board_results_fact_passes` — the overall (Class X+XII)
and Class XII stream cuts merged on one grain, with `"All Categories"` /
`"All Streams"` sentinels for dimensions a cut doesn't break out. `parse_*.py`
each expose a `build_df()`; `clean_board_results.py` merges and writes the single
parquet. Add/change tables in `scripts/sources.py` (the `TABLES` registry); the
loader and uploader iterate over it.

## Parsing gotchas (carried over from the original extractors)

- **Section disambiguation.** Section A = Class X, Section B = Class XII. The
  section a page belongs to is detected from divider pages + the running page
  header — and the header check looks only at the first line, because board
  names contain "Higher Secondary" and would otherwise mis-flip the section.
- **Table numbers move across years.** Overall = Table 3 (2020/21) / Table 1
  (2022/24); stream = Tables 13/15/17 (2020/21) / 31/33/35 (2022/24). Anchored
  in `sources.py`-adjacent config inside each cleaner.
- **2020 layout is fragile.** pdfplumber over-splits the 2020 PDF into ~54
  physical columns with drifting positions; the 2020 stream parser compresses
  non-empty cells and assumes left-to-right stream order. See README caveat.
- **Schema differs by year.** 2020/2021 overall tables omit the Registered
  column → `registered` is NULL (nullable Int64) for those years.
- **Whitespace.** Board/state names are whitespace-normalized (newlines →
  spaces) so BQ strings are single-line. The original CSV extractor left
  newlines in the stream table; this port fixes that.
- **Blacked-out cells dropped, not zeroed.** Missing values are omitted.

## Refreshing for a new RSHSE release

1. Add the new year's URL + path to `REPORT_URLS` and `REPORTS` in `sources.py`,
   and the year to the loops in the parsers. Then `fetch.py` pulls it.
2. Confirm the table numbers for the new layout (they shift between the
   compact and expanded report formats).
3. `fetch.py` → `clean_board_results.py` → `upload_to_gcs.py` → `load_bq.py`.
   Loads are `WRITE_TRUNCATE`.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't `SUM(passed)` across rows of different grain — filter to one slice
  (overall vs a stream/category breakdown) using the `"All"` sentinels first.
- Don't sum across `social_category` (overlapping) or treat blacked-out streams
  as zero.
