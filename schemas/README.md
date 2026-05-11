# BigQuery table schemas

Canonical column-level documentation for the six tables produced by
[`scripts/load_bq.py`](../scripts/load_bq.py). One YAML file per table.

| File | Rows | Purpose |
|---|---:|---|
| [`persons.yaml`](persons.yaml) | ~10.5M | Person-level fact — every analysis lives here |
| [`households.yaml`](households.yaml) | ~2.5M | Household-level fact — income proxy via `mpce` |
| [`releases.yaml`](releases.yaml) | 11 | Release registry — catalog IDs, URLs, weight rules |
| [`dim_nco.yaml`](dim_nco.yaml) | ~2,700 | Full NCO 2015 occupation hierarchy |
| [`dim_nic.yaml`](dim_nic.yaml) | ~1,300 | Full NIC 2008 industry hierarchy |
| [`dim_geo.yaml`](dim_geo.yaml) | ~700 | State + district lookup |

Schemas are documentation today. The loader script uses `autodetect=True`
when calling `bigquery.Client.load_table_from_dataframe`, which infers
column types from the pandas DataFrame. If we ever need stricter type
control (e.g. forcing NULLABLE → REQUIRED, or pinning `INT64` over
`NUMERIC`), wire these YAML files in as explicit schemas at load time.

## Conventions

- **All codes are STRING**, zero-padded as in the MoSPI source (`'01'`,
  `'62011'`). Storing as INT would lose the padding and break joins
  against the dim tables.
- **Labels are denormalized inline** on the fact tables as `*_label`
  columns for the common small-enum lookups (sex, sector, religion,
  marital status, education levels, activity status, enterprise type,
  job contract, social security, etc.). No separate `dim_sex` table.
- **Hierarchical dims** (NCO / NIC / geography) stay as separate
  tables because they have real structure analysts query against.
- **Weights** are pre-computed at load time as `weight_annual`. The
  raw inputs (`mult`, `nss`, `nsc`, `no_qtr`) are retained for
  transparency. CY2021 has a partial schema; `weight_annual` is NULL.
