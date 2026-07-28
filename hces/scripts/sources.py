"""
Central config for the HCES pipeline scripts.
GCS paths, BQ identifiers, and table definitions all live here.
"""

from dataclasses import dataclass
from pathlib import Path

HCES_DIR = Path(__file__).resolve().parent.parent   # external_data_sources/hces

# ── GCS ───────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "hces"

# ── BigQuery ──────────────────────────────────────────────────────────────────
BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"

# ── Clean table (loaded into BigQuery) ────────────────────────────────────────

@dataclass
class Table:
    name: str          # GCS filename stem + BQ table suffix
    local_path: Path

    @property
    def gcs_path(self):
        return f"{GCS_PREFIX}/clean/{self.name}.parquet"

    @property
    def gcs_uri(self):
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def bq_table_id(self):
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.name}"


HOUSEHOLD_MASTER = Table(
    name="hces_fact_household_master",
    local_path=HCES_DIR / "clean" / "hces_fact_household_master.parquet",
)

# ── Raw source files (15 NSS level CSVs, staged for audit) ─────────────────────
# The raw HCES 2023-24 microdata is a directory of 15 "level" CSVs. Only L1, L3
# and L15 feed the household master; all 15 are archived to GCS raw/ for audit.
RAW_SUBDIR = "HCES_Data_2023-24_Csv"      # local: raw/<subdir>/*.csv ; GCS: hces/raw/<subdir>/*.csv


@dataclass
class RawDir:
    subdir: str

    @property
    def local_dir(self):
        return HCES_DIR / "raw" / self.subdir

    @property
    def gcs_prefix(self):
        return f"{GCS_PREFIX}/raw/{self.subdir}"


RAW_LEVEL_CSVS = RawDir(RAW_SUBDIR)
