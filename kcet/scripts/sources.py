"""
KCET source configuration — single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here.

Source: KEA (Karnataka Examinations Authority) cutoff PDFs.
        Raw CSV is produced by parse_KA_2025.py in the futures-v2 repo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"      # gitignored — drop source CSV here before running
CLEAN = ROOT / "clean"  # gitignored — clean parquet written here
CODEMAPS = ROOT / "codemaps"

RAW_FILES = [
    "KA_engg_2025_GEN_R3.pdf",
    "KA_engg_2025_HK_R3.pdf",
    "KA_engg_2025_all_cutoffs_R3.csv",
    "KA_engg_2025_draft_seat_matrix.pdf",
]
OPTIONAL_RAW_FILES = ["KA_engg_closing_ranks_govt_2024.csv"]

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "kcet"     # gs://{bucket}/{prefix}/clean/*.parquet

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
        bq_name="kcet_fact_cutoffs",
        parquet="kcet_fact_cutoffs.parquet",
        clustering_fields=["year", "domicile_pool", "category_code", "college_code"],
    ),
]
