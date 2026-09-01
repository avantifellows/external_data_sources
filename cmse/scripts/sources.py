"""
Central config for the CMS-E pipeline scripts.

CMS-E = Comprehensive Modular Survey: Education, NSS 80th Round (April–June 2025),
published by MoSPI/NSO. Unit-level microdata: three fixed-width text files, released
by MoSPI as CSV with readable column names.

GCS paths, BQ identifiers, table definitions and the official code lists all live here.

GCS layout:
    cmse/raw/<file>.csv          — the three MoSPI unit-level CSVs (audit trail)
    cmse/raw/docs/<file>         — the six official documentation files
    cmse/clean/<table>.parquet   — the bytes BigQuery loads
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"          # MoSPI unit-level CSVs (gitignored)
CLEAN = ROOT / "clean"      # parquet output (gitignored)
CODEMAPS = ROOT / "codemaps"
DOCS = ROOT / "docs"        # official MoSPI documentation (committed — public, small)

# ── GCS ───────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "cmse"

# ── BigQuery ──────────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"

# ── Survey identity ───────────────────────────────────────────────────────────
SURVEY_ROUND = "NSS 80th Round"
SURVEY_NAME = "Comprehensive Modular Survey: Education (CMS-E)"
SURVEY_YEAR = 2025
REFERENCE_PERIOD = "April–June 2025 (current academic year 2025-26)"
SOURCE_URL = "https://microdata.gov.in/NADA/index.php/catalog/255"
RETRIEVED = "2026-08-26"

# NSS weights are published multiplied by 100.
WEIGHT_DIVISOR = 100


# ── Raw inputs ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RawFile:
    """One MoSPI unit-level CSV, staged to GCS raw/ for audit."""
    filename: str
    grain: str

    @property
    def local_path(self) -> Path:
        return RAW / self.filename

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.filename}"


RAW_FILES = [
    RawFile("CMSE80HH25.csv", "household"),
    RawFile("CMSE80PER25.csv", "person (all household members)"),
    RawFile("CMSE80PERST25.csv", "erstwhile member studying away from home"),
]

# The six official MoSPI documentation files, staged alongside the data so the
# bucket carries everything needed to re-derive the tables from scratch.
DOC_FILES = [
    "Data_Layout_CMSE_2025.xlsx",
    "CODEs for Blocks of Sch - CMS-Education.xlsx",
    "README_CMSE_2025.docx",
    "Note_for_data_user - CMS-Education.docx",
    "Survey methodology and estimation procedure - CMS-Education.pdf",
    "NSO Volume I & II_80 - CMSE.pdf",
    "ddi_255.xml",
]


# ── Output tables ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Table:
    bq_name: str
    clustering_fields: tuple[str, ...]

    @property
    def local_path(self) -> Path:
        return CLEAN / f"{self.bq_name}.parquet"

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/clean/{self.bq_name}.parquet"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"


FACT_STUDENT = Table(
    bq_name="cmse_fact_student",
    # State and gender first: the two cuts this table exists to serve.
    clustering_fields=("state_code", "gender_name", "enrolment_level_code", "cut"),
)
FACT_HOUSEHOLD = Table(
    bq_name="cmse_fact_household",
    clustering_fields=("state_code", "sector_name", "social_group_name"),
)
# The ROSTER. Every surveyed household member the enrolment question was put to,
# enrolled or not — which is the only way to ask who is NOT in school. Kept as a
# separate table rather than folded into FACT_STUDENT because that table's grain
# is "one row per student" and its fourteen-figure reconciliation is written
# against it; widening it would move the grain other analyses already read.
FACT_PERSON = Table(
    bq_name="cmse_fact_person",
    # age_band and is_enrolled first: this table exists to compute an
    # out-of-school RATE within an age band, and that is the cut it serves.
    clustering_fields=("state_code", "age_band", "is_enrolled", "social_group_name"),
)

TABLES = [FACT_STUDENT, FACT_HOUSEHOLD, FACT_PERSON]


# ── Official code lists ───────────────────────────────────────────────────────
# Verbatim from "CODEs for Blocks of Sch - CMS-Education.xlsx" (blocks 1–5) and
# the "State code" sheet of Data_Layout_CMSE_2025.xlsx. Both are in docs/.
# build_codemaps.py regenerates the CSVs in codemaps/ from those files; these
# dicts are what the transform actually applies.

SECTOR = {1: "Rural", 2: "Urban"}

GENDER = {1: "Male", 2: "Female", 3: "Transgender"}

SOCIAL_GROUP = {
    1: "Scheduled Tribe (ST)",
    2: "Scheduled Caste (SC)",
    3: "Other Backward Class (OBC)",
    9: "Others",
}

RELIGION = {
    1: "Hinduism", 2: "Islam", 3: "Christianity", 4: "Sikhism",
    5: "Jainism", 6: "Buddhism", 7: "Zoroastrianism", 9: "Others",
}

# Household type is coded on DIFFERENT scales in rural and urban sectors —
# code 3 means "regular wage/salary in agriculture" in a rural household and
# "casual labour" in an urban one. Never decode without the sector.
HOUSEHOLD_TYPE_RURAL = {
    1: "Self-employed in agriculture",
    2: "Self-employed in non-agriculture",
    3: "Regular wage/salary earning in agriculture",
    4: "Regular wage/salary earning in non-agriculture",
    5: "Casual labour in agriculture",
    6: "Casual labour in non-agriculture",
    9: "Others",
}
HOUSEHOLD_TYPE_URBAN = {
    1: "Self-employed",
    2: "Regular wage/salary earning",
    3: "Casual labour",
    9: "Others",
}

RELATION_TO_HEAD = {
    1: "Self", 2: "Spouse of head", 3: "Married child",
    4: "Spouse of married child", 5: "Unmarried child", 6: "Grandchild",
    7: "Father/mother/father-in-law/mother-in-law",
    8: "Brother/sister/brother-in-law/sister-in-law/other relatives",
    9: "Servant/employees/other non-relatives",
}

ENROLMENT_LEVEL = {
    1: "Class I", 2: "Class II", 3: "Class III", 4: "Class IV", 5: "Class V",
    6: "Class VI", 7: "Class VII", 8: "Class VIII", 9: "Class IX", 10: "Class X",
    11: "Class XI", 12: "Class XII",
    13: "Diploma/certificate course (up to secondary)",
    14: "Diploma/certificate (higher secondary equivalent)",
    15: "Below Class I (pre-primary)",
}

# Derived rollup of ENROLMENT_LEVEL. Note code 15 sorts FIRST despite the
# highest number — it is pre-primary, not post-Class-XII.
ENROLMENT_STAGE = {
    15: "Pre-primary", 1: "Primary", 2: "Primary", 3: "Primary", 4: "Primary", 5: "Primary",
    6: "Upper primary", 7: "Upper primary", 8: "Upper primary",
    9: "Secondary", 10: "Secondary",
    11: "Higher secondary", 12: "Higher secondary",
    13: "Diploma/certificate", 14: "Diploma/certificate",
}

SCHOOL_TYPE = {
    1: "Government",
    2: "Government-aided (private school aided by government)",
    3: "Private unaided (recognised)",
    4: "Private unaided (unrecognised)",
    5: "Others",
}

FUNDING_SOURCE = {
    1: "Earnings of the student",
    2: "Other members of the household",
    3: "Erstwhile household members",
    4: "Gifts from friends/relatives",
    5: "Scholarship from school",
    6: "Scholarship from government",
    7: "Scholarship from charitable and other organisations",
    8: "Educational loan",
    10: "Other loan",
    19: "Others",
    99: "No second source of funding",
}

YES_NO = {1: "Yes", 2: "No"}

# Block 5 item 3, the enrolment gate. The transform reads THIS rather than
# inferring enrolment from a populated enrolment_level: checked against the raw
# file, the two row sets are identical (57,742 rows, symmetric difference 0), and
# reading the gate itself means a future MoSPI edit that separates them fails
# loudly instead of silently changing who counts as a student.
CURRENTLY_ENROLLED = {1: True, 2: False}

# Age bands for the roster. Chosen to line up with the schooling stages the
# survey covers — 3–5 pre-primary, 6–10 primary, 11–14 upper primary, 15–17
# secondary and higher secondary — so a band maps onto a real rung rather than a
# round decade.
#
# 18+ IS DELIBERATELY ONE UNDIFFERENTIATED PAIR OF BANDS, and is not school age.
# CMS-E covers school education only, so a non-enrolled 19-year-old may be in a
# degree programme, in work, or in neither, and this survey CANNOT tell the
# difference. An "out-of-school rate" computed on an 18+ band is therefore not a
# statement the data supports — hence the `is_school_age` column the transform
# derives from SCHOOL_AGE_MIN/MAX, which makes the supported denominator a single
# flag rather than a convention someone has to remember.
AGE_BANDS = [
    (3, 5, "3-5"),
    (6, 10, "6-10"),
    (11, 14, "11-14"),
    (15, 17, "15-17"),
    (18, 24, "18-24"),
    (25, 200, "25+"),
]
SCHOOL_AGE_MIN, SCHOOL_AGE_MAX = 3, 17

# Block 4 only (students living away from home).
RESIDENCE_TYPE = {1: "Students' hostel", 2: "Paying guest/mess", 3: "Others"}
PLACE_OF_RESIDENCE = {1: "Rural", 2: "Urban"}

# Non-reporting codes on the away-from-home expenditure items. These distinguish
# "we don't know the amount" from "it was free" — a blank is NOT a zero.
# Manual: Note 10, page C-16 of NSO Volume I.
NONREPORTING_SCHOOL = {1: "Amount reported", 2: "Not known"}
NONREPORTING_COACHING = {
    1: "Amount reported", 2: "Not known", 3: "Free tuition", 4: "No tuition",
}
NONREPORTING_BOARDING = {
    1: "Amount reported", 2: "Not known", 3: "Free boarding/lodging",
}


def load_state_map() -> dict[str, str]:
    """state_code (zero-padded 2-char string) -> state/UT name, from codemaps/."""
    import csv

    with open(CODEMAPS / "cmse_state.csv", newline="", encoding="utf-8") as fh:
        return {r["state_code"]: r["state_name"] for r in csv.DictReader(fh)}
