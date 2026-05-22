# PLFS — Cleaned Microdata + Code Maps

This folder (`plfs/` within the
[`external_data_sources`](../README.md) repo) converts the official PLFS
(Periodic Labour Force Survey) unit-level data from MoSPI/NSO into clean
per-release CSVs with a canonical column schema, code-map lookups, and
per-release calibrated weights. **11 releases covered, 2018-19 → CY2025** —
a continuous year-by-year picture of India's labour market for the
post-COVID/post-AI period.

The final step is loading into BigQuery via [`scripts/load_bq.py`](scripts/load_bq.py)
— one script, six tables, idempotent.

---

## 1. What is PLFS

**PLFS** = **Periodic Labour Force Survey**, run by MoSPI / NSO (Govt of
India). It's the official source for India's employment and unemployment
statistics — where the LFPR / WPR / unemployment rate numbers come from. A
household sample survey covering ~100k households and ~400k–1.1M individuals
per release.

Two release cadences:

- **Annual** (Jul-Jun) — the canonical employment-indicators report. 4 data
  files: `HHV1`/`HHRV` (household first-visit + revisits), `PERV1`/`PERRV`
  (person first-visit + revisits).
- **Calendar Year** (Jan-Dec) — started CY2021. Faster turnaround, first-visit
  only. 2 data files: `CHHV1` + `CPERV1`.

Each survey collects, per person:

- Demographics (age, sex, marital status, relation to head)
- Education (general level, technical level — engineering / medical / other)
- Usual principal activity status (job, industry NIC code, occupation NCO code,
  enterprise type, social security, wages)
- Usual subsidiary activity status (same fields for any second job)
- Current weekly activity status (last 7 days, day-by-day)
- Monthly earnings (regular salaried + self-employment)

Per household:

- Religion, social group (SC/ST/OBC/Other), household type
- Monthly consumer expenditure (the standard income proxy in Indian household
  surveys — PLFS doesn't ask income directly)

PLFS data is published with per-record **sampling weights** so survey counts
scale up to India-wide population estimates (~1.4B).

## 2. What this gets used for

The kinds of questions this dataset answers, drawn from analyses already in
[`analyses/`](analyses/):

- **Engineering jobs longitudinal** — engineering grads age 20-24 in regular
  salaried jobs paying ≥ ₹25k/month, year-by-year from 2018-19 to CY2025,
  split by wage tier (₹25-30k / ₹30-50k / >₹50k). Visible result: a ~25% drop
  in CY2024 → CY2025, the IT-services contraction.
- **Women in IT longitudinal** — same question restricted to NIC 62-63
  (computer programming / information services). How has women's share of
  entry-level IT jobs evolved 2022 → 2025?
- **Education–wages gap** — for engineering grads vs general grads vs school-
  only, what's the median wage at age 25-29 and 35-39?
- **Socio-economic profile of engineering grads** — what % of India's ~9M
  engineering degree holders come from low-income households (HCE proxy)?
  What % are first-generation learners?
- **Underemployment patterns** — ~3-4% of working engineering grads are
  classified as shop salespersons (NCO 522) or office clerks (NCO 411).

## 3. Sources

Single source of truth: **https://microdata.gov.in** (the National Data
Archive run by MoSPI). Each release has a catalog ID:

| Release | Catalog | URL |
|---|---:|---|
| Annual Jul18-Jun19 | 216 | https://microdata.gov.in/nada43/index.php/catalog/216 |
| Annual Jul19-Jun20 | 217 | https://microdata.gov.in/nada43/index.php/catalog/217 |
| Annual Jul20-Jun21 | 206 | https://microdata.gov.in/nada43/index.php/catalog/206 |
| Calendar Year 2021 | 209 | https://microdata.gov.in/nada43/index.php/catalog/209 |
| Annual Jul21-Jun22 | 214 | https://microdata.gov.in/nada43/index.php/catalog/214 |
| Calendar Year 2022 | 211 | https://microdata.gov.in/nada43/index.php/catalog/211 |
| Annual Jul22-Jun23 | 210 | https://microdata.gov.in/nada43/index.php/catalog/210 |
| Calendar Year 2023 | 208 | https://microdata.gov.in/nada43/index.php/catalog/208 |
| Annual Jul23-Jun24 | 213 | https://microdata.gov.in/nada43/index.php/catalog/213 |
| Calendar Year 2024 | 254 | https://microdata.gov.in/nada43/index.php/catalog/254 |
| Calendar Year 2025 | 284 | https://microdata.gov.in/nada43/index.php/catalog/284 |

Plus two non-PLFS reference datasets:

- **NIC 2008** (National Industrial Classification) — from MoSPI. ~2k codes
  organised into divisions / groups / classes / subclasses.
