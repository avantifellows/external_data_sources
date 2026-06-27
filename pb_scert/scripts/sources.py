"""
Central config for the pb_scert pipeline scripts.
GCS paths, BQ identifiers, and table definitions all live here.
"""

from dataclasses import dataclass
from pathlib import Path
import sys

PB_SCERT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PB_SCERT_DIR.parent))

# ── GCS ───────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "pb_scert"

# ── BigQuery ──────────────────────────────────────────────────────────────────
BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass
class Table:
    name: str
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


MERIT_LIST_CLEAN = Table(
    name="pb_scert_fact_soe_rsms_admission_merit_list",
    local_path=PB_SCERT_DIR / "clean" / "merit_list_clean.csv",
)


@dataclass
class RawFile:
    file: str
    sheet: str

    @property
    def gcs_path(self):
        stem = Path(self.file).stem.lower().replace(" ", "_")
        return f"{GCS_PREFIX}/raw/{stem}.parquet"

    @property
    def local_path(self):
        return PB_SCERT_DIR / "raw" / self.file


RAW_MERIT_LIST_FILES = [
    RawFile(
        "SOE & RSMS Admission Test Merit List_ 2024-26 (3 years).xlsx",
        "Student List",
    ),
]
