"""
AISHE source configuration — the single source of truth.

Everything downstream (clean_aishe.py, upload_to_gcs.py, load_bq.py, analyses/)
reads from here.

One denormalized fact (see analyses/README.md for the questions that drive it):
  aishe_fact_outturn — out-turn (graduates) unified across AISHE Tables 33
  (state × level), 34a (programme × social category), and 35 (UG discipline,
  2019-20 → 2021-22). Dimensions that don't apply to a given source cut carry
  the sentinel "All" (as AISHE itself does with Total / All Categories).

Derived cuts (discipline × social-category rollup, 2025-26 projection) live in
analyses/, not as tables. The programme→discipline codemap stays a committed
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

# ─── Raw source workbooks (gitignored; re-downloadable — see README) ──────────
REPORTS: dict[str, Path] = {
    "2019-20": RAW / "aishe_2019-20_final_report.xlsx",
    "2020-21": RAW / "aishe_2020-21_final_report.xlsx",
    "2021-22": RAW / "aishe_2021-22_final_report.xlsx",
}
OUTTURN_YEAR = "2021-22"  # the state×level and programme×social cuts are 2021-22

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
        bq_name="aishe_fact_outturn",
        parquet="outturn.parquet",
        grain="(aishe_year, level, state, discipline, programme, social_category, gender)",
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


# The source sheets the fact is built from: 2021-22 carries all three cuts;
# 2019-20 / 2020-21 contribute the UG-discipline out-turn (35UGDisc) for trend.
RAW_SHEETS: list[RawSheet] = [
    RawSheet("2021-22", "33OutTurnState"),
    RawSheet("2021-22", "34a"),
    RawSheet("2021-22", "35UGDisc"),
    RawSheet("2020-21", "35UGDisc"),
    RawSheet("2019-20", "35UGDisc"),
]
