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
