# CLAUDE.md — udise

Source-level orientation. Read the top-level `../CLAUDE.md` for cross-cutting
conventions first.

## What this source is

UDISE+ (Unified District Information System for Education) school-enrolment data
from the MoE dashboard. Upstream is a single wide cross-tab xlsx (Report 4000,
one academic year). Light-ish: one reshape step (wide → long), then parquet →
GCS → BQ.

## Layout

```
udise/
├── scripts/
│   ├── sources.py        # config + Table registry + SOURCE_XLSX / ACADEMIC_YEAR
│   ├── clean_udise.py    # reshape the wide cross-tab → clean/enrolment.parquet (one fact)
│   ├── upload_to_gcs.py  # raw xlsx + clean parquet -> gs://…/udise/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> avantifellows.external_data_sources.udise_fact_enrolment
├── schemas/              # udise_fact_enrolment.yaml
├── raw/                  # source xlsx (gitignored)
└── clean/                # parsed parquet (gitignored)
```

No `fetch.py`: the UDISE+ dashboard has no static download URL (the report is
generated on demand), so the raw xlsx on GCS is the regenerable source of record.

## The one thing to get right: subtotal rows

The dashboard export is hierarchical — leaf detail rows are interleaved with
subtotals at several levels:
- `urban_rural = "Total"` → Rural + Urban combined
- blank `urban_rural` → state-level subtotals
- blank `Location` → the all-India grand total

`clean_udise.py` keeps **only leaf rows** (`urban_rural ∈ {Rural, Urban}` with
state + management + category present). Validation: `SUM(enrolment)` =
246,932,680 (the all-India total). If you change the parser, re-check that sum —
keeping subtotal rows silently 2-3×'s the count.

The header is multi-row: class labels (merged across Girls/Boys pairs) sit one
row above the `Location / … / Girls / Boys / Overall` sub-header; data follows.
`clean_udise.py` finds the sub-header by locating the cell `"Location"`.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't keep the subtotal/"Total" rows in the fact — they double-count.
- Don't sum across `urban_rural` expecting a "Total" row — there isn't one (it's
  derived); just sum Rural + Urban.

## Two products, one folder — read this first

`udise/` holds two unrelated UDISE+ releases:

1. **Report 4000** — a dashboard cross-tab, already ingested as
   `udise_fact_enrolment` (42,270 rows, state-level aggregate). Everything else in
   this file refers to it.
2. **DSP microdata** — Data Sharing Portal, **one row per school**, 2020-21 and
   2024-25. Raw zips are in `raw/dsp/` (gitignored, ~754 MB) and registered in
   `sources.py` (`DSP_YEARS`, `DSP_GROUPS`, `dsp_zip()`). **Nothing is built yet** —
   read [`docs/DSP_INGEST_PLAN.md`](docs/DSP_INGEST_PLAN.md) before starting, it has
   the codebook gotchas that will otherwise bite:
   - `Yes=1, No=2` — not 1/0.
   - `_b` columns are **"Boys + Transgenders"**, so `_b`/`_g` is not a clean split.
   - Most attributes are numeric DCF codes needing codemaps;
     `codemaps/dsp_item_group.csv` decodes the enrolment breakdown (social
     category, religion, BPL, EWS, 20 disability types, repeaters).
   - `managment` is misspelt in the source. Keep it raw, rename on the way out.
   - One enrolment CSV is 562 MB uncompressed — stream it or push it to BQ.
   - The school key `pseudocode` is pseudonymised: it joins the DSP groups to each
     other but **cannot be linked to Avanti's school lists**.

Keep the two apart in table names and schemas. A DSP table should be
`udise_dim_school_dsp` / `udise_fact_*_dsp`, never merged into the Report 4000 fact.
