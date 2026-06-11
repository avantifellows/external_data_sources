"""
MCC (Medical Counselling Committee) source configuration — single source of truth.

MCC runs the national-level medical admission counselling: the 15% All India
Quota of government MBBS/BDS seats, plus 100% of deemed/central-university/ESI
seats. Admission is on the NEET-UG All India Rank (AIR). This is the medical
counterpart to JoSAA — and the national counterpart to the state-quota seats
in `state_medical_*` (the ~85% pool counselled by state authorities).

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads here.

Upstream: the College DB medical-national-ranks pipeline parses the MCC R1
allotment PDF into closing_ranks_aiq_r1_2025.csv. Drop that into mcc/raw/ and
re-run build_clean + upload + load on a new counselling cycle.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "mcc"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"          # asia-south1
BQ_LOCATION = "asia-south1"

# ─── Raw input ───────────────────────────────────────────────────────────────
# AIQ Round-1 allotment, by (institute, course, quota, alloted_category).
# build_clean.py splits alloted_category → (category, is_pwd) and stamps the
# constant year/round (this file is the 2025-26 cycle, Round 1).
RAW_FILE = "closing_ranks_aiq_r1_2025.csv"
CYCLE_YEAR = 2025
CYCLE_ROUND = 1


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str
    parquet: str
    clustering_fields: list[str] = field(default_factory=list)

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet


TABLES: list[Table] = [
    Table(
        bq_name="mcc_fact_closing_ranks",
        parquet="mcc_fact_closing_ranks.parquet",
        clustering_fields=["year", "round", "course", "category"],
    ),
]
