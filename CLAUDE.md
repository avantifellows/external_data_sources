# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A one-shot ETL pipeline that turns India's official PLFS (Periodic Labour Force
Survey) unit-level data — published by MoSPI at https://microdata.gov.in across
11 releases (2018-19 → CY2025, ~10.5M person-rows, ~2.5M household-rows) — into
a small, queryable BigQuery dataset for labour-market analysis.

This is **not** a production service. It runs locally, on demand, when a new
PLFS release lands (every 6-9 months). Re-runs are idempotent. There is no
orchestrator and no daily schedule.

## Pipeline shape

```
microdata.gov.in        (gated source — manual download, see README §3)
        │
        ▼
raw/data_<release>/     (gitignored — too big + MoSPI licensing)
raw/docs_<release>/     (committed — layout XLSX + READMEs)
        │
        │  scripts/build_layouts.py   (XLSX → clean/layouts/{release}.csv)
        │  scripts/parse_data.py      (per-release source → canonical CSV)
        ▼
clean/{release_id}/*.csv (mostly gitignored — large, regenerable)
codemaps/*.csv           (committed — small lookup tables)
        │
        │  scripts/load_bq.py
        ▼
BigQuery `plfs` dataset  (6 tables — see "BQ schema" below)
        │
        ▼
analyses/*.py            (exploratory research scripts; today read CSVs, will move to BQ)
```

**Single source of truth: [`scripts/releases.py`](scripts/releases.py).** The
`RELEASES` dict holds catalog IDs, URLs, weight rules, file formats, byte
totals, and section bounds. Adding a new release means editing this dict;
nothing else.

## Commands

There is no build system — everything runs as a plain Python script.

```bash
# Local Python env (only needed for scripts/load_bq.py — others run on stdlib)
python3.13 -m venv .venv
.venv/bin/pip install pandas pyarrow google-cloud-bigquery pyyaml

# Regenerate the release registry CSV
python3 scripts/releases.py

# Build layouts from XLSX (one release or all)
python3 scripts/build_layouts.py <release_id>
python3 scripts/build_layouts.py

# Parse raw source files into clean canonical CSVs
python3 scripts/parse_data.py <release_id>
python3 scripts/parse_data.py             # all 11, ~90s

# Validate weight calibration (Σ weight_annual should be ~1.1B per release)
python3 scripts/weights.py

# Load everything to BigQuery (dataset `plfs` in your gcloud-default project)
.venv/bin/python scripts/load_bq.py                       # full load
.venv/bin/python scripts/load_bq.py --project <gcp> --dataset plfs_dev
.venv/bin/python scripts/load_bq.py --release calendar_2025  # one release only
.venv/bin/python scripts/load_bq.py --dims-only           # just dims + registry
.venv/bin/python scripts/load_bq.py --dry-run             # parquet to /tmp/plfs_bq, no upload
```

`bq mk plfs` must be run once before the first real load — the loader does
not auto-create the dataset.

## How releases differ (this matters)

PLFS releases are NOT homogeneous. The pipeline absorbs three kinds of
variation; if you change parsing or BQ-loading logic, verify behavior across
all three:

1. **Source format**: older annual releases ship fixed-width TXT (parsed via
   layout byte offsets). Mid-period releases come as Nesstar archives →
   extracted to TSV. CY2022+ ship CSVs directly. `parse_data.py` dispatches
   on `input_kind` in the release config.

2. **Column naming**: every release uses different layout labels for the same
   concept ("State/Ut Code" vs "State Code" vs `st`). All of this collapses
   to canonical snake_case mnemonics via [`scripts/canonicalize.py`](scripts/canonicalize.py),
   following CY2024's naming. Don't bypass this — write/read clean CSVs by
   canonical name.

3. **Weight rule** (this is the easy place to introduce a silent 2×–100× error):
   - `combined` — `mult / no_qtr / IF(nss = nsc, 100, 200)` — standard, most releases
   - `half_yearly` — `combined / 2` — CY2023 only (half-yearly panel design)
   - `simple` — `mult / 100` — CY2025 only (redesigned calibration)
   - `limited` — CY2021 only; schema is partial, weight is unusable, raises
     `NotImplementedError`. `load_bq.py` writes the rows with `weight_annual = NULL`.

   The canonical implementation is [`scripts/weights.py`](scripts/weights.py).
   Never reimplement weight math in an analysis or in `load_bq.py` — always go
   through `get_weight_fn(release_id)`. See [`WEIGHTS.md`](WEIGHTS.md).

