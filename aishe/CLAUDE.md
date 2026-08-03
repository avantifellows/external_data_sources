# CLAUDE.md — aishe

Source-level orientation for the AISHE pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

AISHE (All India Survey on Higher Education, MoE) — **two pipelines in one folder**:

1. **Higher-ed students** (`aishe_fact_higher_ed_students`) — enrolment + graduates
   (out-turn) from AISHE Final Reports, 2015-16 → 2021-22. One row per cut × year ×
   metric × dimensions. Heavy parsing, and **two parsers**, because AISHE publishes
   two editions: Excel from 2019-20 on (`clean_aishe.py`, openpyxl) and PDF for
   every year (`parse_report_pdf.py`, pdfplumber). Pre-2019 exists ONLY as PDF.
   `clean_aishe.py` is the single entry point — it calls the PDF parser itself.

2. **Institution directory** (5 `aishe_dim_*` tables) — live registry of all HE
   institutions downloaded from the AISHE HE Directory dashboard
   (dashboard.aishe.gov.in/hedirectory). One row per institution. Light passthrough.

## Layout

```
aishe/
├── scripts/
│   ├── sources.py                    # config + Table/DirectoryTable/PdfTable registry (single source of truth)
│   ├── fetch.py                      # download reports -> raw/  (--from-gcs restores the workbooks)
│   ├── inspect_workbook.py           # diagnostic: sheet inventory + header geometry (run before a new year)
│   ├── build_programme_map.py        # 34a programme names -> discipline codemap
│   ├── clean_aishe.py                # parse xlsx + call the PDF parser -> clean/higher_ed.parquet
│   ├── parse_report_pdf.py           # parse Final Report PDFs (the pre-2019 years)
│   ├── build_institution_directory.py# parse HE Directory xlsx -> clean/aishe_dim_*.parquet
│   ├── upload_to_gcs.py              # raw + institution_directory raw + clean -> GCS
│   └── load_bq.py                    # GCS clean/ -> BQ (all tables in TABLES)
├── schemas/                          # one YAML per BQ output table (6 total)
├── codemaps/                         # programme_to_discipline.csv, discipline_to_stem.csv (committed)
├── raw/                              # Final Report workbooks + PDFs (gitignored)
│   └── institution_directory/        # HE Directory xlsx exports (gitignored)
└── clean/                            # parsed parquets (gitignored)
```

## Pipeline 1: higher-ed students

`aishe_fact_higher_ed_students` — one denormalized fact, every row carries:
- `cut` — which published cross-tab it came from
- `metric` — `enrolment` | `graduates`
- `value` — the count

Cuts:
- `state_level` — Table 33, graduates by state × level (2015-16 … 2018-19, 2021-22)
- `programme_social` — Table 34a, graduates by programme × social category (2021-22 ONLY)
- `ug_discipline` — Tables 12 (enrolment) + 35 (graduates), UG by discipline
  (2015-16, 2016-17, 2018-19, 2019-22)

**Coverage is ragged and that is the main trap.** Not every year carries every
cut, so a query that doesn't `GROUP BY aishe_year` will read missing coverage as a
real trend. `programme_social` is 2021-22 only — the pre-2019 editions print a
Table 34 with no social-category breakdown at all.

Dimensions a cut doesn't break out carry `"All"`. Cuts overlap — always filter to
one `cut`. Add/change tables in `sources.py` (`TABLES` registry).

**`RAW_SHEETS` is the parse registry.** Each entry is `(year, sheet, cut, metric)`, and
`clean_aishe.py` builds exactly what's declared there — so which cuts a year contributes
is config, not code. It's the same list `upload_to_gcs.py` mirrors to GCS `raw/`, so the
traceability dump and the parse can't drift apart.

### Parsing gotchas

- **Sheet names vary by year.** Match on the space-stripped, lowercased name
  (`_sheet`). This tolerates whitespace/case drift but *not* a renumbered table —
  AISHE renumbers between editions, so `33OutTurnState` may not be Table 33 next year.
