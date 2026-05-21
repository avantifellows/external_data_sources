"""
Board-results source configuration — the single source of truth.

Everything downstream (clean_*.py, upload_to_gcs.py, load_bq.py) reads from
here:
- where the raw MoE report PDFs live locally before parsing
- where the parsed parquet files are written before upload
- the canonical GCS bucket + prefix where raw + clean are staged
- the BQ destination project / dataset / table mapping

Source: MoE "Result of Secondary & Higher Secondary Examination" (RSHSE)
annual PDFs, covering Class X + Class XII board exam results across all
~41-58 boards. One PDF per year (2020, 2021, 2022, 2024 — no 2023 edition).

GCS layout (mirrors the jnv/ convention):
    gs://avantifellows-external-data/board_results/raw/<pdf>          (traceability)
    gs://avantifellows-external-data/board_results/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source MoE report PDFs (gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)

# ─── Raw source PDFs (gitignored; fetched from the URLs below by fetch.py) ────
REPORTS: dict[int, Path] = {
    2020: RAW / "moe_results_secondary_hs_2020.pdf",
    2021: RAW / "moe_results_secondary_hs_2021.pdf",
    2022: RAW / "moe_results_secondary_hs_2022.pdf",
    2024: RAW / "moe_results_secondary_hs_2024.pdf",
}

# Canonical source URLs — MoE "Result of Secondary & Higher Secondary
# Examination" (RSHSE) annual reports, education.gov.in. fetch.py downloads
# these into raw/ so the source files are regenerable from scratch.
_MOE = "https://www.education.gov.in/sites/upload_files/mhrd/files/statistics-new"
REPORT_URLS: dict[int, str] = {
    2020: f"{_MOE}/Result_Secondary_Higher_Secondary_Examination_2020.pdf",
    2021: f"{_MOE}/RSHSE2021.pdf",
    2022: f"{_MOE}/RSHSE2022.pdf",
    2024: f"{_MOE}/result-2024.pdf",
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "board_results"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Clean tables (parsed → GCS clean/ → loaded to BQ) ────────────────────────
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
        bq_name="board_results_fact_passes",
        parquet="board_results.parquet",
        grain="(year, level, state, board, social_category, stream, gender)",
    ),
]


# ─── Raw PDFs (uploaded to GCS raw/ as-is for traceability; NOT loaded to BQ) ──
@dataclass(frozen=True)
class RawFile:
    year: int

    @property
    def local_path(self) -> Path:
        return REPORTS[self.year]

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.local_path.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


RAW_FILES: list[RawFile] = [RawFile(y) for y in REPORTS]