- **NCO 2015** (National Classification of Occupations) — from DGE&T,
  Ministry of Labour. ~2.7k 8-digit codes mapping back to NCO 2004.

### Extraction story

PLFS unit-level data is mostly distributed as `.Nesstar` archives — a
proprietary NSDstat format that requires a Windows GUI app (Nesstar Explorer)
to extract. Catalogs from 2022+ also offer pre-converted CSV downloads. For
older releases we used a one-time GCE Windows VM workflow:

1. Spin up Windows Server 2022 in `asia-south1` (`avantifellows` project)
2. RDP in, install Nesstar Explorer
3. Manually export each `.Nesstar` archive to TSV
4. Push back to a GCS bucket, pull to local
5. Tear down VM + bucket

Total one-time cost: ~₹100. Extracted TSVs and original catalog URLs are in
[`clean/releases.csv`](clean/releases.csv); no need to repeat unless data corrupts.

## 4. Data flow

```
        ┌─────────────────┐
        │ microdata.gov.in│  (PLFS source — 11 catalog IDs)
        └────────┬────────┘
                 │ manual download (gated by free login)
                 ▼
        ┌─────────────────┐
        │   raw/           │  XLSX layouts, README PDFs, source data
        │     docs_*/      │  (committed: docs only; data files gitignored)
        │     data*/       │
        │     external/    │  NIC 2008 + NCO 2015 reference PDFs
        └────────┬────────┘
                 │ scripts/build_layouts.py    (XLSX → consolidated layout CSV)
                 │ scripts/parse_data.py       (per-release source → canonical CSV)
                 │ scripts/build_codemaps.py   (one-off: reference code lists)
                 │ scripts/parse_nco_2015.py   (one-off: NCO PDF → CSVs)
                 ▼
        ┌─────────────────┐
        │   clean/         │  Per-release CSVs with canonical column names
        │     releases.csv │  Release registry (catalog IDs, URLs, weight rules)
        │     layouts/     │  11 layout CSVs (one per release)
        │     {release}/   │  {hhv1,hhrv,perv1,perrv}.csv  or  {chhv1,cperv1}.csv
        │   codemaps/      │  Code-map dimension tables
        └────────┬────────┘
                 │ scripts/weights.py — per-release calibrated weights
                 │ scripts/load_bq.py  — one-shot ETL into BigQuery
                 ▼
        ┌─────────────────┐
        │   BigQuery       │  6 tables in `avantifellows.external_data_sources` (plfs_* tables):
        │                  │    persons     (~10.5M rows, fact)
        │                  │    households  (~2.5M rows, fact)
        │                  │    releases    (11 rows, registry)
        │                  │    dim_nco     (~2.7k, full occupation hierarchy)
        │                  │    dim_nic     (~1.3k, full industry hierarchy)
        │                  │    dim_geo     (~700, state + district)
        └─────────────────┘
```

Every step is reproducible from the source URLs in
[`clean/releases.csv`](clean/releases.csv). If a release gets republished or
we add a new year, the only change is in [`scripts/releases.py`](scripts/releases.py)
(single source of truth for release config). The rest re-runs.

## 5. Repository layout

```
PLFS/
├── README.md                     ← this file
├── WEIGHTS.md                    ← per-release weight rules
│
├── raw/                          ← source files (mostly gitignored; data is gated)
│   ├── docs_*/                   ← layout XLSX + README PDF per release
│   ├── data_*/                   ← unit-level data per release (gitignored)
│   └── external/                 ← NIC 2008, NCO 2015 reference PDFs
│
├── clean/
│   ├── releases.csv              ← REGISTRY: catalog IDs, URLs, weight rules
│   ├── layouts/                  ← ONE layout CSV per release (consolidated)
│   │   ├── annual_2018_19.csv    ← all files of one release in one CSV
│   │   ├── ...
│   │   └── calendar_2025.csv
│   └── {release_id}/             ← parsed data per release
│       ├── hhv1.csv  hhrv.csv  perv1.csv  perrv.csv     (annual releases)
│       └── chhv1.csv cperv1.csv                          (calendar releases)
│
├── codemaps/                     ← (code, description) lookup CSVs
│
├── scripts/                      ← ETL infrastructure
│   ├── releases.py               ← single source of truth: release configs + URLs
│   ├── weights.py                ← per-release calibrated weight functions + self-test
│   ├── canonicalize.py           ← layout-name → canonical-mnemonic mapping
│   ├── build_layouts.py          ← XLSX → clean/layouts/{release_id}.csv
│   ├── parse_data.py             ← unified parser: handles txt / csv / tsv input
│   ├── build_codemaps.py         ← writes codemaps/*.csv from instruction manual
│   ├── parse_nco_2015.py         ← writes codemaps/nco_*.csv from NCO PDF
│   └── load_bq.py                ← one-shot ETL into BigQuery (6 tables)
│
├── schemas/                      ← BigQuery column-level docs (one YAML per table)
│
└── analyses/                     ← exploratory research scripts (read clean/* CSVs)
```

