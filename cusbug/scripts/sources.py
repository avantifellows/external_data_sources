"""
Central University of South Bihar (CUSB, Gaya) UG admission (CUET) cut-offs
— source configuration, the single source of truth.

Source: CUSB's UG admission 2025-26 notices on its admissions page
(cusb.ac.in, article 751): six category-wise cut-off announcements, a
round-1 corrigendum, the eligibility annexure (which CUET papers each
programme counts) and a clarification that only those papers count. The
'provisionally admitted' lists on the same page name students and are not
downloaded.

roles: text (parsed), manual (scanned; extracted/manual_transcriptions.csv),
rules (eligibility / papers), excluded (with reason).

GCS layout:
    gs://avantifellows-external-data/cusbug/raw/<file>
    gs://avantifellows-external-data/cusbug/extracted/manual_transcriptions.csv
    gs://avantifellows-external-data/cusbug/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
CLEAN = ROOT / "clean"
YEAR = 2025

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "cusbug"
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"

MANUAL = EXTRACTED / "manual_transcriptions.csv"
MANUAL_GCS = f"{GCS_PREFIX}/extracted/manual_transcriptions.csv"
BASE = "https://www.cusb.ac.in/images/2025/admission_25/"


@dataclass(frozen=True)
class RawFile:
    name: str
    path: str          # under BASE
    role: str
    round: int | None = None
    note: str = ""

    @property
    def url(self) -> str:
        return BASE + self.path

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"


RAW_FILES = [
    RawFile("ug_1st_cut_off_ug.pdf", "ug/1st_cut_off_ug.pdf", "text", 1),
    RawFile("ug_2nd_cut_off.pdf", "ug/2nd_cut_off.pdf", "text", 2),
    RawFile("ug_3rd_round_ug.pdf", "ug/3rd_round_ug.pdf", "manual", 3, "scanned"),
    RawFile("ug_4th_round_ug.pdf", "ug/4th_round_ug.pdf", "text", 4),
    RawFile("ug_5th_cut_off_1.pdf", "ug/5th_cut_off_1.pdf", "text", 5),
    RawFile("ug_6th_cut_off_ug.pdf", "ug/6th_cut_off_ug.pdf", "manual", 6,
            "scanned; the page link reads '5th', the heading 'FIRST (6th)', the text 'sixth round'"),
    RawFile("ug_agri_corri.pdf", "ug/agri_corri.pdf", "manual", 1, "round-1 corrigendum (Agriculture PwD)"),
    RawFile("ug_rev_intake.pdf", "ug/rev_intake.pdf", "rules", note="Annexure I: CUET papers, eligibility, intake"),
    RawFile("ug_clearification_1.pdf", "ug/clearification_1.pdf", "rules",
            note="only the programme's specified papers count, never an aggregate"),
    RawFile("ug_adm_notification.pdf", "ug_adm/notification.pdf", "rules", note="admission notification"),
    RawFile("ug_spot_round_spot_ug_not.pdf", "ug/spot_round/spot_ug_not.pdf", "excluded",
            note="spot round: offline, no cut-off scores"),
    RawFile("ug_spot_round_ann_ug_s_1.pdf", "ug/spot_round/ann_ug_s_1.pdf", "excluded", note="= Annexure I"),
    RawFile("ug_spot_round_ann_ug_s_2.pdf", "ug/spot_round/ann_ug_s_2.pdf", "excluded", note="fee table"),
    RawFile("ug_spot_round_ann_ug_s_3.pdf", "ug/spot_round/ann_ug_s_3.pdf", "excluded", note="spot round form annexure"),
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


TABLES = [Table("cusbug_fact_cutoffs", "cusbug_fact_cutoffs.parquet",
                "(round, program, category, source_file)")]
