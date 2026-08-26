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

# ─── DSP microdata (school level) ─────────────────────────────────────────────
# A second, much larger UDISE+ product, unrelated to the Report 4000 cross-tab
# above: per-school records from the Data Sharing Portal, downloaded by hand as one
# zip per file group per year. See docs/DSP_INGEST_PLAN.md for the domain notes.
#
# Grain is ONE ROW PER SCHOOL, keyed on `pseudocode` — a pseudonymised school id
# that joins the file groups to each other. There is no school name and no UDISE
# code, so these cannot be linked to Avanti's own school lists, and there are no
# student-level records: school aggregates throughout, no PII.
#
# Size is the main constraint: ~1.7 GB of zips across the five years, ~12 GB of CSV
# uncompressed, and the 2025-26 enrolment_data_2 CSV alone is 1.17 GB. Nothing is
# ever read with a naive pandas.read_csv — scripts/dsp_stage.py streams each member
# straight out of its zip into gzip, into GCS, into a BigQuery staging table, and
# every reshape happens in SQL (scripts/dsp_build_bq.py).
#
# Nothing under raw/dsp/ is committed (.gitignore).
DSP_YEARS = ("2020-21", "2022-23", "2023-24", "2024-25", "2025-26")

# Group -> the CSV inside that group's zip, for the 2022-23 onward editions. The
# zip filenames carry the year, the CSVs do not: "100_enr1.csv" is the same name in
# every edition from 2022-23 on.
DSP_GROUPS: dict[str, str] = {
    "enrolment_data_1": "100_enr1.csv",   # enrolment by class x gender x item (social cat, religion, BPL, EWS, CWSN…)
    "enrolment_data_2": "100_enr2.csv",   # continues the enrolment block (age distribution)
    "profile_data_1":   "100_prof1.csv",  # state/district/block, category, management
    "profile_data_2":   "100_prof2.csv",  # continues the profile block (entitlements, SMC, grants)
    "teacher_data":     "100_tch.csv",    # teacher counts by sex/social group/qual
    "facility_data":    "100_fac.csv",    # building, classrooms, toilets, utilities
    "safety":           "100_safety.csv", # 2025-26 only: SDMP, CCTV, fire, self-defence
}

# Not every group exists in every year.
DSP_GROUP_YEARS: dict[str, tuple[str, ...]] = {
    g: (DSP_YEARS if g != "safety" else ("2025-26",)) for g in DSP_GROUPS
}

# The 2020-21 edition predates the "100_*" naming AND shards the two enrolment
# files by state — six CSVs each, same header, disjoint schools. The member paths
# below are the exact names inside those zips.
_E1_2020 = "21-100_enr1/nationalEnrol1"
DSP_MEMBERS_2020_21: dict[str, tuple[str, ...]] = {
    "enrolment_data_1": tuple(
        f"{_E1_2020}{suffix}.csv"
        for suffix in ("", "_AP_KA_TN_TL", "_AS_WB", "_MH_MP", "_OD_RJ_BR", "_UP")
    ),
    "enrolment_data_2": tuple(
        f"nationalEnrol2{suffix}.csv"
        for suffix in ("", "_AP_KA_TN_TL", "_AS_WB", "_MH_MP", "_OD_RJ_BR", "_UP")
    ),
    "profile_data_1": ("nationalProfile_1.csv",),
    "profile_data_2": ("nationalProfile_2.csv",),
    "teacher_data":   ("nationalTeacher.csv",),
    "facility_data":  ("nationalfacility.csv",),
}

# 2020-21's enrolment_data_1 zip also carries 21-100_enr1/NationalStreamEnrolment.csv
# (pseudocode, stream, caste, c11b..c12g) — a class 11/12 stream x caste cut that no
# other edition publishes. Deliberately NOT staged: it is a different grain from the
# item_group fact and would need its own table. Left for a follow-up.
DSP_UNSTAGED_2020_21 = ("21-100_enr1/NationalStreamEnrolment.csv",)


def dsp_zip(year: str, group: str) -> Path:
    """Path to a downloaded DSP zip, named as the portal produces them."""
    return RAW / "dsp" / year / f"{group}_All State_{year}.zip"


def dsp_members(year: str, group: str) -> tuple[str, ...]:
    """The CSV member path(s) to read out of that year's zip for that group."""
    if year == "2020-21":
        return DSP_MEMBERS_2020_21[group]
    return (DSP_GROUPS[group],)


def dsp_staging_table(year: str, group: str) -> str:
    """Fully-qualified BQ staging table for one (year, group). Transient."""
    return f"{BQ_PROJECT}.{DSP_STAGING_DATASET}.{group}_{year.replace('-', '_')}"


DSP_CODEBOOKS: dict[str, Path] = {
    "2020-21": ROOT / "docs" / "DSP_Schema_2020-21.pdf",
    "2024-25": ROOT / "docs" / "DSP_Schema_2024-25.pdf",
    # 2025-26 ships its codebook inside raw/dsp/2025-26/ (gitignored); the
    # 2024-25 book still describes every column the 2025-26 edition shares.
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "udise"

# DSP staging prefixes. `raw/dsp/` holds the untouched portal zips (the source of
# record — the portal has no static download URL). `staging/dsp/` holds the same
# CSVs re-containered zip -> gzip purely so BigQuery can load them; it is
# regenerable from raw and safe to delete once the BQ tables are built.
GCS_DSP_RAW = f"{GCS_PREFIX}/raw/dsp"
GCS_DSP_STAGING = f"{GCS_PREFIX}/staging/dsp"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"

# Transient dataset holding one raw, unreshaped table per (year, file group). It
# exists only between dsp_stage.py and dsp_build_bq.py; the finished tables land in
# BQ_DATASET. Created with a default table expiry so a half-finished run cleans up
# after itself, and dropped explicitly by `dsp_build_bq.py --drop-staging`.
DSP_STAGING_DATASET = "udise_dsp_staging"
DSP_STAGING_EXPIRY_DAYS = 14


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
