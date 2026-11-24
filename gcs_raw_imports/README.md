# gcs_raw_imports

Records of raw files put into `gs://avantifellows-external-data` from outside a
source's own pipeline, so every object in the bucket can be traced to where it
came from and what it is.

## `dropbox_2026-11-24.csv`

174 files (1.06 GB) that existed only in Dropbox: in a stale Dropbox clone of
this repo, and in the `India Public Education Data` folder. They were uploaded
without overwriting anything, and every object was checksum-verified (MD5, or
CRC32C for the three composite uploads). The Dropbox copies have not been deleted.

Columns: `gcs_uri`, `md5_base64` (of the local file), `bytes`, `source`,
`dropbox_path` (relative to the Dropbox `Claude/` folder), `contents`.

| source | files | notes |
|---|---|---|
| `nvs` | 5 | NVS annual reports 2019-24. Fuller provenance (original URL, which script uses each) is in India-education-data `sources/GCS_MANIFEST.csv` |
| `aicte` | 1 | AICTE Annual Report 2023-24, same as above |
| `josaa` | 58 | an older Dropbox scrape, under `josaa/raw/_dropbox_2026-11-24/`. Same file names as the canonical `josaa/raw/` but different bytes; the pipeline here does not read them |
| `mcc` | 8 | MCC NEET-UG all-India-quota closing ranks |
| `state_cet` | 31 | state CET engineering closing ranks |
| `state_medical` | 71 | state-quota medical closing ranks |

**Gap:** `mcc`, `state_cet` and `state_medical` have no pipeline in this repo
and no BigQuery table. Their scrape and build scripts exist only in the Dropbox
clone. The raw data is safe here, but until those pipelines are ported, nothing
in git can rebuild a table from it.
