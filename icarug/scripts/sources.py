"""
ICAR-UG (CUET) counselling cutoffs — source configuration, the single
source of truth.

Source: ICAR's "Cut off - CUET (ICAR-UG) - 2025" (886-page PDF exported
from a spreadsheet, watermarked "ICAR"), and a CSV extraction of it shared
by the team. Admission to B.Sc. (Hons.) Agriculture / Horticulture /
Forestry, B.Tech. Agricultural Engineering / Food / Dairy, B.F.Sc. and
others at 72 agricultural universities, through the ICAR-UG counselling
on the CUET (UG) score. Five rounds: First - Fourth and Mop-up.

Each row: round x allottees' home state x course x university x category
-> CUET marks (three subjects) and ICAR-UG overall rank, first and last
allotted. build_clean.py builds from the CSV and checks every number of it
against the PDF (after removing the rows the PDF prints twice across page
breaks).

GCS is the canonical raw source — build_clean.py fetches missing files.

GCS layout:
    gs://avantifellows-external-data/icarug/raw/<file>
    gs://avantifellows-external-data/icarug/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

YEAR = 2025  # the 2025 counselling

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "icarug"

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


RAW_FILES = [RawFile("icar_ug_cutoff_2025.pdf"), RawFile("icar_ug_cutoff_2025.csv")]


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
    Table("icarug_fact_cutoffs", "icarug_fact_cutoffs.parquet",
          "(round, home_state, course, university_raw, category)"),
]