## BQ schema (what `load_bq.py` produces)

Six tables in the `plfs` dataset. Authoritative column-level docs in
[`schemas/*.yaml`](schemas/).

| Table | Rows | Notes |
|---|---:|---|
| `persons` | ~10.5M | Fact. `weight_annual`, `hh_id`, `ind_pas_div` (2-digit NIC prefix), and `*_label` columns for the small enums are pre-computed/denormalized at load time. |
| `households` | ~2.5M | Fact. `weight_annual`, `hh_id`, `mpce = hce_tot/hh_size` pre-computed. |
| `releases` | 11 | Registry derived from `scripts/releases.py`. |
| `dim_nco` | ~2.7k | Full NCO 2015 occupation hierarchy in one wide table (division → subdivision → group → family → full). |
| `dim_nic` | ~1.3k | Full NIC 2008 industry hierarchy in one wide table (division → group → class → subclass). |
| `dim_geo` | ~700 | State + district. |

**Design calls worth knowing before you change them:**

- Small enums (sex, sector, religion, marital_status, education levels, activity
  status, enterprise type, social security, job contract, …) are denormalized
  as `*_label` columns on the fact tables. There is no `dim_sex` table.
  Adding a per-enum dim was explicitly rejected — it's enum-per-table snowflake
  and doesn't fit BQ.
- Hierarchical dims (NCO/NIC/geo) stay as separate tables because they have
  real structure analysts query against (e.g., NIC division `62`/`63` = IT
  services; NCO group `522` = shop salespersons).
- All codes are `STRING`, zero-padded as in the MoSPI source (`'01'`, `'62011'`).
  Storing as INT loses the padding and breaks joins.
- `hh_id` is a SHA1 prefix of `(release_id, qtr, month, visit, sec, st, dc,
  mfsu, sss, ssu)`. The single join key between `persons` and `households`;
  globally unique because `release_id` is part of the hash.

## Repo layout (only the parts that aren't obvious)

- `raw/data*/` — gitignored. Source data files. Don't check in.
- `raw/docs_<release>/` — committed. Layout XLSX + MoSPI READMEs.
- `clean/{release_id}/` — parsed canonical CSVs. Larger ones are gitignored
  (see `.gitignore` — CY2025 `cperv1.csv` alone is ~700MB).
- `clean/layouts/` — one CSV per release with the resolved layout (byte
  offsets, canonical field names). Committed.
- `clean/releases.csv` — derived registry, regenerated by `releases.py`.
- `codemaps/*.csv` — small lookup tables (state, district, NCO/NIC by level,
  the trivial enums). Committed. Read by `load_bq.py` to build dim tables and
  to denormalize labels onto facts.
- `analyses/` — exploratory Python research. Currently reads `clean/*.csv`
  directly. Will move to BQ SQL once the loader is run end-to-end.

## Analyses worth understanding before touching the schema

All under `analyses/`. They define what the data is actually used for:

- Engineering grads in regular salaried roles, longitudinal by wage tier
- Women's share of entry-level IT jobs (filters on NIC `62`/`63`)
- Education × wage gaps by age band
- Socio-economic profile of engineering grads (uses `mpce` as income proxy)
- Underemployment patterns (engineering grads ending up as NCO `522` salespersons / `411` clerks)

If you change the BQ schema, sanity-check that these analyses can still be
expressed cleanly. The schema is shaped around these queries — `ind_pas_div`,
`mpce`, `hh_id`, and the inline `tedu_label` / `pas_label` exist because of
them.

## Pitfalls

- **Don't reimplement weights anywhere.** Always `get_weight_fn(release_id)`.
- **Don't add per-enum dim tables.** Labels go inline on the facts.
- **Don't load data files into git.** `.gitignore` is comprehensive; check
  before adding to `raw/data*/` or `clean/{release_id}/`.
- **Don't assume `qtr` or `month` is populated** — exactly one is, per
  release. CY2025 has `month`; everything else has `qtr`.
- **CY2021 is the limited release.** Its schema lacks `tedu_lvl`, `pas`,
  `ind_pas`, `ern_reg`. Demographic-only queries work; engineering-jobs
  analyses skip it. `weight_annual` is `NULL` for these rows in BQ.
- **District codes are not globally unique** — they're scoped per state.
  Always join on `(state_code, district_code)`.