## 6. Quickstart

```bash
# Build the release registry (clean/releases.csv)
python3 scripts/releases.py

# Build all 11 release layouts from their XLSX files
python3 scripts/build_layouts.py

# Build code-map CSVs (one-time)
python3 scripts/build_codemaps.py
python3 scripts/parse_nco_2015.py

# Parse data for one release
python3 scripts/parse_data.py calendar_2025

# Parse all 11 releases (~90 seconds total)
python3 scripts/parse_data.py

# Load everything into BigQuery (idempotent; ~5-10 min for full dataset)
python3 scripts/load_bq.py                       # to dataset `plfs`
python3 scripts/load_bq.py --dataset plfs_dev    # to a dev dataset
python3 scripts/load_bq.py --release calendar_2025  # one release only
python3 scripts/load_bq.py --dims-only           # just dims + registry
python3 scripts/load_bq.py --dry-run             # build parquet locally, no upload
```

## 7. How to add a new release

1. Add an entry to `RELEASES` in [`scripts/releases.py`](scripts/releases.py) —
   fill in catalog URL, format (`annual`/`calendar`), period, weight rule,
   paths, byte totals, section row bounds, file names.
2. Place the source XLSX in `raw/docs_<release_id>/` and the data files in
   `raw/data_<release_id>/` (or wherever the config points).
3. `python3 scripts/build_layouts.py <release_id>` — verify byte totals match.
4. `python3 scripts/parse_data.py <release_id>` — verify row counts match
   the release's README.
5. `python3 scripts/releases.py` — regenerate the registry CSV.
6. `python3 scripts/weights.py` — confirm calibration self-test passes
   (weighted total population should be ~1.1-1.2B for any new release).

## 8. Data fetch (gated by microdata.gov.in)

Most PLFS data is behind a free MoSPI login. Catalog URLs are in
[`clean/releases.csv`](clean/releases.csv). Three usable paths:

- **Browser**: each catalog page has a "Get Microdata" tab → log in → download
- **`mospi-unitdata` Python client**: authenticated API. Newer releases give
  CSVs directly; older releases give Nesstar archives.
- **Nesstar archives** (older releases): extract via a cloud Windows VM or
  Wine on macOS. See §3 above.

## 9. Code maps

Every coded column in a clean data table joins to a code map in
[`codemaps/`](codemaps/) on the `code` column. Codes are stored as
zero-padded text.

Notable maps:

- **Geography**: `state.csv` (36 states/UTs), `district.csv` (~700 districts)
- **Demographics**: `religion.csv`, `social_group.csv`, `general_education.csv`, `technical_education.csv`
- **Activity**: `activity_status.csv` (UPS / USS / CWS shared codes)
- **Employment**: `enterprise_type.csv`, `job_contract.csv`, `social_security.csv`
- **Industry (NIC 2008)**: `nic_division.csv`, `nic_group.csv`, `nic_class.csv`, `nic_subclass.csv`
- **Occupation (NCO 2015)**: `nco_division.csv`, `nco_subdivision.csv`, `nco_group.csv`, `nco_family.csv`, `nco_full.csv`

## 10. Weights

See [WEIGHTS.md](WEIGHTS.md). Four rules across releases:

- **`combined`** — `mult / no_qtr / IF(nss = nsc, 100, 200)`. Standard rule.
  Used by all annual releases + CY2022 + CY2024.
- **`half_yearly`** — same as combined but with an extra `/2`. CY2023 only
  (half-yearly panel design).
- **`simple`** — `mult / 100`. CY2025 only (redesigned weight scheme).
- **`limited`** — CY2021 omits `tedu_lvl`/`pas`/`ind_pas`/`ern_reg` from the
  schedule. Usable only for demographic and CWS analyses.

The canonical implementation lives in [`scripts/weights.py`](scripts/weights.py):

```python
from weights import get_weight_fn
weight_fn = get_weight_fn('calendar_2023')
total = sum(weight_fn(row) for row in csv.DictReader(f))
```

Per-release `weight_rule` is recorded in [`clean/releases.csv`](clean/releases.csv).

## 11. BigQuery

Six tables in `avantifellows.external_data_sources` (plfs_*-prefixed), populated by
[`scripts/load_bq.py`](scripts/load_bq.py):