- **Tables 12 and 35 share a layout** — UG by discipline, T12 = enrolment, T35 = graduates.
- **Every reader detects its own geometry — none assume fixed columns.**
  `discipline_rows` (T12/T35) locates the `"Discipline"` cell; `_crosstab_geometry`
  (T33/T34a) locates the `Male/Female/Total` header row, taking the value block's start
  and width from it, so an inserted S.No. or state-code column shifts harmlessly. It
  additionally verifies the merged group-label row against `LEVELS` /
  `SOCIAL_CATEGORIES` — order matters, because the read within the block is positional.
- **Value cells fail loudly.** `_num()` maps blanks and `-`/`NA`/`nil` to 0 but raises
  on any other text. That is the tripwire for a layout shift: a label landing in a value
  column is an error, not a `0`. (Before this, an inserted column silently produced 864
  plausible-looking rows whose UG total was 6,768 instead of 7,754,223.)
- **Discipline totals only.** Sub-discipline rows are skipped.
- **Social categories overlap.** All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS — never sum
  across `social_category`.

### The PDF parser (`parse_report_pdf.py`)

`PDF_TABLES` in `sources.py` is its parse registry — the PDF counterpart of
`RAW_SHEETS`. Entries are `(year, label, title_re, cut, metric)`, and tables are
located by their **printed caption**, not a page number: pagination moves between
editions but captions are stable. The separator after the table number varies
('.' in 2015-18, ':' in 2018-19), hence `[.:]` in every pattern.

**`PDF_TABLES` is deliberately not a cross product of years × tables.** All four
registered editions print tables 12/33/34/35, but they do not lay them out the
same way, and seven `(year, table)` pairs currently fail their reconciliation
check. Those are commented out in `sources.py` with the exact discrepancy. Do not
"fix" that by adding them back — the check is what makes the table trustworthy.

**Everything is reconciled against a published total, and the build dies if it
doesn't match.** This is not belt-and-braces; every single one of these was a real
bug that produced *plausible* numbers:

| Failure mode | What it looked like |
|---|---|
| Column-number row read as data | +45 on a 4.3M total |
| Wrapped label welded to the next row | −32,847, one state silently dropped |
| Two adjacent rows merged into one | a UG total of 1,086,637,865 |
| Subject row taken as a discipline | +38,652 — still a credible national figure |
| Page footer read as a row | `T-44` in a value column |
| Sheet roll-up emitted as a discipline | 2019-20 / 2020-21 UG totals **exactly doubled** |

That last one was in the **Excel** reader, not the PDF one, and it sat in the
production table until 2026-08. `discipline_rows` strips a trailing "Total" from
the label, which turned the sheet's `Grand Total` row into a discipline named
`Grand`; since that row equals the sum of the disciplines, `SUM(value)` for those
two years returned twice the truth. It went unnoticed because neither year carries
a `state_level` cut, so the cross-cut check had nothing to compare against. Both
readers now validate against the published roll-up instead of emitting it.

So: **never widen a tolerance to make a check pass.** The checks are
`_check_grand_total` (Table 33: levels must sum to the published `Grand Total`
column) and `_check_total` (Tables 12/34/35: rows must sum to the published Grand
Total row).

### PDF parsing gotchas

- **Rows are anchored on the serial number, not on having values.** A state that
  reports nothing at some levels has a blank row that still carries its serial; a
  wrapped label has no serial. Both alternatives break: "line with values starts a
  row" loses Daman and Diu, and "a continuation belongs to the row above" breaks
  where the label wraps *around* its values (Table 33 page 3 sets the Andaman and
  Nicobar Islands digits on the middle of three lines).
- **The serial column must be proven, not guessed.** Its presence comes from the
  column-number row's length (`n_values + 2` means serial + label + values;
  `n_values + 1` means no serial). Reading Table 12's leading "1" as a serial drops
  every row. And do NOT match a row's serial against that row's x position — the
  column-number row's own "1" is typeset ~9pt left of where the data serials sit.
- **2016-17 sets the serial hard against the label** — it extracts as one word
  (`1Ph.D.-Doctor`), so the digits are split off by regex.
