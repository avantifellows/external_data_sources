"""
BHU UG admission (CUET) cutoffs — source configuration, the single source
of truth.

Source: Banaras Hindu University's UG admission 2025 allocation summaries,
printed from spreadsheets: Round 1 ("allocation_summary_round_1", 85
pages) and Spot Round 2 (dt. 15.09.2025, 34 pages), and the team's CSV
combining both. Each row: programme x faculty/college x allotted quota ->
minimum score allotted. Scores are BHU's CUET-based merit score for that
programme; the scale differs by programme (B.A. up to ~374, B.Sc. ~637).

build_clean.py builds from the CSV and checks every row against the PDFs.

GCS layout:
    gs://avantifellows-external-data/bhuug/raw/<file>
    gs://avantifellows-external-data/bhuug/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

YEAR = 2025  # the 2025 admission

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "bhuug"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class RawFile:
    name: str

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


RAW_FILES = [RawFile("bhu_ug_2025_round1.pdf"), RawFile("bhu_ug_2025_spot2.pdf"),
             RawFile("bhu_ug_2025_combined.csv")]


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


TABLES = [
    Table("bhuug_fact_cutoffs", "bhuug_fact_cutoffs.parquet",
          "(round, program_raw, college_raw, category)"),
]
