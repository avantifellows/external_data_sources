"""
CUET (UG) merit rules — source configuration, the single source of truth.

Universities that admit on CUET (UG) don't use one CUET total: each course
adds up its own papers (DU B.Sc. Physics: Physics + Chemistry + Maths; BHU
B.A.: English or Hindi + GAT). NTA reports one normalized score per paper
(out of 250); a course's merit score is the sum of the papers its rule
counts. The rules are read from each university's own bulletin
(scripts/rules.py, with the page they come from) and joined to the course
strings of that university's cutoff fact.

Raw: the bulletins as published.
Course strings: the clean facts of the cutoff sources (ducuet, bhuug, allahabadug),
fetched from GCS.

GCS layout:
    gs://avantifellows-external-data/cuet/raw/<file>
    gs://avantifellows-external-data/cuet/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"

YEAR = 2025  # the 2025-26 admission

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "cuet"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"


@dataclass(frozen=True)
class RawFile:
    name: str
    university: str
    url: str  # where the university publishes it

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


RAW_FILES = [
    RawFile("du_ug_bulletin_2025.pdf", "DU",
            "https://www.du.ac.in/uploads/07032025_UG-BOI_compressed.pdf"),
    RawFile("bhu_ug_cuet_eligibility_2025.pdf", "BHU",
            "https://www.bhu.ac.in/Images/files/BHU_UG_CUET_Program_Course_Eligibility_Criteria_2025.pdf"),
    # Allahabad: the merit papers per programme; the cut-off notices
    # (allahabadug/raw) repeat them, with the domain lists for B.Sc. Biology
    # and B.Com
    RawFile("allahabad_ug_guidelines_2025.pdf", "ALD",
            "https://allduniv.ac.in/upload/file_collection/GuidelinesEligibilityRevised.pdf"),
]
BULLETIN = {rf.university: rf for rf in RAW_FILES}


@dataclass(frozen=True)
class CutoffSource:
    """A cutoff fact whose course strings get a rule."""
    university: str
    gcs_path: str
    program_col: str
    score_col: str


CUTOFF_SOURCES = [
    CutoffSource("DU", "ducuet/clean/ducuet_fact_cutoffs.parquet",
                 "program_name", "min_allocation_score"),
    CutoffSource("BHU", "bhuug/clean/bhuug_fact_cutoffs.parquet",
                 "program", "min_score"),
    CutoffSource("ALD", "allahabadug/clean/allahabadug_fact_cutoffs.parquet",
                 "program", "cutoff"),
]


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


TABLES = [
    Table("cuet_dim_merit_rules", "cuet_dim_merit_rules.parquet", "(rule_id)"),
    Table("cuet_dim_program_rules", "cuet_dim_program_rules.parquet",
          "(university, program)"),
]
