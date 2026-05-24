# CLAUDE.md — aicte

Source-level orientation for the AICTE pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

AICTE technical-education intake data from the AICTE dashboard JSON API
(facilities.aicte-india.org). Upstream is an API, not a file: one endpoint
returns 11-year arrays (intake / enrolment / passed / placed / institution
count) per filter, plus girls/boys/faculty scalars for a selected focal year.
`fetch.py` pulls three cuts into `raw/` as panel CSVs; `clean_aicte.py` unifies
them into one wide fact. Follows the `board_results/` shape (scripted `fetch.py`
→ clean → GCS → BQ), one denormalized fact.

## Layout

```
aicte/
├── scripts/
│   ├── sources.py        # config + Table registry + RAW panel paths (single source of truth)
│   ├── fetch.py          # pull the 3 cuts from the AICTE API -> raw/panel_*.csv (regenerable)
│   ├── clean_aicte.py    # unify the 3 panels -> clean/intake.parquet (one wide fact)
│   ├── upload_to_gcs.py  # raw panels (as-is) + clean parquet -> gs://…/aicte/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> avantifellows.external_data_sources.aicte_fact_intake
├── schemas/              # aicte_fact_intake.yaml (one YAML per BQ table)
├── raw/                  # the 3 pulled panel CSVs (gitignored)
└── clean/                # unified parquet (gitignored)
```

**One denormalized fact**, `aicte_fact_intake` — the national, by-state, and
by-institution-type cuts merged on one grain
`(year, program, level, state, institution_type)`, with an `"All"` sentinel for
the dimensions a cut doesn't break out. Add/change tables in `scripts/sources.py`
(the `TABLES` registry); the loader and uploader iterate over it.

## The "All" sentinel — the one thing to get right

The three cuts are the SAME population sliced differently, so they overlap.
Each row is tagged with the explicit `cut` column — filter on it (don't rely on
the `"All"` sentinel combos):

- **`cut='national'`**: `state="All"`, `institution_type="All"` — the totals
  (88 rows = 8 program×level cuts × 11 years). `faculties` populated here only.
- **`cut='state'`**: `institution_type="All"`; `faculties` NULL (3,168 rows).
- **`cut='inst_type'`**: `state="All"`; `faculties` NULL (1,408 rows).

Total = 88 + 3,168 + 1,408 = **4,664 rows**. Validation: filtering
`state="All" AND institution_type="All"` returns exactly the 88 national rows;
Eng & Tech / UG / 2021-22 national `approved_intake` = 1,253,337. If you change
the unify logic, re-check that filter and that count — mixing cuts double-counts.

## API quirks (carried over from the original pull script)

- **One query per cut gives 11 years.** The endpoint returns
  intake/enrolment/passed/placed/institution-count as 11-element arrays
  (2012-13 … 2022-23); the `year` arg only selects which year's gender/faculty
  scalar is returned. So `fetch.py` issues one request per (cut, program, level)
  and expands the arrays to 11 rows — not one request per year.
- **Gender is focal-year-only off the national cut.** state/inst-type panels are
  pulled at focal year 2021-22 → `girls`/`boys` populated only for AY 2021-22 on
  those rows. The national panel queries each year, so it has gender per year.
- **`faculties` is national-only** — the API reports it only at the national
  level; NULL on every state/inst-type row.
- **2022-23 enrolment incomplete** in the live dashboard at pull time.
- **Throttled.** `DELAY = 0.25s` between ~440 requests; `User-Agent: Mozilla/5.0`
  header (the endpoint 403s bare clients).

## Refreshing for a new AICTE release

1. Add the new year to `YEAR_LABEL` and bump the array length in `fetch.py`;
   bump the focal year if a newer reliable gender year exists.
2. `fetch.py` → `clean_aicte.py` → `upload_to_gcs.py` → `load_bq.py`. Loads are
   `WRITE_TRUNCATE`.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't `SUM` measures across the `"All"`-sentinel rows and the broken-out rows —
  they overlap (same population, different slices). Filter to one cut first.
- Don't treat blank source cells as 0 — they're NULL (nullable Int64).
- Don't expect gender on every state/inst-type row — it's AY 2021-22 only there.