- **Tables 12/34/35 are read line-by-line, not by column geometry.** Their rows sit
  as little as 7pt apart with differing indents, so assigning words to column bands
  interleaves two rows and concatenates their digits. Anchoring on "three integers
  at end of line" cannot do that.
- **Table 12/35 use no orphan attachment.** That table has a second, merged label
  column holding the discipline name across its block of subject rows; treating it
  as a wrapped label produces `Gandhian Grand Total Studies`.
- **The discipline/subject margin is measured across ALL of the table's pages.** In
  2016-17 and 2017-18 Table 35 is a *ranked list* whose subject rows and discipline
  rows land on different pages, so a per-page margin returns subjects.
- **Roll-up rows are anchors, never data.** Every reader holds the published
  `Grand Total` / `All India` row back and validates against it. Emitting one as a
  dimension value doubles the year's total — see the table above.
- **Discipline labels need whitespace normalising.** AISHE varies internal spacing
  between editions (`Footwear  Design` vs `Footwear Design`), which silently splits
  one discipline into two values and breaks trends and codemap joins.
- **Grand Total is a group, not a level.** Table 33 prints 9 groups: the 8 levels
  plus a roll-up. It is read for validation and never emitted. The Excel sheet does
  this too — that is what the strict geometry check in `clean_aishe.py` trips on if
  `STATE_LEVEL_GROUPS` loses its 9th entry.

### Adding a year from PDF

1. `fetch.py --year <new>` (PDFs come from the MoE CDN and all currently work).
2. Confirm the captions really match before registering anything:
   `grep -c` the title patterns, or run `parse_report_pdf.py --year <new> --debug`.
   A non-matching pattern raises; a pattern matching the *wrong* table does not.
3. Add the `(year, table)` pairs to `PDF_TABLES`, one at a time.
4. Run `parse_report_pdf.py --year <new>`. If a reconciliation fails, fix the read
   or leave the pair out with a comment saying why. Never load an unreconciled table.

### Refreshing for a new AISHE Final Report

1. Add the new year's URL + path to `REPORT_URLS` / `REPORTS` in `sources.py`.
2. `fetch.py` pulls the workbook into `raw/`.
3. **`inspect_workbook.py --year <new> --all-sheets` — do not skip.** AISHE renumbers
   tables between editions, so this is how you learn the real sheet names (it suggests
   candidates for a renumbered table). It also reports the value-block width per sheet.
4. Add the year's `RawSheet(year, sheet, cut, metric)` entries to `RAW_SHEETS` using
   those **actual** sheet names. Nothing is parsed for a year until this is done.
5. Add the year's published UG-graduates figure to `UG_GRADUATES_ANCHOR` in
   `clean_aishe.py` if one exists. Without it the cross-cut reconciliation still runs
   (state_level vs ug_discipline must agree) but has no external anchor.
6. If the programme list changed, re-run `build_programme_map.py`.
7. `clean_aishe.py` → `upload_to_gcs.py --raw-only` → `upload_to_gcs.py --clean-only`
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

- Don't commit anything under `raw/` or `clean/` — gitignored data (`raw/*.pdf`
  included; the PDF set alone is ~76 MB).
- **Don't delete the report files from the GCS mirror.** `gs://…/aishe/raw/` is the
  source of record, not a backup: the Excel workbooks 404 upstream and
  `fetch.py --from-gcs` is the only way to get them back.
- **Don't relax a reconciliation check to make a build pass**, and don't register a
  `(year, table)` pair that fails one. See the failure-mode table above.
- Don't write a partial fact to `higher_ed.parquet` — `load_bq.py` truncates, so a
  build missing years would delete them from BQ. That's why
  `--allow-missing-excel` writes a differently-named file.
- Don't `SUM(value)` across `cut`s in `aishe_fact_higher_ed_students` — they overlap.
- Don't sum across `social_category` (overlapping bands).
- Don't treat `metric='enrolment'` as available outside the `ug_discipline` cut.
- Don't add `raw_file` / `header_row` fields to the shared `Table` dataclass —
  those belong on `DirectoryTable` (institution directory only).
