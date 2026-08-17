"""
NEET 2026 minimum-marks matrix — source configuration, the single source of truth.

Everything downstream (build_parquet.py, upload_to_gcs.py, load_bq.py) reads from here.

WHAT THIS SOURCE IS
  For each state/UT and category, the minimum NEET marks that realistically win a
  GOVERNMENT MBBS (B1a) / BDS (B1b) seat, plus B2b (the national qualifying floor).
  370 rows = 37 tracks x 10 category rows — all 36 states/UTs plus "All India" (the
  15% All-India-Quota track). 32 tracks carry numbers; 5 are deliberately blank with
  the reason recorded in data_status.

  It answers "what is the bar?" — one floor per (state, category) — as against the
  per-college closing ranks that a college predictor needs.

PROVENANCE
  Built by the pipeline in futures-v2/neet/matrix_2026/ from ~30 official documents
  (state counselling cutoff PDFs, allotment lists, merit lists, and one admitted-student
  register published as page images). Those documents are staged to GCS raw/ below;
  the parsers' intermediate CSVs go to extracted/.

  Method, validation and per-state provenance:
    futures-v2/neet/matrix_2026/docs/NEET_2026_HOW_WE_BUILT_IT.md
    futures-v2/neet/matrix_2026/docs/NEET_SOURCE_OF_TRUTH.md

GCS layout (mirrors nmc/):
    gs://avantifellows-external-data/neet_matrix/raw/<pdf>              (traceability)
    gs://avantifellows-external-data/neet_matrix/raw/mizoram-zmch-2025-admitted/<png>
    gs://avantifellows-external-data/neet_matrix/extracted/<csv>        (parser output)
    gs://avantifellows-external-data/neet_matrix/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"          # source documents (gitignored)
EXTRACTED = ROOT / "extracted"  # parser output CSVs (gitignored)
CLEAN = ROOT / "clean"      # parquet, ready for upload (gitignored)

SNAPSHOT = "2026"           # the admission year the matrix projects to (from 2025 actuals)

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "neet_matrix"

# ─── BigQuery ─────────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"        # asia-south1
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
        bq_name="neet_dim_marks_matrix_2026",
        parquet="neet_marks_matrix_2026.parquet",
        grain="(snapshot, state, category) — one row per state/UT x category",
    ),
]
