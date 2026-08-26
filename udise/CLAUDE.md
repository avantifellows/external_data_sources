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

1. **Report 4000** — a dashboard cross-tab, ingested as `udise_fact_enrolment`
   (42,270 rows, state-level aggregate). Everything above this section refers to it.
2. **DSP microdata** — Data Sharing Portal, **one row per school**, five editions
   (2020-21, 2022-23, 2023-24, 2024-25, 2025-26; 2021-22 is not held). Raw zips in
   `raw/dsp/` (gitignored, ~1.7 GB). Ingested as `udise_dim_school_dsp` and
   `udise_fact_enrolment_dsp` by `scripts/dsp_stage.py` → `scripts/dsp_build_bq.py`.

Keep the two apart in table names and schemas. A DSP table is `*_dsp`; never merge
one into the Report 4000 fact, and never union them — they are different grains.

## Working on DSP

Read [`schemas/README.md`](schemas/README.md) first — it carries the re-entry
status line and the five gotchas. In short:

- **`9` = Not Applicable** on nearly every coded column. **Yes=1, No=2** — not 1/0.
- **`_b` is "Boys + Transgenders"** through 2024-25; 2025-26 is the first edition
  with a separate `_t` column. The `gender` value in the fact says which
  (`boys_incl_transgender` vs `boys`) rather than relying on a footnote.
- **Only `item_group=1` partitions the students.** Religion, BPL, EWS, disability
  and repeaters all overlap it. Summing across item groups double-counts.
- **`managment` is misspelt at source.** Only `psuedocode` → `pseudocode` is fixed
  at the staging boundary; every other source spelling is kept raw in staging and
  renamed in `dsp_build_bq.py`.
- **`pseudocode` is pseudonymised** — joins the DSP tables to each other within a
  year and reaches nothing else. Cross-year stability is unverified.
- **Five editions, four layouts.** `dsp_stage.py` takes column names from each
  CSV's own header and records them in the committed `schemas/dsp_layouts.json`, so
  a silent upstream schema change shows up as a git diff. Do not hand-maintain a
  per-year column list.

### Don'ts specific to DSP

- **Don't read a DSP CSV with pandas.** The 2025-26 enrolment file is 1.17 GB
  uncompressed. Everything streams zip → gzip → GCS → BigQuery, and every reshape
  happens in SQL.
- **Don't publish the 2020-21 profile_2 columns at source positions 20-45.** The
  CSV header and the codebook disagree about what those 26 columns mean. See the
  `not_published` block in `schemas/udise_dim_school_dsp.yaml`.
- **Don't invent an age mapping.** From 2022-23 the age cut is `item_group=8` with
  an `item_id` the codebook describes only as "Age id (2 to 22)" — no id-to-age
  table is published. 2020-21's readable age labels are carried as-is; the two are
  not comparable, and the schema says so.
- **Don't leave the staging dataset behind.** `udise_dsp_staging` is transient
  (14-day table expiry). Drop it with `dsp_build_bq.py --drop-staging` once the
  finished tables validate.
