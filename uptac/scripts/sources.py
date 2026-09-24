"""
UPTAC (Uttar Pradesh Technical Admission Counselling) OR-CR — source
configuration, the single source of truth.

Source: UPTAC's public OR-CR "cut-off matrix" on the Samarth portal
(uptac.samarth.edu.in), every round and programme: opening/closing rank
and min/max score per round x institute x programme x branch x category x
seat gender. Fetched page by page as HTML (fetch_pages.py); the pages are
the raw artifact, zipped to GCS.

GCS layout:
    gs://avantifellows-external-data/uptac/raw/uptac_orcr_pages_<date>.zip
    gs://avantifellows-external-data/uptac/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
PAGES = RAW / "pages"
CLEAN = ROOT / "clean"

BASE_URL = ("https://uptac.samarth.edu.in/index.php/cut-off-matrix/index?"
            "PrgAdmissionCutOffSeatsSearch%5Bactivity_id%5D=&PrgAdmissionCutOffSeatsSearch%5Bou_id%5D="
            "&PrgAdmissionCutOffSeatsSearch%5Bparent_programme_id%5D=&PrgAdmissionCutOffSeatsSearch%5Bprogramme_id%5D="
            "&PrgAdmissionCutOffSeatsSearch%5Bcategory_id%5D=")

YEAR = 2026  # the counselling session the grid publishes

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "uptac"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


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
    Table("uptac_fact_cutoffs", "uptac_fact_cutoffs.parquet",
          "(round, institute, programme, branch, category, seat_gender)"),
]
