"""
TG-EAPCET / TGCHE Telangana source configuration — single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here.

Source: TG-EAPCET 2025 Last Rank Statements (First / Second / Final Phase),
        published by TGCHE + Convener TG-EAPCET (JNTU Hyderabad) at
        https://tgeapcetd.nic.in/files/. Raw CSVs are produced by state_TG.py
        in the futures-v2 repo (state_cet/scrape/scripts/).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"      # gitignored — drop parsed CSVs here before running
CLEAN = ROOT / "clean"  # gitignored — clean parquet written here

# ONE stream, ONE year — unlike gujcet, which carries engineering 2025 and
# pharmacy 2024 and therefore needs year+stream scoping everywhere.
#
# The "all_cutoffs" file is every institute type and is PER-PHASE (long:
# one row per college × branch × category × phase). "closing_ranks_govt" is
# the govt-scope subset already aggregated to MAX-across-phases with the full
# canonical column set. build_clean.py takes the all-types rows as the row set
# and re-derives everything, so the shipped table is ALL colleges WITH the
# canonical columns — the same choice kcet/, mhtcet/ and gujcet/ make, where
# govt scope is a *query* (college_type IN (...)) rather than a pipeline
# decision baked into the data.
RAW_FILES = [
    "TG_engg_all_cutoffs_2025.csv",
    "TG_engg_closing_ranks_govt_2025.csv",
]
OPTIONAL_RAW_FILES: list[str] = [
    "TG_engg_consolidated_5cat_govt_2025.csv",
]

# The official TG-EAPCET PDFs the CSVs were parsed from — the auditable source
# of record. Mirrored to GCS (never git) so any rank in the fact table can be
# traced back to the page it came from without re-scraping the portal.
RAW_PDF_DIR = RAW / "pdfs"
RAW_PDF_FILES = [
    "TGEAPCET_2025_LASTRANKS_FirstPhase.pdf",
    "TGEAPCET_2025_LASTRANKS_SecondPhase.pdf",
    "TGEAPCET_2025_FINALPHASE_LASTRANKS.pdf",
]

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "tgeapcet"   # gs://{bucket}/{prefix}/clean/*.parquet

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
        bq_name="tgeapcet_fact_cutoffs",
        parquet="tgeapcet_fact_cutoffs.parquet",
        # Query-oriented: almost every question filters year first, then the
        # candidate's category and gender pool, then narrows to a college.
        clustering_fields=["year", "category", "gender", "college_name"],
    ),
]
