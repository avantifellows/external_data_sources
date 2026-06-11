"""
AISHE HE Directory — source configuration.

Single source of truth for file names, GCS paths, and BQ destinations.
Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here.

Source: https://dashboard.aishe.gov.in/hedirectory/#/hedirectory

The five Excel files are downloaded manually from the AISHE dashboard
(each tab has an "Export" button). Drop them into aishe/raw/ using the
canonical names below, then run the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "aishe"  # gs://{bucket}/{prefix}/clean/*.parquet

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"  # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str          # BQ table name (no project/dataset prefix)
    raw_file: str         # Excel filename in raw/  (as downloaded from dashboard)
    parquet: str          # clean parquet filename in clean/  and on GCS
    header_row: int       # 0-based row index of the column header in the Excel
    column_renames: dict[str, str] = field(default_factory=dict)

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def raw_path(self) -> Path:
        return RAW / self.raw_file

    @property
    def clean_path(self) -> Path:
        return CLEAN / self.parquet


# Column renames: raw Excel header → canonical snake_case BQ column name.
# Applied in build_clean.py so both the parquet and the BQ table use the
# canonical names.

COLLEGES_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "State": "state",
    "District": "district",
    "Website": "website",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "College Type": "college_type",
    "Manegement": "management",          # source has a typo ("Manegement")
    "University Aishe Code": "university_aishe_code",
    "University Name": "university_name",
    "University Type": "university_type",
}

UNIVERSITIES_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "State": "state",
    "District": "district",
    "Website": "website",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
}

STANDALONE_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "State": "state",
    "District": "district",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "Standalone Type": "standalone_type",
    "Manegement": "management",          # source has a typo
}

RD_RENAMES = {
    "S. No.": "sno",
    "AISHE Code": "aishe_code",
    "Institute Name": "institute_name",
    "State Name": "state_name",
    "District Name": "district_name",
    "Administrative Ministry": "administrative_ministry",
}

PM_VIDYALAXMI_RENAMES = {
    "S. No.": "sno",
    "AISHE Code": "aishe_code",
    "Institute Name": "institute_name",
    "State Name": "state_name",
    "Management Type": "management_type",
}

TABLES: list[Table] = [
    Table(
        bq_name="aishe_fact_colleges",
        raw_file="College-ALL COLLEGE (1).xlsx",
        parquet="aishe_fact_colleges.parquet",
        header_row=2,  # rows 0-1 are title/date; row 2 is the header
        column_renames=COLLEGES_RENAMES,
    ),
    Table(
        bq_name="aishe_fact_universities",
        raw_file="University-ALL UNIVERSITIES (1).xlsx",
        parquet="aishe_fact_universities.parquet",
        header_row=2,
        column_renames=UNIVERSITIES_RENAMES,
    ),
    Table(
        bq_name="aishe_fact_standalone",
        raw_file="Standalone-ALL STANDALONE.xlsx",
        parquet="aishe_fact_standalone.parquet",
        header_row=2,
        column_renames=STANDALONE_RENAMES,
    ),
    Table(
        bq_name="aishe_fact_rd",
        raw_file="R & D Institutes.xlsx",
        parquet="aishe_fact_rd.parquet",
        header_row=2,
        column_renames=RD_RENAMES,
    ),
    Table(
        bq_name="aishe_fact_pm_vidyalaxmi",
        raw_file="vidya_lakshmiAll.xlsx",
        parquet="aishe_fact_pm_vidyalaxmi.parquet",
        header_row=2,
        column_renames=PM_VIDYALAXMI_RENAMES,
    ),
]

# Convenience lookup: bq_name → Table
TABLE_BY_NAME: dict[str, Table] = {t.bq_name: t for t in TABLES}
