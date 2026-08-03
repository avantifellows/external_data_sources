# CLAUDE.md — aishe

Source-level orientation for the AISHE pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

AISHE (All India Survey on Higher Education, MoE) — **two pipelines in one folder**:

1. **Higher-ed students** (`aishe_fact_higher_ed_students`) — enrolment + graduates
   (out-turn) from AISHE Final Report workbooks. One row per cut × year × metric ×
   dimensions. Heavy parsing.

2. **Institution directory** (5 `aishe_dim_*` tables) — live registry of all HE
   institutions downloaded from the AISHE HE Directory dashboard
   (dashboard.aishe.gov.in/hedirectory). One row per institution. Light passthrough.

## Layout

```
aishe/
├── scripts/
│   ├── sources.py                    # config + Table/DirectoryTable registry (single source of truth)
│   ├── fetch.py                      # download Final Report workbooks -> raw/
│   ├── inspect_workbook.py           # diagnostic: sheet inventory + header geometry (run before a new year)
│   ├── build_programme_map.py        # 34a programme names -> discipline codemap
│   ├── clean_aishe.py                # parse Final Report xlsx -> clean/higher_ed.parquet
│   ├── build_institution_directory.py# parse HE Directory xlsx -> clean/aishe_dim_*.parquet
│   ├── upload_to_gcs.py              # raw + institution_directory raw + clean -> GCS
│   └── load_bq.py                    # GCS clean/ -> BQ (all tables in TABLES)
├── schemas/                          # one YAML per BQ output table (6 total)
├── codemaps/                         # programme_to_discipline.csv (committed)
├── raw/                              # Final Report workbooks (gitignored)
│   └── institution_directory/        # HE Directory xlsx exports (gitignored)
└── clean/                            # parsed parquets (gitignored)
```

## Pipeline 1: higher-ed students

`aishe_fact_higher_ed_students` — one denormalized fact, every row carries:
- `cut` — which published cross-tab it came from
- `metric` — `enrolment` | `graduates`
- `value` — the count

Cuts:
- `state_level` — Table 33, graduates by state × level (2021-22)
- `programme_social` — Table 34a, graduates by programme × social category (2021-22)
- `ug_discipline` — Tables 12 (enrolment) + 35 (graduates), UG by discipline, 2019-22

Dimensions a cut doesn't break out carry `"All"`. Cuts overlap — always filter to
one `cut`. Add/change tables in `sources.py` (`TABLES` registry).

### Parsing gotchas

- **Sheet names vary by year.** Match on the space-stripped, lowercased name
  (`_sheet`). This tolerates whitespace/case drift but *not* a renumbered table —
  AISHE renumbers between editions, so `33OutTurnState` may not be Table 33 next year.
- **Tables 12 and 35 share a layout** — UG by discipline, T12 = enrolment, T35 = graduates.
- **Only the discipline sheets self-describe.** `_discipline_series` (T12/T35) detects
  its header by locating the `"Discipline"` cell, so it absorbs a column shift — that's
  how 2021-22's added S.No. column was handled. **Tables 33 and 34a do not**: they read
  fixed offsets (`row[2 + i * 3 + gender]`) from a fixed start row against the fixed
  `LEVELS` / `SOCIAL_CATEGORIES` lists.
- **A layout change on T33/T34a fails silently, not loudly.** `_row()` coerces a
  non-numeric cell to `0`, so an inserted column or an added social category yields
  plausible zeros and wrong totals rather than an error. Run
  `inspect_workbook.py` before trusting a new year, and re-check the validation total.
- **`LATEST_YEAR` is a data value, not just a selector.** `state_level_rows` and
  `programme_social_rows` stamp it into `aishe_year` and `main()` only ever opens that
  one workbook — so those two cuts are single-year *by construction*. Extending them to
  a new year is a code change (thread `year` through), not a config change.
- **Discipline totals only.** Sub-discipline rows are skipped.
- **Social categories overlap.** All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS — never sum
  across `social_category`.

### Refreshing for a new AISHE Final Report

1. Add the new year's URL + path to `REPORT_URLS` / `REPORTS` in `sources.py`.
2. `fetch.py` pulls the workbook into `raw/`.
3. **`inspect_workbook.py --year <new>` — do not skip.** Confirms the sheets still
   exist under the expected names (and suggests candidates if a table was renumbered),
   and reports where data starts plus how many value columns follow. If T33 shows
   anything other than 24 value columns from index 2 (8 levels × 3 genders), or T34a
   anything other than 24 (8 social categories × 3), the positional readers in
   `clean_aishe.py` need updating before the numbers can be trusted — see the
   silent-zero gotcha above.
4. If the programme list changed, re-run `build_programme_map.py`.
5. `clean_aishe.py` → `upload_to_gcs.py --raw-only` → `upload_to_gcs.py --clean-only`
   → `load_bq.py --table aishe_fact_higher_ed_students`.

   (Bare `upload_to_gcs.py` runs the strict all-tables path — it requires *every*
   table's parquet present locally, including the dim tables. Use the scoped flags
   when refreshing only one pipeline.)

## Pipeline 2: institution directory

Five dim tables — one row per institution, passthrough from the AISHE HE Directory
dashboard export. Table config (xlsx filename, header row, column renames) lives in
`sources.py` as `DIRECTORY_TABLES: list[DirectoryTable]`.

| Table | Rows (approx) | Key columns |
|---|---|---|
| `aishe_dim_colleges` | 53,559 | aishe_code, name, state, district, college_type, management, university_aishe_code |
| `aishe_dim_universities` | 1,420 | aishe_code, name, state, university_type |
| `aishe_dim_standalone_institutions` | 16,795 | aishe_code, name, state, standalone_type, management |
| `aishe_dim_research_institutions` | 279 | aishe_code, institute_name, administrative_ministry |
| `aishe_dim_pm_vidyalaxmi_eligible_institutions` | 1,051 | aishe_code, institute_name, management_type |

All tables have `aishe_as_on_date` (snapshot date from file header) and `ingested_at`.

### Refreshing the institution directory

1. Download fresh exports from dashboard.aishe.gov.in/hedirectory → place xlsx files
   in `raw/institution_directory/` (filenames must match `INSTITUTION_DIRECTORY_RAW_FILES`
   in sources.py).
2. `build_institution_directory.py` → `upload_to_gcs.py --institution-directory-raw-only`
   → `upload_to_gcs.py --clean-only` → `load_bq.py` (or per-table with `--table`).

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't `SUM(value)` across `cut`s in `aishe_fact_higher_ed_students` — they overlap.
- Don't sum across `social_category` (overlapping bands).
- Don't treat `metric='enrolment'` as available outside the `ug_discipline` cut.
- Don't add `raw_file` / `header_row` fields to the shared `Table` dataclass —
  those belong on `DirectoryTable` (institution directory only).
