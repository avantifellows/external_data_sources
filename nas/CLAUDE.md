# CLAUDE.md — nas

Source-level orientation. Read the top-level `../CLAUDE.md` for cross-cutting
conventions first.

## What this source is

NAS 2021 (National Achievement Survey, NCERT) student-achievement data. Upstream
is the **community CSV mirror** [`gsidhu/NAS-2021-data`](https://github.com/gsidhu/NAS-2021-data),
a tidy CSV form of NCERT's published NAS 2021 results. The pipeline does one
real transform — student-weighted aggregation of state-level performance up to
national — then parquet → GCS → BQ.

## Layout

```
nas/
├── scripts/
│   ├── sources.py        # config + Table registry + SOURCE_REPO / SOURCE_CSV_DIR
│   ├── fetch.py          # git clone --depth 1 gsidhu/NAS-2021-data → raw/
│   ├── clean_nas.py      # state rows + 'All India' weighted rollup → clean/state_proficiency.parquet
│   ├── upload_to_gcs.py  # raw CSVs + clean parquet -> gs://…/nas/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> avantifellows.external_data_sources.nas_fact_state_proficiency
├── schemas/              # nas_fact_state_proficiency.yaml
├── raw/                  # cloned community CSV mirror (gitignored)
└── clean/                # aggregated parquet (gitignored)
```

`fetch.py` shallow-clones the upstream repo into `raw/NAS-2021-data`, so the
CSVs read by `clean_nas.py` live at `raw/NAS-2021-data/csv_data/`.

## The one thing to get right: the weighting

NAS publishes percent-correct and proficiency bands **per state only**. National
figures are derived in `clean_nas.py` as a student-weighted mean across states:

    weight = state total_student × (share of that bucket / 100)

where the share columns (`govt_school`, `govt_aided_school`, `private_school`,
`central_govt_school`, `rural_location`, `urban_location`) come from
`NAS_participation_state.csv`. Don't average state values unweighted — small and
large states would count equally.

The participation file can have multiple rows per (state, grade); `load_part()`
keeps the latest by `id`. CSVs are **semicolon-separated** (`sep=";"`).

## Proficiency is two tails, not four bands

NAS reports only "% Proficient and Advance" (top) and "% Basic and Below Basic"
(bottom). There is no four-band split in this data set. The fact carries
`pct_correct_mean` plus those two tails — don't expect them to sum to 100 in any
given row (they're independent shares of the distribution).

## Validation

`clean_nas.py` writes **3,510 rows** = 90 per state (4 grades × subjects ×
dimensions × buckets) × 39 (38 states/UTs + the `All India` rollup). The
`All India` numbers are the student-weighted national figures. E.g. All India /
grade 5 / math / location / Urban → pct_correct_mean 42.89. If the count isn't
3,510 or `All India` values drift, the source layout or weighting changed.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't average state figures unweighted — use the student-count weights.
- Don't treat the two proficiency tails as a partition that sums to 100.
