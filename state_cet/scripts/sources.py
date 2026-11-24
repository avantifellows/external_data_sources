"""
State-CET source configuration — the single source of truth.

Engineering (+ pharmacy/nursing/architecture) admission cutoffs from India's
STATE Common Entrance Tests (MHT-CET, KCET, TNEA, EAMCET, WBJEE, KEAM, …) —
the state-quota counterpart to JoSAA's national pool.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here.

Upstream: the per-state scrapers + consolidate_all.py in the College DB repo
(state-cet-scrape/) produce ALL_STATES_consolidated_5cat_govt.csv. Drop that
file into state_cet/raw/ and re-run build_clean + upload + load when states
are added or refreshed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "state_cet"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"          # asia-south1
BQ_LOCATION = "asia-south1"

# ─── Raw input ───────────────────────────────────────────────────────────────
# The consolidated all-states file is already snake_case and analyst-clean;
# build_clean.py only types columns + tidies college_name newlines.
RAW_FILE = "ALL_STATES_consolidated_5cat_govt.csv"


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
        bq_name="state_cet_fact_closing_ranks",
        parquet="state_cet_fact_closing_ranks.parquet",
        clustering_fields=["state", "cet_name", "year", "category"],
    ),
]
