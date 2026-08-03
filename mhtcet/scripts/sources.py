"""
MHT-CET source configuration — single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here.

Source: Maharashtra State CET Cell CAP cutoff PDFs (2025-26 cycle), one portal
        per stream. Raw per-stream CSVs are produced by state_MH.py /
        state_MH_arch.py in the futures-v2 repo (state_cet/scrape/scripts/).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"      # gitignored — drop per-stream CSVs here before running
CLEAN = ROOT / "clean"  # gitignored — clean parquet written here

# One CSV per stream, each the "all colleges" closing-rank view (college_type is
# a column, not a filter — govt scope is a query, not a pipeline decision).
RAW_FILES = [
    "MH_engg_state_quota_closing_ranks_2025.csv",
    "MH_pharm_state_quota_closing_ranks_2025.csv",
    "MH_arch_state_quota_closing_ranks_2025.csv",
]
# bdesign has 3 private institutes and no govt seats; included when present.
OPTIONAL_RAW_FILES = ["MH_bdesign_state_quota_closing_ranks_2025.csv"]

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "mhtcet"   # gs://{bucket}/{prefix}/clean/*.parquet

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"   # asia-south1
BQ_LOCATION = "asia-south1"


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
        bq_name="mhtcet_fact_cutoffs",
        parquet="mhtcet_fact_cutoffs.parquet",
        # Query-oriented: almost every question filters stream first, then the
        # candidate's category and the quota pool, then narrows to a college.
        clustering_fields=["year", "stream", "category", "college_code"],
    ),
]
