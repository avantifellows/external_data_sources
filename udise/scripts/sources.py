"""
UDISE+ source configuration — the single source of truth.

Everything downstream (clean_udise.py, upload_to_gcs.py, load_bq.py) reads from
here.

Source: UDISE+ Dashboard "Report 4000 — Enrolment by Location, School Category
and School Management for Each Class & Level of Education", AY 2024-25, exported
from the interactive dashboard at https://dashboard.udiseplus.gov.in/. The
dashboard has no static download URL (the report is generated on demand), so —
like PLFS — there is no fetch.py; the raw xlsx staged on GCS is the regenerable
source of record.

GCS layout (jnv/ convention):
    gs://avantifellows-external-data/udise/raw/<xlsx>          (traceability)
    gs://avantifellows-external-data/udise/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source xlsx (gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)

# Raw source workbook (gitignored; dashboard export — see module docstring).
SOURCE_XLSX = RAW / "udise_2024-25_enrolment.xlsx"
SHEET = "UDISE+"
ACADEMIC_YEAR = "2024-25"

# ─── DSP microdata (school level) — NOT YET INGESTED ──────────────────────────
# A second, much larger UDISE+ product, unrelated to the Report 4000 cross-tab
# above: per-school records from the Data Sharing Portal, downloaded by hand as one
# zip per file group per year. See docs/DSP_INGEST_PLAN.md before starting.
#
# Grain is ONE ROW PER SCHOOL, keyed on `pseudocode` — a pseudonymised school id
# that joins the four groups to each other. There is no school name and no UDISE
# code, so these cannot be linked to Avanti's own school lists, and there are no
# student-level records: school aggregates throughout, no PII.
#
# Size is the main constraint. The zips are ~754 MB across the two years and the
# enrolment CSV alone is 562 MB uncompressed — do not read one with a naive
# pandas.read_csv on a laptop. Nothing under raw/dsp/ is committed (.gitignore).
DSP_YEARS = ("2020-21", "2024-25")

# Group -> the CSV inside that group's zip. The zip filenames carry the year, the
# CSVs do not: "100_enr1.csv" is the same name in every edition.
DSP_GROUPS: dict[str, str] = {
    "enrolment_data_1": "100_enr1.csv",   # enrolment by class x gender (cpp..c12)
    "enrolment_data_2": "100_enr2.csv",   # continues the enrolment block
    "profile_data_1":   "100_prof1.csv",  # state/district/block, category, management
    "profile_data_2":   "100_prof2.csv",  # continues the profile block
    "teacher_data":     "100_tch.csv",    # teacher counts by sex/social group/qual
    "facility_data":    "100_fac.csv",    # building, classrooms, toilets, utilities
}


def dsp_zip(year: str, group: str) -> Path:
    """Path to a downloaded DSP zip, named as the portal produces them."""
    return RAW / "dsp" / year / f"{group}_All State_{year}.zip"


DSP_CODEBOOKS: dict[str, Path] = {
    year: ROOT / "docs" / f"DSP_Schema_{year}.pdf" for year in DSP_YEARS
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "udise"

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
        bq_name="udise_fact_enrolment",
        parquet="enrolment.parquet",
        grain="(academic_year, state, school_management, school_category, urban_rural, class_level, gender)",
    ),
]
