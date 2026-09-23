"""
IISER closing ranks source configuration — the single source of truth.

Source: IISER Admissions website, "Round Wise Closing Ranks" page, saved as
one PDF (9 counselling rounds, newest first). Admission to the IISERs'
BS-MS / BS / B.Tech programmes is on the IISER Aptitude Test (IAT); the
closing ranks are IAT **overall** ranks (the page says so), per programme x
category (UR / EWS / OBC-NCL / SC / ST, each with a PwD column).

The page has no stable per-round URL, so the PDF is captured manually and
staged to GCS. GCS is the canonical raw source — build_clean.py fetches it
when the local copy is missing; local raw/ is only a cache.

GCS layout:
    gs://avantifellows-external-data/iiser/raw/<pdf>
    gs://avantifellows-external-data/iiser/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

YEAR = 2025  # the 2025 admission cycle's rounds

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "iiser"

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


RAW_FILES = [RawFile("iiser_round_wise_closing_ranks_2025.pdf")]


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
    Table("iiser_fact_cutoffs", "iiser_fact_cutoffs.parquet",
          "(round, program_name, category)"),
]
