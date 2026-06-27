"""
Central config for the NVS NCST pipeline scripts.
GCS paths, BQ identifiers, and table definitions all live here.
"""

from dataclasses import dataclass
from pathlib import Path
import sys

NVS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NVS_DIR.parent))  # external_data_sources root

# ── GCS ───────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nvs"

# ── BigQuery ──────────────────────────────────────────────────────────────────
BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"

# ── Table definitions ─────────────────────────────────────────────────────────

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


NCST_CLEAN = Table(
    name="nvs_fact_ncst_results",
    local_path=NVS_DIR / "clean" / "ncst_clean.csv",
)

# ── Raw file definitions (Excel → parquet on GCS) ─────────────────────────────

@dataclass
class RawFile:
    file: str
    sheet: str
    subdir: str = "ncst"

    @property
    def gcs_path(self):
        stem = Path(self.file).stem.lower().replace(" ", "_")
        return f"{GCS_PREFIX}/raw/{self.subdir}/{stem}.parquet"

    @property
    def local_path(self):
        return NVS_DIR / "raw" / self.file


RAW_NCST_FILES = [
    RawFile("NCST 2026.xlsx", "NCST Data"),
]
