"""
JNU UG admission (CUET) cut-offs — source configuration.

Source: JNU's 2025-26 cut-off page (jnuee.jnu.ac.in/JNUCutoff2025.html):
four B.A. (Hons.) foreign-language merit lists, each with a Code-1 and a
Code-2 table, plus the Admission Policy (merit = total CUET marks of the
required papers, converted to 100) and the UG e-Prospectus (required papers:
English 101 + General Aptitude Test 501).

GCS layout:
    gs://avantifellows-external-data/jnuug/raw/<file>
    gs://avantifellows-external-data/jnuug/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"
YEAR = 2025

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "jnuug"
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str
    role: str                # list / rules / excluded
    list_no: int | None = None
    note: str = ""

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"


_B = "https://jnuee.jnu.ac.in/2024/"
RAW_FILES = [
    RawFile("BA_list1_cutoff_2025.pdf", _B + "BA_list1_cutoff_2025.pdf", "list", 1),
    RawFile("BA_list2_cutoff_2025_07_08.pdf", _B + "BA_list2_cutoff_2025_07_08.pdf", "list", 2),
    RawFile("BA_list3_cutoff_2025_03.pdf", _B + "BA_list3_cutoff_2025_03.pdf", "list", 3),
    RawFile("BA_list4_cutoff_15_09_25.pdf", _B + "BA_list4_cutoff_15_09_25.pdf", "list", 4),
    RawFile("BA_COP_defence_JK_Covid_revised_2025_08_08_2025.pdf",
            _B + "BA_COP_defence_JK_Covid_revised_2025_08_08_2025.pdf", "excluded",
            note="supernumerary defence / J&K / Covid-orphan quotas"),
    RawFile("AdmissionPolicy2025-26.pdf",
            "https://www.jnu.ac.in/sites/default/files/admission/AdmissionPolicy2025-26.pdf", "rules",
            note="3.2: UG merit = total CUET CBT marks converted into 100 marks"),
    RawFile("e-Prospectus-UG-COP-2025-26.pdf",
            "https://www.jnu.ac.in/sites/default/files/admission/e-Prospectus-UG-COP-2025-26.pdf", "rules",
            note="B.A. (Hons.) foreign languages: English (101) + GAT (501); Code-I / Code-II seats"),
]

# programme code in the lists -> programme
PROGRAMS = {
    "ARAU": "B.A. (Hons.) Arabic", "CHIU": "B.A. (Hons.) Chinese",
    "FREU": "B.A. (Hons.) French", "GRMU": "B.A. (Hons.) German",
    "JPNU": "B.A. (Hons.) Japanese", "KRNU": "B.A. (Hons.) Korean",
    "PASU": "B.A. (Hons.) Pashto", "PRNU": "B.A. (Hons.) Persian",
    "RUSU": "B.A. (Hons.) Russian", "SPAU": "B.A. (Hons.) Spanish",
}


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
    def local_path(self) -> Path:
        return CLEAN / self.parquet

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"


TABLES = [Table("jnuug_fact_cutoffs", "jnuug_fact_cutoffs.parquet",
                "(list_no, seat_code, program, category)")]
