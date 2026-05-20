"""
AISHE source configuration — the single source of truth.

Everything downstream (clean_aishe.py, upload_to_gcs.py, load_bq.py) reads
from here:
- where the raw Final Report workbooks live locally before parsing
- where the parsed parquet files are written before upload
- the canonical GCS bucket + prefix where raw + clean are staged
- the BQ destination project / dataset / table mapping

GCS layout (mirrors the jnv/ + nirf/ convention):
    gs://avantifellows-external-data/aishe/raw/<year>/<sheet>.parquet   (traceability)
    gs://avantifellows-external-data/aishe/clean/<table>.parquet        (loaded to BQ)

AISHE publishes one Final Report per academic year as an Excel workbook.
This pipeline parses the 2021-22 report (out-turn cuts) plus the 2019-20 →
2021-22 series (UG discipline panel) into the tables below. To refresh with
a newer report, drop the workbook into raw/ and re-run clean_aishe.py →
upload_to_gcs.py → load_bq.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source Final Report workbooks (.xlsx, gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)
CODEMAPS = ROOT / "codemaps"

# ─── Raw source workbooks (gitignored; re-downloadable — see README) ──────────
REPORTS: dict[str, Path] = {
    "2019-20": RAW / "aishe_2019-20_final_report.xlsx",
    "2020-21": RAW / "aishe_2020-21_final_report.xlsx",
    "2021-22": RAW / "aishe_2021-22_final_report.xlsx",
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "aishe"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Clean tables (parsed → GCS clean/ → loaded to BQ) ────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str                              # table in BQ (no project/dataset)
    parquet: str                              # filename in clean/ and on GCS
    grain: str                                # human description of the row grain

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
        bq_name="aishe_fact_outturn_state_level",
        parquet="outturn_state_level.parquet",
        grain="(aishe_year, state, level, gender)",
    ),
    Table(
        bq_name="aishe_fact_outturn_ug_discipline",
        parquet="outturn_ug_discipline.parquet",
        grain="(aishe_year, discipline, gender)",
    ),
    Table(
        bq_name="aishe_fact_outturn_programme_social_category",
        parquet="outturn_programme_social_category.parquet",
        grain="(aishe_year, programme, social_category, gender)",
    ),
    Table(
        bq_name="aishe_fact_outturn_discipline_social_category",
        parquet="outturn_discipline_social_category.parquet",
        grain="(aishe_year, discipline, social_category, gender)",
    ),
    Table(
        bq_name="aishe_dim_programme_discipline_map",
        parquet="programme_discipline_map.parquet",
        grain="(programme)",
    ),
    Table(
        bq_name="aishe_fact_ug_discipline_panel",
        parquet="ug_discipline_panel.parquet",
        grain="(aishe_year, metric, discipline, gender)",
    ),
    Table(
        bq_name="aishe_fact_ug_discipline_extrapolated",
        parquet="ug_discipline_extrapolated.parquet",
        grain="(target_year, metric, discipline, gender)",
    ),
]


# ─── Raw sheets (uploaded to GCS raw/ as parquet for traceability; NOT in BQ) ──
@dataclass(frozen=True)
class RawSheet:
    year: str                                 # key into REPORTS
    sheet: str                                # AISHE sheet name (space-insensitive)

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


# The source sheets the parser consumes. 2021-22 carries the out-turn cuts;
# all three years feed the UG-discipline panel (sheets 12UGDisc + 35UGDisc).
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
