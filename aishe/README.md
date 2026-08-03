# aishe

AISHE (All India Survey on Higher Education, MoE) student data → BigQuery.

**Enrolment + graduates (out-turn)** from the AISHE Final Reports, as a **single
denormalized fact** sliceable by state×level, programme×social-category, and UG
discipline. Covers **2015-16 → 2021-22**. The reports need real parsing, so this
is a heavier pipeline than `nirf/`, but it still stages parsed parquet through GCS.

**Source:** AISHE Final Reports from [aishe.gov.in](https://aishe.gov.in/)
(Ministry of Education), one per academic year, in **two editions that are not
interchangeable**:

| Edition | Years | Parser |
|---|---|---|
| Excel `.xlsx` | 2019-20 → 2021-22 | `clean_aishe.py` (openpyxl) |
| PDF | 2012-13 → 2023-24 | `parse_report_pdf.py` (pdfplumber) |

**Everything before 2019-20 exists only as a PDF** — there is no Excel edition to
parse, which is why there are two parsers. Neither is redistributed in git; see
*Raw data* below.

## Pipeline at a glance

```
AISHE Final Reports        PDFs from the MoE CDN  +  Excel from the GCS mirror
       │ scripts/fetch.py              (--from-gcs for the workbooks)
       ▼
raw/aishe_<year>_final_report.pdf            (local; gitignored)
raw/aishe_<year>_final_report.xlsx           (local; gitignored)
       │ scripts/build_programme_map.py  → codemaps/programme_to_discipline.csv  (committed)
       │ scripts/clean_aishe.py   ── calls ──▶ scripts/parse_report_pdf.py
       ▼
clean/higher_ed.parquet                      (local; gitignored)
       │ scripts/upload_to_gcs.py
       ▼
gs://…/aishe/raw/aishe_<year>_final_report.{xlsx,pdf}   ← the durable mirror
gs://…/aishe/raw/<year>/<sheet|table>.parquet           (traceability)
gs://…/aishe/clean/higher_ed.parquet                    (loaded to BQ)
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.aishe_fact_higher_ed_students   (asia-south1)
```

`clean_aishe.py` is the single entry point for the fact — it parses the workbooks
itself and calls `parse_report_pdf.py` for the PDF-only years, so one command
produces the whole table.

The single source of truth for filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Table produced

**`aishe_fact_higher_ed_students`** — one wide fact (10,956 rows). Grain:
`(cut, aishe_year, metric, level, state, discipline, programme, social_category, gender)`
→ `value`. Each row carries a `cut` (which published cross-tab it came from) and a
`metric` (`enrolment` = students currently studying, or `graduates` = out-turn /
qualifiers that year). Dimensions a cut doesn't break out carry the sentinel `"All"`:

| `cut` | Source | Metric(s) | Set dimensions | Years | Rows |
|---|---|---|---|---|---:|
| `state_level`      | Table 33     | graduates             | level, state                       | 2015-16, 2016-17, 2017-18, 2018-19, 2021-22 | 4,320 |
| `programme_social` | Table 34a    | graduates             | programme, social_category         | 2021-22 | 5,448 |
| `ug_discipline`    | Tables 12+35 | enrolment + graduates | level=`Under Graduate`, discipline | 2015-16, 2016-17, 2018-19, 2019-20, 2020-21, 2021-22 | 1,188 |

**The cuts overlap (different views of the same students) — always filter to one
`cut`, and never `SUM(value)` across cuts.**

**Coverage is ragged — `GROUP BY aishe_year` before reading any trend.**
`state_level` is the only cut with real historical depth (5 years) and is the one
to use for a time series. `programme_social` is **2021-22 only**: the pre-2019 PDFs
print a Table 34 with no social-category breakdown at all. A series that appears
to collapse is far more likely to be missing coverage than a real change.

Schema: [`schemas/aishe_fact_higher_ed_students.yaml`](schemas/aishe_fact_higher_ed_students.yaml).

### Validation

Every year is reconciled against a figure the report itself publishes, and the
build **fails rather than emit an unreconciled table**:

- **Table 33** — the 8 levels must sum to the published `Grand Total` column.
- **Tables 12 / 35** — the disciplines must sum to the published Grand Total row.
- **Cross-cut** — UG graduates via `state_level` must equal UG graduates via
  `ug_discipline` for any year carrying both. Holds exactly for 2015-16
  (6,331,999), 2018-19 (6,474,715) and 2021-22 (7,754,223); 2021-22 also matches
  AISHE's published 7,754,223.

These checks are what keeps a PDF layout change from landing as plausible-looking
wrong numbers — see `CLAUDE.md` for the failure modes they caught.

### STEM bucketing

[`codemaps/discipline_to_stem.csv`](codemaps/discipline_to_stem.csv) maps all 41
`discipline` values to `STEM` / `non-STEM`, for the low-income-representation and
discipline-mix analyses. STEM is the **broad** definition: engineering, science,
IT, **medical and paramedical**, agriculture/veterinary/fisheries, and
design/fashion/footwear. The `basis` column marks whether each row was specified
or inferred — grep `inferred` before relying on a boundary case.

## Analysis (not in this repo)

Exploratory analysis — the discipline × social-category rollup, the 2025-26
projection, and the discipline → wage-bucket grouping for the cross-source RoI /
wage-curve work — runs locally; the analysis *intents* are documented in
`data-assistant/docs/analyses/external_data_sources.yaml`. Only the
programme→discipline **codemap stays a committed CSV**
(`codemaps/programme_to_discipline.csv`), the audit interface those rollups read.

## GCS layout

```
gs://avantifellows-external-data/
  aishe/raw/aishe_<year>_final_report.xlsx   ← THE DURABLE MIRROR of the source file
  aishe/raw/aishe_<year>_final_report.pdf    ← ditto, for the PDF edition
  aishe/raw/<year>/<sheet>.parquet           ← dump of each Excel sheet (traceability)
  aishe/raw/<year>/t<NN>.parquet             ← dump of each parsed PDF table (traceability)
  aishe/clean/higher_ed.parquet              ← the fact; load_bq.py loads this
```

**The bucket, not the publisher, is the source of record.** Publisher URLs for
Indian government data rot — every `he.nic.in` Excel URL this pipeline once used
now 404s. `fetch.py --from-gcs` restores `raw/` from the mirror above, and for the
`.xlsx` workbooks it is the **only** way to get them.

## Raw data

Nothing under `raw/` is in git (`raw/*.xlsx`, `raw/*.pdf` — ~80 MB across the
set). Everything is re-obtainable with `scripts/fetch.py`:

| Year | PDF | Excel | Parsed into the fact |
|---|---|---|---|
| 2012-13 → 2014-15 | ✓ CDN | — | no — registered but not parsed |
| 2015-16 | ✓ CDN | — | T12, T33, T35 |
| 2016-17 | ✓ CDN | — | T12, T33 |
| 2017-18 | ✓ CDN | — | T33 |
| 2018-19 | ✓ CDN | — | T12, T33, T35 |
| 2019-20 → 2021-22 | ✓ CDN | **GCS mirror only** | Excel: T12, T35 (+T33/T34a for 2021-22) |
| 2022-23, 2023-24 | ✓ CDN | not obtainable | no — see below |

```bash
.venv/bin/python scripts/fetch.py              # PDFs from the MoE CDN
.venv/bin/python scripts/fetch.py --from-gcs   # workbooks + directory exports
.venv/bin/python scripts/fetch.py --timeseries # the GER / GPI series PDFs
```

**The Excel workbooks cannot be re-downloaded from AISHE.** All five
`he.nic.in/aishereport/assets/excel/...` URLs return 404 (checked 2026-08-03), and
the "(Excel)" links on aishe.gov.in point at a JavaScript viewer
(`he.nic.in/aishereport/#/report/<year>`) that exposes no static file. So
`sources.REPORT_URLS` is deliberately **empty** and `--from-gcs` is the only
route. If anyone finds the real endpoint, filling that dict in is the only change
needed. **Corollary: never delete the workbooks from the GCS mirror.**

### Not yet ingested

- **2022-23 / 2023-24.** Both shipped in the 8 Jul 2026 release. Their PDFs fetch
  fine; the Excel does not exist for us. Ingesting them from PDF means adding
  their `(year, table)` pairs to `sources.PDF_TABLES` after checking the captions
  — AISHE renumbers tables between editions.
- **2012-13 → 2014-15.** PDFs are registered in `PDF_REPORT_URLS` and fetch, but
  no `PDF_TABLES` entries exist yet, so they contribute nothing.
- **Seven `(year, table)` pairs that fail their reconciliation check** — listed
  with the exact discrepancy in the comment above `PDF_TABLES` in
  [`scripts/sources.py`](scripts/sources.py). They are commented out rather than
  loaded wrong.

## First-time setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for upload + load
```

## Running

The whole flow, from an empty checkout to a loaded table:

```bash
# 0. setup
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
gcloud auth application-default login

# 1. get the raw reports (both editions)
.venv/bin/python scripts/fetch.py              # PDFs from the MoE CDN
.venv/bin/python scripts/fetch.py --from-gcs   # Excel workbooks + directory exports

# 2. build the fact — parses BOTH editions into clean/higher_ed.parquet
.venv/bin/python scripts/clean_aishe.py

# 3. stage to GCS (source mirror + traceability dumps + the clean fact)
.venv/bin/python scripts/upload_to_gcs.py --dry-run
.venv/bin/python scripts/upload_to_gcs.py
#   …or one side only: --sources-only / --raw-only / --clean-only

# 4. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run
.venv/bin/python scripts/load_bq.py --table aishe_fact_higher_ed_students
```

Expected from step 2: **10,956 rows**, and three `OK` reconciliation lines
(2015-16, 2018-19, 2021-22). Any other output means a parse moved — read the error
rather than loading the result.

Occasionally:

```bash
# rebuild the programme->discipline codemap from the 2021-22 workbook
.venv/bin/python scripts/build_programme_map.py

# diagnose one edition's layout before registering a new year
.venv/bin/python scripts/inspect_workbook.py --year 2022-23 --all-sheets
.venv/bin/python scripts/parse_report_pdf.py --year 2018-19 --debug
```

`load_bq.py` uses `WRITE_TRUNCATE`, so **the parquet is the whole table** — a
build that covers only some years would delete the rest. `clean_aishe.py`
therefore refuses to write `higher_ed.parquet` when a registered Excel year is
missing; `--allow-missing-excel` writes `higher_ed.partial.parquet` instead, a
name neither `upload_to_gcs.py` nor `load_bq.py` will touch. Only the clean fact
is loaded to BQ — the raw parquet on GCS is for traceability.

## Caveats

- **`enrolment` exists only on the `ug_discipline` cut** (UG, by subject
  discipline, Table 12). The state and programme cuts are graduates only.
- **The cuts overlap** — each is a different view of the same students. Filter to
  one `cut`; never `SUM(value)` across cuts.
- **Social categories overlap** (All Categories ⊇ SC/ST/OBC/PwD/Muslim/EWS) —
  never sum across `social_category` either.
- **discipline (subject) ≠ programme (degree).** Table 34a is degree-based
  (B.A., MBBS, …); Tables 12/35 are subject-based (Arts, Engineering & Tech, …).
  They use incompatible classifications and can't be cross-walked exactly — use
  the `ug_discipline` cut for subject-based numbers.
- **Coverage differs by year and cut** — see the table above. Only `state_level`
  spans 2015-16 → 2021-22, and it skips 2019-20 / 2020-21 because `RAW_SHEETS`
  registers Table 33 for 2021-22 only.
- **Discipline labels are whitespace-normalised.** AISHE spells the same
  discipline with a variable number of internal spaces between editions
  (`Footwear  Design` in the 2019-22 workbooks vs `Footwear Design` in the PDFs),
  which used to split it into two values. `clean_aishe.py` collapses internal
  runs of whitespace. Note `codemaps/programme_to_discipline.csv` still carries
  the two-space spelling.
- **Roll-up rows are excluded from the fact.** Until 2026-08 the Excel reader
  emitted each sheet's `Grand Total` row as a discipline named `Grand`; because
  that row equals the sum of the disciplines, `SUM(value)` for **2019-20 and
  2020-21 returned exactly double** the true UG figure. Both years are now correct
  (29,545,053 and 31,046,985 UG enrolment). Any cached number for those two years
  predating the fix should be re-checked.
