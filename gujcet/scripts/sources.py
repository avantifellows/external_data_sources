"""
GUJCET / ACPC Gujarat source configuration — single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here.

Source: ACPC (Admission Committee for Professional Courses, Gujarat) closure
        PDFs. Raw CSVs are produced by state_GJ.py in the futures-v2 repo
        (state_cet/scrape/scripts/).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"      # gitignored — drop parsed CSVs here before running
CLEAN = ROOT / "clean"  # gitignored — clean parquet written here

# Two streams, two source PDFs, two different admission YEARS — engineering is
# 2025-26, pharmacy is 2024-25 (the latest ACPC has published in the wide
# rank+percentile format). The year column keeps them distinguishable; never
# aggregate across streams without filtering on it.
#
# The "all_cutoffs" file is every institute type; "closing_ranks_govt" is the
# govt-scope subset with the full canonical column set. build_clean.py joins
# them so the shipped table is ALL colleges WITH the canonical columns.
RAW_FILES = [
    "GJ_engg_all_cutoffs_2025.csv",
    "GJ_engg_closing_ranks_govt_2025.csv",
    "GJ_pharm_all_cutoffs_2024.csv",
    "GJ_pharm_closing_ranks_govt_2024.csv",
]
OPTIONAL_RAW_FILES: list[str] = []

# The official ACPC PDFs the CSVs were parsed from — the auditable source of
# record. Mirrored to GCS (never git) so any number in the fact table can be
# traced back to the page it came from without re-scraping the portal.
RAW_PDF_DIR = RAW / "pdfs"
RAW_PDF_FILES = [
    "GJ_ACPC_2025_Final_RankAndMarks.pdf",
    "GJ_ACPC_2024_Pharmacy_Closure.pdf",
]

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "gujcet"   # gs://{bucket}/{prefix}/clean/*.parquet

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
        bq_name="gujcet_fact_cutoffs",
        parquet="gujcet_fact_cutoffs.parquet",
        # Query-oriented: almost every question filters stream + year first,
        # then the candidate's category, then narrows to a college.
        clustering_fields=["year", "stream", "category", "college_name"],
    ),
]
