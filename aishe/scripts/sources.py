"""
AISHE source configuration — the single source of truth.

Everything downstream (clean_aishe.py, build_institution_directory.py,
upload_to_gcs.py, load_bq.py) reads from here.

Two pipelines:

1. Higher-ed students (aishe_fact_higher_ed_students)
   Student enrolment + graduates from AISHE Final Report workbooks (Tables 33,
   34a, 12+35). Parsed by clean_aishe.py.

2. Institution directory (aishe_dim_colleges, aishe_dim_universities, etc.)
   Live registry of all HE institutions downloaded from the AISHE HE Directory
   dashboard (dashboard.aishe.gov.in/hedirectory). Parsed by
   build_institution_directory.py. One row per institution.

GCS layout:
    aishe/raw/<year>/<sheet>.parquet   — Final Report raw sheets (traceability)
    aishe/raw/institution_directory/   — Institution directory raw xlsx files
    aishe/clean/<table>.parquet        — loaded to BQ
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source Final Report workbooks (.xlsx, gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)
CODEMAPS = ROOT / "codemaps"

SENTINEL = "All"          # dimension value for "not broken out on this cut"

# ─── Raw source workbooks (gitignored; fetched from the URLs below by fetch.py) ─
REPORTS: dict[str, Path] = {
    "2019-20": RAW / "aishe_2019-20_final_report.xlsx",
    "2020-21": RAW / "aishe_2020-21_final_report.xlsx",
    "2021-22": RAW / "aishe_2021-22_final_report.xlsx",
}
LATEST_YEAR = "2021-22"  # the state×level and programme×social cuts are 2021-22 only

# Canonical source URLs — AISHE Final Report workbooks, he.nic.in (MoE). fetch.py
# downloads these into raw/ so the source files are regenerable from scratch.
_AISHE = "https://he.nic.in/aishereport/assets/excel"
REPORT_URLS: dict[str, str] = {
    "2019-20": f"{_AISHE}/AISHE%20Final%20Report%202019-20.xlsx",
    "2020-21": f"{_AISHE}/AISHE%20Final%20Report%202020-21.xlsx",
    "2021-22": f"{_AISHE}/AISHE%20Final%20Report%202021-22.xlsx",
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "aishe"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Clean table (parsed → GCS clean/ → loaded to BQ) ─────────────────────────
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
    # ── Pipeline 1: higher-ed students (from Final Report workbooks) ───────────
    Table(
        bq_name="aishe_fact_higher_ed_students",
        parquet="higher_ed.parquet",
        grain="(cut, aishe_year, metric, level, state, discipline, programme, social_category, gender)",
    ),
    # ── Pipeline 2: institution directory (from HE Directory dashboard xlsx) ───
    Table(
        bq_name="aishe_dim_colleges",
        parquet="aishe_dim_colleges.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_universities",
        parquet="aishe_dim_universities.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_standalone_institutions",
        parquet="aishe_dim_standalone_institutions.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_research_institutions",
        parquet="aishe_dim_research_institutions.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_pm_vidyalaxmi_eligible_institutions",
        parquet="aishe_dim_pm_vidyalaxmi_eligible_institutions.parquet",
        grain="(aishe_code)",
    ),
]

# Convenience lookups
TABLE_BY_NAME: dict[str, Table] = {t.bq_name: t for t in TABLES}


# ─── Institution directory — per-table config for build_institution_directory.py ─
# Separate dataclass because these tables have xlsx-specific fields (raw filename,
# header row, column renames) that the higher-ed pipeline doesn't need.

@dataclass(frozen=True)
class DirectoryTable:
    bq_name: str                          # must match a bq_name in TABLES
    raw_file: str                         # xlsx filename under raw/institution_directory/
    header_row: int                       # 0-based row of the column header in the xlsx
    column_renames: dict[str, str]        # raw Excel header → snake_case BQ column name

    @property
    def raw_path(self) -> Path:
        return RAW / "institution_directory" / self.raw_file

    @property
    def clean_path(self) -> Path:
        return CLEAN / f"{self.bq_name}.parquet"


COLLEGES_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "State": "state",
    "District": "district",
    "Website": "website",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "College Type": "college_type",
    "Manegement": "management",
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
    "University Type": "university_type",
}

STANDALONE_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "Web Url": "website",
    "State": "state",
    "District": "district",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "Standalone Type": "standalone_type",
    "Manegement": "management",
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

DIRECTORY_TABLES: list[DirectoryTable] = [
    DirectoryTable(
        bq_name="aishe_dim_colleges",
        raw_file="College-ALL COLLEGE.xlsx",
        header_row=2,
        column_renames=COLLEGES_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_universities",
        raw_file="University-ALL UNIVERSITIES.xlsx",
        header_row=2,
        column_renames=UNIVERSITIES_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_standalone_institutions",
        raw_file="Standalone-ALL_STANDALONE_with_URLs.xlsx",
        header_row=2,
        column_renames=STANDALONE_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_research_institutions",
        raw_file="R & D Institutes.xlsx",
        header_row=2,
        column_renames=RD_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_pm_vidyalaxmi_eligible_institutions",
        raw_file="vidya_lakshmiAll.xlsx",
        header_row=2,
        column_renames=PM_VIDYALAXMI_RENAMES,
    ),
]

DIRECTORY_TABLE_BY_NAME: dict[str, DirectoryTable] = {t.bq_name: t for t in DIRECTORY_TABLES}

# Institution directory raw Excel files — for upload_to_gcs.py
INSTITUTION_DIRECTORY_RAW_FILES: list[str] = [t.raw_file for t in DIRECTORY_TABLES]

# ─── Raw sheets (uploaded to GCS raw/ as parquet for traceability; NOT in BQ) ──
@dataclass(frozen=True)
class RawSheet:
    year: str
    sheet: str

    @property
    def workbook(self) -> Path:
        return REPORTS[self.year]

    @property
    def stem(self) -> str:
        return self.sheet.replace(" ", "").lower()

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.year}/{self.stem}.parquet"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


# The source sheets the fact is built from: 2021-22 carries all cuts; 2019-20 /
# 2020-21 contribute the UG-discipline trend. Table 12 = UG enrolment by
# discipline, Table 35 = UG graduates by discipline (same layout).
RAW_SHEETS: list[RawSheet] = [
    RawSheet("2021-22", "33OutTurnState"),
    RawSheet("2021-22", "34a"),
    RawSheet("2021-22", "35UGDisc"),
    RawSheet("2021-22", "12UGDisc"),
    RawSheet("2020-21", "35UGDisc"),
    RawSheet("2020-21", "12UGDisc"),
    RawSheet("2019-20", "35UGDisc"),
    RawSheet("2019-20", "12UGDisc"),
]
