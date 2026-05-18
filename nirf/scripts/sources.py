"""
NIRF source configuration — the single source of truth.

Everything downstream (upload_to_gcs.py, load_bq.py) reads from here:
- where the raw parquet files live locally before upload
- the canonical GCS bucket + prefix where they're staged
- the BQ destination project / dataset / table mapping
- per-table column rename maps (parquet → BQ-friendly names)

When NIRF publishes new data, drop the new parquet files into nirf/raw/
with the same filenames and re-run upload_to_gcs.py + load_bq.py.
Overwrite-in-place is intentional: NIRF data is mostly additive (new year
appends rows; historical years rarely change), and BQ's 7-day time travel
covers short rollbacks.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nirf"                          # gs://{bucket}/{prefix}/*.parquet

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str                              # table in BQ (no project/dataset)
    parquet: str                              # filename in raw/ and on GCS
    column_renames: dict[str, str]            # parquet col → BQ col (only for cols that need it)

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return RAW / self.parquet


# `nirf_fact_aggregate` has several columns with spaces / percent signs that
# BigQuery won't accept as identifiers. We rename them in-memory during the
# GCS upload step so the staged parquet (and the BQ table) are both clean.
AGGREGATE_RENAMES = {
    "Median salary of placed graduates":              "median_salary",
    "Number of first year students intake":           "first_year_intake",
    "Number of first year students admitted":         "first_year_admitted",
    "Number of students admmited through lateral entry": "lateral_entry_admitted",
    "Number of students graduating in min stipulated time": "graduating_on_time",
    "Number of students placed":                      "students_placed",
    "Number of students selected for higher studies": "higher_studies_selected",
    "Percentage Placed (%)":                          "percentage_placed",
    "Admission Rate (%)":                             "admission_rate",
}

TABLES: list[Table] = [
    Table(
        bq_name="nirf_fact_rankings",
        parquet="nirf_rankings.parquet",
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_aggregate",
        parquet="nirf_aggregate.parquet",
        column_renames=AGGREGATE_RENAMES,
    ),
    Table(
        bq_name="nirf_fact_strength",
        parquet="nirf_strength.parquet",
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_master",
        parquet="nirf_master.parquet",
        column_renames={},
    ),
]