| Table | Rows | Notes |
|---|---:|---|
| `plfs_fact_persons` | ~10.5M | All releases unioned. `weight_annual` pre-computed. `hh_id` joins to households. `ind_pas_div` (2-digit NIC prefix) and `*_label` columns for the common enums are denormalized inline. |
| `plfs_fact_households` | ~2.5M | `weight_annual`, `hh_id`, and `mpce = hce_tot/hh_size` pre-computed. |
| `plfs_releases` | 11 | Registry: catalog IDs, URLs, weight rules, period bounds. |
| `plfs_dim_nco` | ~2.7k | Full NCO 2015 occupation hierarchy in one wide table (division → subdivision → group → family → full). |
| `plfs_dim_nic` | ~1.3k | Full NIC 2008 industry hierarchy in one wide table (division → group → class → subclass). |
| `plfs_dim_geo` | ~700 | State + district. (State name is also inline on the facts.) |

Labels for the small enums (sex, sector, religion, marital_status, education
levels, activity_status, enterprise_type, social_security, job_contract, etc.)
are denormalized as `*_label` columns on the fact tables rather than separate
dim tables. Pattern matches `etl-next/production/`: a small number of
well-shaped fact/dim tables, not a per-enum snowflake.

Typical query:

```sql
SELECT release_year,
       SUM(weight_annual) / 1e6 AS engg_grads_millions,
       APPROX_QUANTILES(ern_reg, 100)[OFFSET(50)] AS median_wage
FROM plfs.persons
WHERE tedu_lvl IN ('03','13')   -- engineering degree
  AND age BETWEEN 20 AND 24
  AND pas = '31'                -- regular salaried
GROUP BY release_year ORDER BY release_year;
```

The load script is idempotent (`WRITE_TRUNCATE`), reproducible, and runs in
~5-10 minutes for the full 10.5M-row dataset. Re-run whenever a new PLFS
release lands.

## 12. GCS staging (parquet — BigQuery later, post-approval)

To fit the `external_data_sources` model (raw in GCS → joined parquets → BQ once
reviewed), [`scripts/upload_to_gcs.py`](scripts/upload_to_gcs.py) stages two
things under `gs://avantifellows-external-data/plfs/`:

- **`raw/`** — the per-release unit-level microdata (rsync of the local `raw/`
  tree). PLFS raw is gated behind microdata.gov.in, so there is **no `fetch.py`**;
  this GCS copy is the regenerable source of record.
- **`clean/`** — the six joined tables as parquet, built by `load_bq.py --dry-run`
  (which unions all 11 releases into `/tmp/plfs_bq`), uploaded with source-prefixed
  names that map 1:1 to the eventual BQ tables: `plfs_fact_persons`,
  `plfs_fact_households`, `plfs_dim_nco` / `nic` / `geo`, `plfs_releases`.

```bash
python3 scripts/load_bq.py --dry-run                          # joined parquets → /tmp/plfs_bq
python3 scripts/upload_to_gcs.py --raw-dir <raw> --parquet-dir /tmp/plfs_bq
#   --raw-only / --clean-only / --dry-run
```

The BQ load is deferred to post-approval. When it runs it can use the dataframe
loader above (point `--dataset external_data_sources`, table names gain the
`plfs_` prefix) or be switched to load the staged parquets from GCS via
`load_table_from_uri`.

## Status

| Release          | Format   | Catalog | Parsed | Sample size |
| ---------------- | -------- | :-----: | :----: | -----------:|
| `annual_2018_19` | annual   | 216     | ✅     | persons: 420k FV / 533k RV |
| `annual_2019_20` | annual   | 217     | ✅     | persons: 418k FV / 523k RV |
| `annual_2020_21` | annual   | 206     | ✅     | persons: 413k FV / 510k RV |
| `calendar_2021`  | calendar | 209     | ✅     | persons: 421k (limited schema) |
| `annual_2021_22` | annual   | 214     | ✅     | persons: 428k FV / 511k RV |
| `calendar_2022`  | calendar | 211     | ✅     | persons: 425k |
| `annual_2022_23` | annual   | 210     | ✅     | persons: 419k FV / 508k RV |
| `calendar_2023`  | calendar | 208     | ✅     | persons: 416k (half-yearly) |
| `annual_2023_24` | annual   | 213     | ✅     | persons: 418k FV / 504k RV |
| `calendar_2024`  | calendar | 254     | ✅     | persons: 416k |
| `calendar_2025`  | calendar | 284     | ✅     | persons: 1.15M |

Total: **~10.5M person-rows** across all releases.

## Source attribution

PLFS data is published by the **National Statistical Office, MoSPI, Govt of
India** at https://microdata.gov.in. Use freely under their terms — cite the
catalog ID + reference period of any release you use.
