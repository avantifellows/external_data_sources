"""
AICTE source configuration — the single source of truth.

Everything downstream (clean_aicte.py, upload_to_gcs.py, load_bq.py) reads from
here:
- where the raw panel CSVs live locally before cleaning
- where the cleaned parquet is written before upload
- the canonical GCS bucket + prefix where raw + clean are staged
- the BQ destination project / dataset / table mapping

Source: AICTE technical-education dashboard JSON API
(facilities.aicte-india.org), covering approved intake / enrolment / passouts /
placements / institution counts for the six technical streams (Engineering &
Technology, Management, MCA, Pharmacy, Architecture, Hotel Management) across
academic years 2012-13 → 2022-23. fetch.py pulls three cuts (national, state,
institution-type) into raw/ as three panel CSVs.

GCS layout (mirrors the jnv/ / udise/ convention):
    gs://avantifellows-external-data/aicte/raw/panel_*.csv          (traceability)
    gs://avantifellows-external-data/aicte/clean/<table>.parquet    (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source panel CSVs pulled by fetch.py (gitignored)
CLEAN = ROOT / "clean"    # cleaned parquet, ready for upload (gitignored)

# ─── Raw source panels (gitignored; produced by fetch.py from the AICTE API) ──
PANEL_NATIONAL = RAW / "panel_national.csv"       # program × level × year
PANEL_STATE = RAW / "panel_state.csv"             # state × program × level × year
PANEL_INST_TYPE = RAW / "panel_inst_type.csv"     # institution_type × program × level × year

RAW_PANELS: list[Path] = [PANEL_NATIONAL, PANEL_STATE, PANEL_INST_TYPE]

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "aicte"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Clean tables (cleaned → GCS clean/ → loaded to BQ) ───────────────────────
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
        bq_name="aicte_fact_intake",
        parquet="intake.parquet",
        grain="(year, program, level, state, institution_type)",
    ),
]
