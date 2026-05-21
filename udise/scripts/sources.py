"""
UDISE+ source configuration — the single source of truth.

Everything downstream (clean_udise.py, upload_to_gcs.py, load_bq.py) reads from
here.

Source: UDISE+ Dashboard "Report 4000 — Enrolment by Location, School Category
and School Management for Each Class & Level of Education", AY 2024-25, exported
from the interactive dashboard at https://dashboard.udiseplus.gov.in/. The
dashboard has no static download URL (the report is generated on demand), so —
like PLFS — there is no fetch.py; the raw xlsx staged on GCS is the regenerable
source of record.

GCS layout (jnv/ convention):
    gs://avantifellows-external-data/udise/raw/<xlsx>          (traceability)
    gs://avantifellows-external-data/udise/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source xlsx (gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)

# Raw source workbook (gitignored; dashboard export — see module docstring).
SOURCE_XLSX = RAW / "udise_2024-25_enrolment.xlsx"
SHEET = "UDISE+"
ACADEMIC_YEAR = "2024-25"

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "udise"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
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
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet


TABLES: list[Table] = [
    Table(
        bq_name="udise_fact_enrolment",
        parquet="enrolment.parquet",
        grain="(academic_year, state, school_management, school_category, urban_rural, class_level, gender)",
    ),
]
