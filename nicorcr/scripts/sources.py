"""
NIC-hosted counselling OR-CR reports — source configuration, the single
source of truth.

Several counselling boards run on NIC's "Online Counselling System"
(admissions.nic.in) and publish opening / closing ranks as one HTML report
per programme and year (…/Applicant/report/orcrreport.aspx?enc=…), linked
from the board's own portal. The report only opens when visited from that
portal (a session cookie + Referer), and holds every round in one table.

Boards here: HBTU Kanpur (B.Tech on JEE Main CRL). MMMUT Gorakhpur uses the
same system, but its reports returned HTTP 500 for every year on
2026-09-25 (in a browser too) — add it to REPORTS when they open.

GCS layout:
    gs://avantifellows-external-data/nicorcr/raw/<board>_<programme>_<year>.html
    gs://avantifellows-external-data/nicorcr/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nicorcr"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class Report:
    board: str       # short code
    board_name: str
    portal: str      # the page that links the report (sets cookie + Referer)
    title: str       # link text on the portal, exactly
    programme: str
    year: int

    @property
    def raw_name(self) -> str:
        return f"{self.board.lower()}_{self.programme.lower().replace('.', '')}_{self.year}.html"


REPORTS = [
    Report("HBTU", "Harcourt Butler Technical University, Kanpur", "https://hbtu.admissions.nic.in/or-cr/",
           f"B. Tech. Opening and Closing Rank {y}", "B.Tech", y)
    for y in (2026, 2025, 2024)
]


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
    Table("nicorcr_fact_cutoffs", "nicorcr_fact_cutoffs.parquet",
          "(board, year, round, institute, programme_raw, quota, category_raw)"),
]
