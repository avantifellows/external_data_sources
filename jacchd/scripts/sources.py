"""
JAC Chandigarh cutoffs source configuration — the single source of truth.

Source: the Joint Admission Committee, Chandigarh (jacchd.admissions.nic.in)
publishes round-wise opening and closing ranks for first-year B.E. / B.Arch
at five institutes: CCET and CCA (Chandigarh Administration) and Panjab
University's UIET, Dr. S.S. Bhatnagar UICET and UIET Hoshiarpur. The team
transcribed the 2026 cycle (Rounds 1-3, Special, SPOT) into one Google
Sheet; its CSV export is the raw file here.

Ranks are JEE Main ranks (Paper 1 for B.E., Paper 2 for CCA's B.Arch),
except the Defence and Sports lists, which print positions in their own
merit list. build_clean.py tags each row's rank_basis so they never mix.

GCS is the canonical raw source — build_clean.py fetches it when the local
copy is missing; local raw/ is only a cache.

GCS layout:
    gs://avantifellows-external-data/jacchd/raw/<csv>
    gs://avantifellows-external-data/jacchd/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

YEAR = 2026  # the 2026 admission cycle

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "jacchd"

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


RAW_FILES = [RawFile("jacchd_2026_cutoffs_sheet.csv")]


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
    Table("jacchd_fact_cutoffs", "jacchd_fact_cutoffs.parquet",
          "(round, institute, programme_raw, quota, category_raw)"),
]
