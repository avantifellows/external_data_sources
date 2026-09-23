"""
AIIMS B.Sc. (Hons.) Nursing seat allocation — source configuration, the
single source of truth.

Source: AIIMS New Delhi Examination Section result notifications for the
2025 session — No. 117/2025 (Round 1, 19.07.2025) and No. 132/2025
(Round 2, 02.08.2025), aiimsexams.ac.in. Each lists every eligible
candidate in overall-rank order with the institute and seat category
allotted (or NR/NP: did not participate; FCNA: filled choices not
available at that rank), and ends with the last rank allotted per
category. Allotment is to B.Sc. (Hons.) Nursing at AIIMS New Delhi and
17 other AIIMS on the AIIMS B.Sc. Nursing entrance OVERALL rank.

Roll numbers are dropped at parse time; nothing downstream needs them.

GCS is the canonical raw source — build_clean.py fetches missing PDFs.

GCS layout:
    gs://avantifellows-external-data/aiimsnursing/raw/<pdf>
    gs://avantifellows-external-data/aiimsnursing/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

YEAR = 2025  # the 2025 session

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "aiimsnursing"

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


RAW_FILES = [RawFile("aiims_bsc_nursing_2025_round1.pdf"),
             RawFile("aiims_bsc_nursing_2025_round2.pdf")]


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
    Table("aiimsnursing_fact_allotments", "aiimsnursing_fact_allotments.parquet",
          "(round, overall_rank)"),
    Table("aiimsnursing_fact_cutoffs", "aiimsnursing_fact_cutoffs.parquet",
          "(round, institute, seat_category)"),
]
