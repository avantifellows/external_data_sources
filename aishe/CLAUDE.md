# CLAUDE.md — aishe

Source-level orientation for the AISHE pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

AISHE (All India Survey on Higher Education, MoE) student data — **enrolment +
graduates (out-turn)**. Upstream is one Excel **Final Report** workbook per
academic year (`raw/*.xlsx`, gitignored). The workbooks need real parsing, so
this folder follows the `plfs/` (heavy parse) shape for cleaning but the `nirf/`
(parquet → GCS → BQ) shape for loading.

## Layout

```
aishe/
├── scripts/
│   ├── sources.py            # config + Table registry + REPORT_URLS (single source of truth)
│   ├── fetch.py              # download raw workbooks from REPORT_URLS -> raw/ (regenerable)
│   ├── build_programme_map.py# 34a programme names -> discipline (heuristic) -> codemaps/*.csv
│   ├── clean_aishe.py        # parse raw/*.xlsx -> clean/higher_ed.parquet (one fact)
│   ├── upload_to_gcs.py      # raw sheets + clean fact -> gs://…/aishe/{raw,clean}/ (both parquet)
│   └── load_bq.py            # GCS clean/ -> avantifellows.external_data_sources.aishe_fact_higher_ed
├── schemas/                  # one YAML per BQ table (just aishe_fact_higher_ed)
├── codemaps/                 # programme_to_discipline.csv (committed, auditable)
├── raw/                      # source workbooks (gitignored)
└── clean/                    # parsed parquet (gitignored)
```

**One denormalized fact**, `aishe_fact_higher_ed`. Every row carries a `cut`
(which published cross-tab it came from) and a `metric` (`enrolment` |
`graduates`); the measure is `value`:

- `cut='state_level'` — Table 33, graduates by state × level (2021-22)
- `cut='programme_social'` — Table 34a, graduates by programme × social category (2021-22)
- `cut='ug_discipline'` — Tables 12 (enrolment) + 35 (graduates), UG by discipline, 2019-22

Dimensions a cut doesn't break out carry the `"All"` sentinel. The cuts overlap,
so always filter to one `cut`. Add/change tables in `scripts/sources.py` (the
`TABLES` registry) — every other script iterates over it. Exploratory analysis
(discipline rollup, projection, wage-bucket grouping) is NOT in this repo — it
runs locally; intents live in `bq-assistant/docs/analyses/external_data_sources.yaml`.

## Parsing gotchas (carried over from the original extractors)

- **Sheet names vary by year.** Match on the space-stripped, lowercased name
  (`12UGDisc` has a trailing space; `_sheet()` in clean_aishe.py handles this).
- **Tables 12 and 35 share a layout** — UG by discipline, Table 12 = enrolment,
  Table 35 = graduates. `_discipline_series(ws, year, metric)` parses both.
- **Column layout shifts across years.** 2019-20/2020-21 UG-discipline sheets
  put Discipline in column 0; 2021-22 added an S.No. column, shifting it to
  column 1. `_discipline_series()` auto-detects by locating the row whose cell
  equals `"Discipline"` exactly.
- **Discipline totals only.** Sub-discipline (subject) rows are skipped; a
  discipline total row has an empty Subject column or a name ending in "Total".
- **Two incompatible taxonomies.** Tables 12/35 classify by *subject* (AISHE
  disciplines); Table 34a classifies by *degree programme*. The
  programme→discipline codemap maps by degree name and cannot recover
  subject-based disciplines (Indian Language, Social Science, …). See README.
- **Social categories overlap.** All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS —
  never sum across `social_category`.

## Refreshing for a new AISHE release

1. Add the new year's URL + path to `REPORT_URLS` / `REPORTS` in `sources.py`,
   then `fetch.py` pulls the workbook into `raw/`.
2. If the programme list changed, re-run `build_programme_map.py` and review the
   diff in `codemaps/programme_to_discipline.csv`.
3. `fetch.py` → `clean_aishe.py` → `upload_to_gcs.py` → `load_bq.py`. Loads are
   `WRITE_TRUNCATE` (idempotent). The fact keys on `aishe_year`, so adding a new
   report year appends naturally.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't `SUM(value)` across `cut`s — they overlap (different views of the same
  students). Filter to one `cut` (and one `metric`) first.
- Don't sum across `social_category` (overlapping bands).
- Don't treat `metric='enrolment'` as available outside the `ug_discipline` cut.
