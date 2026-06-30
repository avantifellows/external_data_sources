"""
Central config for the UBSE pipeline scripts.
GCS paths, BQ identifiers, and table definitions all live here.
"""

from dataclasses import dataclass
from pathlib import Path
import sys

UBSE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(UBSE_DIR.parent))

# ── GCS ───────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "ubse"

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


GRADE10_CLEAN = Table(
    name="ubse_fact_grade10_results",
    local_path=UBSE_DIR / "clean" / "grade10_clean.csv",
)

GRADE12_CLEAN = Table(
    name="ubse_fact_grade12_results",
    local_path=UBSE_DIR / "clean" / "grade12_clean.csv",
)


@dataclass
class RawFile:
    file: str
    sheet: str
    exam_year: int
    subdir: str

    @property
    def gcs_path(self):
        stem = Path(self.file).stem.lower().replace(" ", "_")
        return f"{GCS_PREFIX}/raw/{self.subdir}/{stem}.parquet"

    @property
    def local_path(self):
        return UBSE_DIR / "raw" / self.file


RAW_GRADE10_FILES = [
    RawFile("G10th _ UBSE Board data 2026.xlsx", "HS_NET", 2026, "grade10"),
]

RAW_GRADE12_FILES = [
    RawFile("G12th _UBSE Board data - 2026.xlsx", "int_net", 2026, "grade12"),
]
