"""
BITSAT cut-off scores — source configuration.

Source: BITS Pilani's admissions page "BITSAT cutoff Links"
(admissions.bits-pilani.ac.in/FD/BITSAT_cutOffs.html), one page holding the
final cut-off score per campus (Pilani, K K Birla Goa, Hyderabad) and
programme for every academic year 2017-18 to 2026-27, each year in a
<div id="YYYY-YYYY">. Saved as an HTML snapshot (the page is replaced as
years are added).

GCS layout:
    gs://avantifellows-external-data/bitsat/raw/<file>
    gs://avantifellows-external-data/bitsat/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "bitsat"
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"

PAGE_URL = "https://admissions.bits-pilani.ac.in/FD/BITSAT_cutOffs.html"


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"


# newest snapshot last; build_clean reads the last one
RAW_FILES = [RawFile("bitsat_cutoffs_page_2026-10-07.html", PAGE_URL)]


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


TABLES = [Table("bitsat_fact_cutoffs", "bitsat_fact_cutoffs.parquet",
                "(academic_year, campus, program)")]
