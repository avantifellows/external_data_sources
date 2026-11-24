"""
State medical counselling source configuration — single source of truth.

The state-quota (~85%) MBBS/BDS seats counselled by ~30 individual STATE
authorities, harmonized across 32 states/UTs into one fact. The state-quota
counterpart to MCC's national All India Quota (`mcc_*`).

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads here.

Upstream: the College DB medical-state-counselling pipeline (35 per-state
parsers + national consolidation) produces national_closing_ranks_unified_AIR_2025.csv.
We ingest the NEUTRAL projection of that file (actual closing ranks + native
rank-space provenance + official/third-party flag) and deliberately DROP the
Avanti modeling columns (AIR estimation, tier, multiplier, estimated R3).
Drop the file into state_medical/raw/ and re-run build_clean + upload + load.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "state_medical"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"          # asia-south1
BQ_LOCATION = "asia-south1"

# ─── Raw input ───────────────────────────────────────────────────────────────
# The unified file is the superset (carries conversion_method, which documents
# each native value's rank space). build_clean.py projects to neutral columns.
RAW_FILE = "national_closing_ranks_unified_AIR_2025.csv"
CYCLE_YEAR = 2025


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
        bq_name="state_medical_fact_closing_ranks",
        parquet="state_medical_fact_closing_ranks.parquet",
        clustering_fields=["state", "program", "category", "year"],
    ),
]
