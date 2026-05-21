# CLAUDE.md — aishe

Source-level orientation for the AISHE pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

AISHE (All India Survey on Higher Education, MoE) out-turn data. Upstream is one
Excel **Final Report** workbook per academic year (`raw/*.xlsx`, gitignored).
The workbooks need real parsing, so this folder follows the `plfs/` (heavy
parse) shape for cleaning but the `nirf/` (parquet → GCS → BQ) shape for
loading.

## Layout

```
aishe/
├── scripts/
│   ├── sources.py            # config + Table registry (single source of truth)
│   ├── build_programme_map.py# 34a programme names -> discipline (heuristic) -> codemaps/*.csv
│   ├── clean_aishe.py        # parse raw/*.xlsx -> clean/outturn.parquet (one fact)
│   ├── upload_to_gcs.py      # raw sheets + clean fact -> gs://…/aishe/{raw,clean}/ (both parquet)
│   └── load_bq.py            # GCS clean/ -> avantifellows.external_data_sources.aishe_fact_outturn
├── schemas/                  # one YAML per BQ table (just aishe_fact_outturn)
├── analyses/                 # question writeup + derived rollup/projection scripts
├── codemaps/                 # programme_to_discipline.csv (committed, auditable)
├── raw/                      # source workbooks (gitignored)
└── clean/                    # parsed parquet (gitignored)
```

**One denormalized fact**, `aishe_fact_outturn` — Tables 33 (state×level), 34a
(programme×social) and 35 (UG discipline, 2019-22) unified with the `"All"`
sentinel for dimensions a cut doesn't break out. Derived cuts (discipline×social
rollup, 2025-26 projection) live in `analyses/`, not as tables. The questions
that drive this shape are in `analyses/README.md`. Add/change tables in
`scripts/sources.py` (the `TABLES` registry) — every other script iterates over it.

## Parsing gotchas (carried over from the original extractors)

- **Sheet names vary by year.** Match on the space-stripped, lowercased name
  (`12UGDisc` sometimes has a trailing space; `_sheet()` in clean_aishe.py
  handles this).
- **Column layout shifts across years.** 2019-20/2020-21 UG-discipline sheets
  put Discipline in column 0; 2021-22 added an S.No. column, shifting it to
  column 1. `_parse_discipline_series()` auto-detects by locating the row whose
  cell equals `"Discipline"` exactly.
- **Discipline totals only.** Sub-discipline (subject) rows are skipped; a
  discipline total row has an empty Subject column or a name ending in "Total".
- **Two incompatible taxonomies.** Table 35 classifies by *subject* (rolled into
  AISHE disciplines); Table 34a classifies by *degree programme*. The
  programme→discipline codemap maps by degree name and cannot recover
  subject-based disciplines (Indian Language, Social Science, …). See README.
- **Social categories overlap.** All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS —
  never sum across `social_category`.

## Refreshing for a new AISHE release

1. Download the new Final Report `.xlsx` into `raw/` (canonical filename).
2. If the programme list changed, re-run `build_programme_map.py` and review the
   diff in `codemaps/programme_to_discipline.csv`.
3. `clean_aishe.py` → `upload_to_gcs.py` → `load_bq.py`. Loads are
   `WRITE_TRUNCATE` (idempotent). The fact keys on `aishe_year`, so adding a new
   report year appends naturally.

## Don't

- Don't commit anything under `raw/` or `clean/` — they're gitignored data.
- Don't `SUM(out_turn)` across rows of different grain — filter to one slice
  (state, programme, or discipline) using the `"All"` sentinels first.
- Don't sum across `social_category` (overlapping) or treat the `analyses/`
  rollup / projection as published AISHE figures (both are derived).
