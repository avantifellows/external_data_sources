"""
Dakshana source configuration — single source of truth for the Dakshana pipeline.

Dakshana shares self-reported result sheets per cycle. A build_*.py reads the raw sheets (raw/) and
writes a harmonised clean parquet (clean/); upload_to_gcs.py stages it, load_bq.py loads it.
raw/ and clean/ are gitignored — bytes live in GCS (gs://avantifellows-external-data/dakshana/).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "dakshana"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class Table:
    bq_name: str
    parquet: str
    clustering: tuple[str, ...] = field(default_factory=tuple)
    column_renames: dict[str, str] = field(default_factory=dict)

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet


TABLES: list[Table] = [
    Table(
        bq_name="dakshana_fact_reported_results",
        parquet="dakshana_fact_reported_results.parquet",
        clustering=("test_year", "exam"),
    ),
]

# Original Dakshana sheets kept in GCS for audit. local path (under raw/) -> GCS raw subpath.
RAW_FILES: list[tuple[str, str]] = [
    ("reported/Dakshana - JEE-NEET 2025_Result_NVS_16.06.2025.xlsx - JEE Main.csv", "reported/"),
    ("reported/Dakshana - 2025- NEET.csv", "reported/"),
]
