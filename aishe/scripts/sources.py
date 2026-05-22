"""
AISHE source configuration — the single source of truth.

Everything downstream (clean_aishe.py, upload_to_gcs.py, load_bq.py) reads from
here.

One denormalized fact:
  aishe_fact_higher_ed — student ENROLMENT + GRADUATES (out-turn), unified across
  AISHE Tables 33 (graduates by state × level), 34a (graduates by programme ×
  social category), and 12 + 35 (UG enrolment + graduates by discipline,
  2019-20 → 2021-22). Each row is tagged with `cut` (the published slice) and
  `metric` (enrolment | graduates). Dimensions that don't apply to a given cut
  carry the sentinel "All" (as AISHE itself does with Total / All Categories).

Exploratory analysis (discipline × social-category rollup, 2025-26 projection,
discipline → wage-bucket grouping) runs locally / lives in bq-assistant analysis
intents — not in this repo. The programme→discipline codemap stays a committed
CSV in codemaps/.

GCS layout (mirrors the jnv/ convention):
    gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet   (traceability)
    gs://avantifellows-external-data/aishe/clean/<table>.parquet        (loaded to BQ)
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
    Table(
        bq_name="aishe_fact_higher_ed",
        parquet="higher_ed.parquet",
        grain="(cut, aishe_year, metric, level, state, discipline, programme, social_category, gender)",
    ),
]


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
