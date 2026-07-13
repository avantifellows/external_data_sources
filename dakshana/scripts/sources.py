"""
Dakshana source configuration — single source of truth for the Dakshana pipeline scripts.

Two output tables, two shapes:
  - dakshana_fact_ncst_results      NCST selection test (2022–2025). Raw = per-year Excel
                                    (one sheet each); clean = ncst_clean.csv, built by clean_ncst.py.
  - dakshana_fact_reported_results  Dakshana self-reported JEE/NEET results. Raw = per-cycle CSV
                                    (staged as-is); clean = parquet, built by build_reported_results.py.

A build_*.py / clean_*.py reads the raw sheets (raw/) and writes a harmonised clean artifact (clean/);
upload_to_gcs.py stages both raw and clean to GCS; load_bq.py loads the clean parquet into BQ.
raw/ and clean/ are gitignored — bytes live in GCS (gs://avantifellows-external-data/dakshana/).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"
sys.path.insert(0, str(ROOT))  # so post_read hooks can import codemaps.*

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "dakshana"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


# ── Output tables (clean artifact → GCS clean/ → BQ) ──────────────────────────

@dataclass(frozen=True)
class Table:
    bq_name: str
    parquet: str                       # clean parquet name under GCS clean/
    clean_file: str                    # local clean artifact under clean/ (.csv or .parquet)
    clustering: tuple[str, ...] = field(default_factory=tuple)
    column_renames: dict[str, str] = field(default_factory=dict)
    post_read: Optional[Callable] = None   # optional df→df transform applied after reading clean_file

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.clean_file


def _ncst_dtypes(df):
    """NCST clean is a CSV; apply the canonical dtypes before writing parquet."""
    from codemaps.ncst.shared import apply_dtypes
    return apply_dtypes(df)


TABLES: list[Table] = [
    Table(
        bq_name="dakshana_fact_ncst_results",
        parquet="dakshana_fact_ncst_results.parquet",
        clean_file="ncst_clean.csv",
        post_read=_ncst_dtypes,
    ),
    Table(
        bq_name="dakshana_fact_reported_results",
        parquet="dakshana_fact_reported_results.parquet",
        clean_file="dakshana_fact_reported_results.parquet",
        clustering=("test_year", "exam"),
    ),
]


# ── Raw artifacts (staged to GCS raw/ for audit) ──────────────────────────────

@dataclass(frozen=True)
class RawFile:
    """A raw source artifact staged under GCS raw/. Two modes:
       - sheet set   → read that Excel sheet and write it as parquet (NCST per-year files)
       - sheet None  → upload the local file unchanged (reported CSVs)
    """
    local_rel: str            # path under raw/
    gcs_subdir: str           # subdir under raw/ on GCS, incl. trailing slash (e.g. "ncst/")
    sheet: Optional[str] = None

    @property
    def local_path(self) -> Path:
        return RAW / self.local_rel

    @property
    def gcs_path(self) -> str:
        if self.sheet is not None:  # Excel → parquet: normalise the stem
            stem = Path(self.local_rel).stem.lower().replace(" ", "_")
            return f"{GCS_PREFIX}/raw/{self.gcs_subdir}{stem}.parquet"
        return f"{GCS_PREFIX}/raw/{self.gcs_subdir}{Path(self.local_rel).name}"


RAW_FILES: list[RawFile] = [
    # NCST per-year Excel exports → parquet
    RawFile("NCST 2022.xlsx", "ncst/", sheet="NCST2022 Full Data"),
    RawFile("NCST 2023.xlsx", "ncst/", sheet="NCST 2023"),
    RawFile("NCST 2024.xlsx", "ncst/", sheet="Result"),
    RawFile("NCST 2025.xlsx", "ncst/", sheet="All"),
    # Dakshana self-reported sheets → kept as-is for audit
    RawFile("reported/Dakshana - JEE-NEET 2025_Result_NVS_16.06.2025.xlsx - JEE Main.csv", "reported/"),
    RawFile("reported/Dakshana - 2025- NEET.csv", "reported/"),
]
