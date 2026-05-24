"""
NMC seat-matrix source configuration — the single source of truth.

Everything downstream (clean_nmc.py, upload_to_gcs.py, load_bq.py) reads from
here:
- where the raw NMC seat-matrix PDF lives locally before parsing
- where the parsed parquet file is written before upload
- the canonical GCS bucket + prefix where raw + clean are staged
- the BQ destination project / dataset / table mapping

Source: National Medical Commission (NMC) "Revised UG (MBBS) Seat Matrix
2024-25" — the state-wise list of MBBS medical colleges (including AIIMS &
JIPMER) functioning in the country, with their annual intake of seats. One PDF,
~780 colleges across all states/UTs.

GCS layout (mirrors the board_results/ convention):
    gs://avantifellows-external-data/nmc/raw/<pdf>          (traceability)
    gs://avantifellows-external-data/nmc/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source NMC seat-matrix PDF (gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)

SNAPSHOT = "2024-25"

# ─── Raw source PDF (gitignored; fetched from the URL below by fetch.py) ──────
PDF = RAW / "nmc_mbbs_seat_matrix_2024-25.pdf"

# Canonical source URL — NMC "Revised UG Seat Matrix 2024-25" (as on
# 31-03-2025), nmc.org.in. fetch.py downloads this into raw/ so the source file
# is regenerable from scratch.
PDF_URL = (
    "https://www.nmc.org.in/wp-content/uploads/2025/04/"
    "Revised%20UG%20Seat%20Matrix%202024-25%20on%2031-03-2025.pdf"
)

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nmc"

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
        bq_name="nmc_fact_mbbs_seats",
        parquet="mbbs_seats.parquet",
        grain="(snapshot, sl_no) — one row per MBBS medical college",
    ),
]


# ─── Raw PDF (uploaded to GCS raw/ as-is for traceability; NOT loaded to BQ) ──
@dataclass(frozen=True)
class RawFile:
    local_path: Path

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.local_path.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


RAW_FILES: list[RawFile] = [RawFile(PDF)]
