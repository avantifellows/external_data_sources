"""
NAAC source configuration — single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here:
- where the raw xlsx lives locally
- where the clean parquets are written by build_clean.py
- the canonical GCS bucket + prefix where parquets are staged
- the BQ destination project / dataset / table mapping
- per-table sheet name, column rename map, and date columns

Pipeline:
  raw/*.xlsx  →  build_clean.py  →  clean/*.parquet
                                         │  upload_to_gcs.py
                                         ▼
                              gs://avantifellows-external-data/naac/*.parquet
                                         │  load_bq.py
                                         ▼
                              avantifellows.external_data_sources.naac_fact_*
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
RAW   = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "naac"                          # gs://{bucket}/{prefix}/*.parquet

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"        # asia-south1
BQ_LOCATION = "asia-south1"

# Date the source file was published on naac.gov.in.
# Stamped onto every row by build_clean.py so analysts know data vintage.
DATA_AS_OF = datetime.date(2025, 8, 14)

XLSX_FILE = "Institutions_accredited_by_NAAC_having_valid_accreditation-as_on_14082025_1.xlsx"


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name:        str               # table name in BQ (no project/dataset prefix)
    sheet:          str               # sheet name inside the xlsx
    parquet:        str               # filename in clean/ and on GCS
    column_renames: dict[str, str]    # xlsx col → BQ col
    date_columns:   list[str] = field(default_factory=list)  # BQ col names to parse as DATE

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        """Clean parquet written by build_clean.py; read by upload_to_gcs.py."""
        return CLEAN / self.parquet

    @property
    def raw_xlsx(self) -> Path:
        return RAW / XLSX_FILE


# Shared renames for Universities and Colleges sheets (same 9 columns).
_ACCREDITED_RENAMES = {
    "Sl No":                "sl_no",
    "HEI Name":             "hei_name",
    "Track-Id":             "track_id",
    "Aishe-Id":             "aishe_id",
    "Address":              "address",
    "Current Cycle Number": "current_cycle_number",
    "Current CGPA":         "current_cgpa",
    "Current Grade":        "current_grade",
    "Date Of Declaration":  "date_of_declaration",
}

TABLES: list[Table] = [
    Table(
        bq_name="naac_fact_universities",
        sheet="Universities",
        parquet="naac_fact_universities.parquet",
        column_renames=_ACCREDITED_RENAMES,
        date_columns=["date_of_declaration"],
    ),
    Table(
        bq_name="naac_fact_colleges",
        sheet="Colleges",
        parquet="naac_fact_colleges.parquet",
        column_renames={**_ACCREDITED_RENAMES, "Affiliating University": "affiliating_university"},
        date_columns=["date_of_declaration"],
    ),
    Table(
        bq_name="naac_fact_transition_autonomous_colleges",
        sheet="Transition Autonomous Colleges",
        parquet="naac_fact_transition_autonomous_colleges.parquet",
        column_renames={
            "Sl. No.":                "sl_no",
            "HEI Name":               "hei_name",
            "State":                  "state",
            "Extended validity upto":  "extended_validity_upto",
        },
        date_columns=["extended_validity_upto"],
    ),
]
