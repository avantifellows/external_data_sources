"""
JNV source configuration — single source of truth for the JNV NTA-results pipeline.

The JNV cohort's NTA exam results (JEE Main, JEE Advanced rank lists, NEET) arrive as per-year NTA
Excel/CSV exports plus Dakshana's self-reported result sheets. A `build_*` script per table reads the
raw files (raw/) and writes a harmonised clean parquet (clean/); upload_to_gcs.py stages it and
load_bq.py loads it into BigQuery.

raw/ and clean/ are gitignored — the bytes live in GCS (gs://avantifellows-external-data/jnv/), the
build recipe lives in git.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "jnv"                            # gs://{bucket}/{prefix}/{raw,clean}/

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"          # asia-south1
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class Table:
    bq_name: str                              # BQ table (no project/dataset)
    parquet: str                              # filename in clean/ and on GCS
    clustering: tuple[str, ...] = field(default_factory=tuple)   # BQ clustering cols
    column_renames: dict[str, str] = field(default_factory=dict)

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
        bq_name="jnv_fact_jee_advanced_rank_list",
        parquet="jnv_fact_jee_advanced_rank_list.parquet",
        clustering=("test_year", "category"),
    ),
    Table(
        bq_name="jnv_fact_jee_main_candidate_details",
        parquet="jnv_fact_jee_main_candidate_details.parquet",
        clustering=("test_year", "qual_state"),
    ),
]

# Original NTA exports kept in GCS for audit/reproducibility. local path (under raw/) -> GCS raw subpath.
# Mirrors the existing jnv raw layout (raw/jee_advanced/, raw/jee_mains/, ...).
RAW_FILES: list[tuple[str, str]] = [
    ("jee_advanced/JEE Advanced 2024.csv", "jee_advanced/"),
    ("jee_advanced/JEE Advanced 2025.csv", "jee_advanced/"),
    ("jee_mains/2025 NTA JNV - JEE Main.csv", "jee_mains/"),
]
