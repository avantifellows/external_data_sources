"""
JEE (Advanced) aggregate marks at published ranks — source configuration.

Source: the Joint Implementation Committee (JIC) report of each JEE
(Advanced) year, jeeadv.ac.in/reports/<year>.pdf, Volume 1 sections
6.8-6.13 "Aggregate Total Marks with Different Ranks in CRL / GEN-EWS /
OBC-NCL / SC / ST / CRL-PwD": the aggregate marks (Paper 1 + Paper 2, out of
360) scored by the candidate at ranks 1, 101, 201, ... of each rank list.

GCS layout:
    gs://avantifellows-external-data/jeeadv/raw/<file>
    gs://avantifellows-external-data/jeeadv/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "jeeadv"
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class RawFile:
    year: int
    name: str
    url: str
    max_marks: int          # aggregate maximum (both papers), from the report

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"


RAW_FILES = [
    RawFile(2025, "jic_report_2025.pdf", "https://jeeadv.ac.in/reports/2025.pdf", 360),
    RawFile(2026, "jic_report_2026.pdf", "https://jeeadv.ac.in/reports/2026.pdf", 360),
]

# report section -> rank list
SECTIONS = {"6.8": "CRL", "6.9": "GEN-EWS", "6.10": "OBC-NCL", "6.11": "SC",
            "6.12": "ST", "6.13": "CRL-PwD"}


@dataclass(frozen=True)
class Table:
    bq_name: str
    parquet: str
    grain: str

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"


TABLES = [Table("jeeadv_fact_marks_at_rank", "jeeadv_fact_marks_at_rank.parquet",
                "(exam_year, rank_list, rank)")]
