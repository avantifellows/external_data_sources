"""
Gujarat medical, dental, AYUSH, nursing and allied admissions (ACPMEC) —
source configuration, the single source of truth.

Source: medadmgujarat.org, the portal of Gujarat's admission committees
for professional medical courses. Two committees publish the institute
lists used here, for the 2026-27 admission cycle:

  - Admission Committee for Professional Undergraduate Medical Educational
    Courses (NEET-based): BDS seat matrix, BAMS (Ayurveda) and BHMS
    (Homoeopathy) colleges with intake and fees.
  - Admission Committee for Gujarat Professional Nursing and Allied Medical
    Educational Courses: one institute file per course (B.Sc. Nursing,
    Physiotherapy, Optometry, Occupational Therapy, Prosthetics & Orthotics,
    Audiology & Speech-Language Pathology, Naturopathy & Yoga) with intake
    and fees.

MBBS is not here: the colleges tab already lists every MBBS college from the
NMC (nmc_fact_mbbs_seats). GNM / ANM (nursing diplomas) are not here: they
are not degree courses.

GCS is the canonical raw source — build_clean.py fetches missing files.

GCS layout:
    gs://avantifellows-external-data/acpmec/raw/<file>
    gs://avantifellows-external-data/acpmec/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

ACADEMIC_YEAR = "2026-27"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "acpmec"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"

PORTAL = "http://medadmgujarat.ncode.in/web"


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str          # where the committee publishes it
    kind: str         # which parser reads it
    course: str | None = None

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


def _nursing(code: str, file_code: str) -> RawFile:
    return RawFile(f"nur_inst_{file_code.replace(' ', '_')}_2026-27.pdf",
                   f"{PORTAL}/NUR2026/INST-FILES-WEB/{file_code} 2026-27.PDF",
                   "nursing_allied", code)


RAW_FILES = [
    RawFile("dental_seat_matrix_2026-27.pdf",
            f"{PORTAL}/UG2026/R1/Seat Matrix Dental 2026-27.pdf", "dental", "BDS"),
    RawFile("ayurved_intake_fees_2026-27.pdf",
            f"{PORTAL}/UG2026/UGAYUSH/List of Ayurvedic Colleges with Intake & Fees 2026-27.pdf",
            "ayush", "BAMS"),
    RawFile("homoeo_intake_fees_2026-27.pdf",
            f"{PORTAL}/UG2026/UGAYUSH/List of Homoeopathic Colleges with Intake & Fees 2026-27.pdf",
            "ayush", "BHMS"),
    _nursing("BSC_NURSING", "BSC GOV"),
    _nursing("BSC_NURSING", "BSC SFI"),
    _nursing("BPT", "BPT"),
    _nursing("BO", "BO"),
    _nursing("BOT", "BOT"),
    _nursing("BOP", "BOP"),
    _nursing("BASLP", "BASLP"),
    _nursing("BNYS", "BNYS"),
]

COURSE_NAMES = {
    "BDS": "Bachelor of Dental Surgery",
    "BAMS": "Bachelor of Ayurvedic Medicine and Surgery",
    "BHMS": "Bachelor of Homoeopathic Medicine and Surgery",
    "BSC_NURSING": "B.Sc. Nursing",
    "BPT": "Bachelor of Physiotherapy",
    "BO": "Bachelor of Optometry",
    "BOT": "Bachelor of Occupational Therapy",
    "BOP": "Bachelor of Prosthetics and Orthotics",
    "BASLP": "Bachelor of Audiology and Speech-Language Pathology",
    "BNYS": "Bachelor of Naturopathy and Yogic Sciences",
}

# which committee admits to the course
COMMITTEE = {
    "BDS": "ug_medical", "BAMS": "ug_medical", "BHMS": "ug_medical",
}  # everything else: "nursing_allied"


@dataclass(frozen=True)
class Table:
    name: str

    @property
    def parquet(self) -> str:
        return f"{self.name}.parquet"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.name}"


TABLES = [Table("acpmec_dim_institutes")]
