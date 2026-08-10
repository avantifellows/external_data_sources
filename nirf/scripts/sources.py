"""
NIRF source configuration — the single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here:
- where the raw parquet files land locally
- where build_clean.py writes the clean parquets
- the canonical GCS bucket + prefix where they're staged
- the BQ destination project / dataset / table mapping
- the documented grain of each table (used by build_clean.py to deduplicate)
- per-table column rename maps (source col → BQ-friendly name)

GCS layout (matches the repo convention — raw/ for traceability, clean/ for BQ):
  gs://avantifellows-external-data/nirf/raw/<parquet>     the Dataful-derived inputs
  gs://avantifellows-external-data/nirf/clean/<parquet>   what load_bq.py loads

Pipeline:
  gs://…/nirf/raw/*.parquet  →  raw/*.parquet  →  build_clean.py  →  clean/*.parquet
                                                                          │  upload_to_gcs.py
                                                                          ▼
                                       gs://avantifellows-external-data/nirf/clean/*.parquet
                                                                          │  load_bq.py
                                                                          ▼
                                       avantifellows.external_data_sources.nirf_fact_*

When NIRF publishes new data, replace the parquet files in nirf/raw/ with the
same filenames and re-run build_clean.py + upload_to_gcs.py + load_bq.py.
Overwrite-in-place is intentional: NIRF data is mostly additive (new year
appends rows; historical years rarely change), and BQ's 7-day time travel
covers short rollbacks.

⚠️ The raw parquets are NOT raw NIRF data — see README.md "Data provenance".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
RAW   = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nirf"                          # gs://{bucket}/{prefix}/{raw,clean}/*.parquet

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str                              # table in BQ (no project/dataset)
    parquet: str                              # filename in raw/, clean/ and on GCS
    grain: tuple[str, ...]                    # documented grain; build_clean dedups on it
    column_renames: dict[str, str]            # source col → BQ col (only cols that need it)
    derived: bool = False                     # True = built by build_clean, no raw/ input

    @property
    def gcs_uri(self) -> str:
        """Clean parquet on GCS — the object load_bq.py reads."""
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def raw_gcs_uri(self) -> str:
        """Raw parquet on GCS — kept for traceability; fetch into raw/ to rebuild."""
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        """Clean parquet written by build_clean.py; read by upload_to_gcs.py."""
        return CLEAN / self.parquet

    @property
    def raw_path(self) -> Path:
        return RAW / self.parquet


# `nirf_fact_aggregate` is pivoted from `nirf_fact_master`, so its measure
# columns inherit master's `category` values — which contain spaces and `%`
# signs that BigQuery won't accept as identifiers. build_clean.py renames them
# so the clean parquet, the GCS file and the BQ table all agree.
AGGREGATE_RENAMES = {
    "Median salary of placed graduates":                    "median_salary",
    "Number of first year students intake":                 "first_year_intake",
    "Number of first year students admitted":               "first_year_admitted",
    "Number of students admmited through lateral entry":    "lateral_entry_admitted",
    "Number of students graduating in min stipulated time": "graduating_on_time",
    "Number of students placed":                            "students_placed",
    "Number of students selected for higher studies":       "higher_studies_selected",
    "Percentage Placed (%)":                                "percentage_placed",
    "Admission Rate (%)":                                   "admission_rate",
}

# How nirf_fact_aggregate is rebuilt from the deduplicated master.
AGGREGATE_PIVOT_INDEX = ["institute_id", "ranking_category", "ranking_year",
                         "academic_year", "type"]
AGGREGATE_JOIN_KEYS   = ["institute_id", "ranking_year", "ranking_category"]

TABLES: list[Table] = [
    Table(
        bq_name="nirf_fact_rankings",
        parquet="nirf_rankings.parquet",
        grain=("ranking_year", "ranking_category", "institute_id"),
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_master",
        parquet="nirf_master.parquet",
        grain=("ranking_year", "ranking_category", "institute_id",
               "type", "academic_year", "category"),
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_strength",
        parquet="nirf_strength.parquet",
        grain=("ranking_year", "ranking_category", "institute_id",
               "programme", "category"),
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_aggregate",
        parquet="nirf_aggregate.parquet",
        grain=("ranking_year", "ranking_category", "institute_id",
               "academic_year", "type"),
        column_renames=AGGREGATE_RENAMES,
        derived=True,          # rebuilt from master + rankings, no raw/ input
    ),
]
