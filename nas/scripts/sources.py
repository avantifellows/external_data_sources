"""
NAS 2021 source configuration — the single source of truth.

Everything downstream (clean_nas.py, upload_to_gcs.py, load_bq.py) reads from
here.

Source: NAS 2021 (National Achievement Survey), NCERT. The upstream artifact is
the community CSV mirror gsidhu/NAS-2021-data
(https://github.com/gsidhu/NAS-2021-data) — a tidy CSV form of NCERT's
published NAS 2021 results. `scripts/fetch.py` shallow-clones that repo into
raw/, so the source CSVs land at raw/NAS-2021-data/csv_data/.

GCS layout (udise/ convention):
    gs://avantifellows-external-data/nas/raw/<...>            (traceability)
    gs://avantifellows-external-data/nas/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # cloned community CSV mirror (gitignored)
CLEAN = ROOT / "clean"    # aggregated parquet, ready for upload (gitignored)

# Raw source: the gsidhu/NAS-2021-data repo cloned into raw/ by fetch.py; its
# CSVs live under csv_data/ (gitignored — see fetch.py / module docstring).
SOURCE_REPO = "https://github.com/gsidhu/NAS-2021-data"
SOURCE_CSV_DIR = RAW / "NAS-2021-data" / "csv_data"
SURVEY_YEAR = "2021"

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nas"

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
        bq_name="nas_fact_state_proficiency",
        parquet="state_proficiency.parquet",
        grain="(state, grade, subject, dimension, category)",
    ),
]
