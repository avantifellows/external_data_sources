"""
JoSAA source configuration — the single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here:
- where the raw per-(year, round) CSVs land locally before upload
- where the clean parquet is written
- the canonical GCS bucket + prefix where both are staged
- the BQ destination project / dataset / table mapping
- the raw-CSV → BQ column rename map

When JoSAA publishes a new counselling cycle, the upstream scraper in the
College DB repo (josaa-ranks/scripts/01_scrape_archive.py +
02_scrape_current.py) writes the new per-(year, round) CSVs. Drop them into
josaa/raw/ (filename pattern `<year>_R<round>.csv`), then re-run
build_clean.py + upload_to_gcs.py + load_bq.py. Overwrite-in-place is
intentional: JoSAA data is additive (a new cycle appends rows; historical
cycles are frozen once the portal archives them).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"                            # per-(year, round) CSVs (gitignored)
CLEAN = ROOT / "clean"                        # clean parquet (gitignored)

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "josaa"                          # gs://{bucket}/{prefix}/{raw,clean}/

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"          # asia-south1
BQ_LOCATION = "asia-south1"

# ─── Raw → clean column rename (JoSAA portal headers → snake_case) ───────────
COLUMN_RENAMES = {
    "Institute":              "institute",
    "Academic Program Name":  "academic_program_name",
    "Quota":                  "quota",
    "Seat Type":              "seat_type",
    "Gender":                 "gender",
    "Opening Rank":           "opening_rank",
    "Closing Rank":           "closing_rank",
    "Year":                   "year",
    "Round":                  "round",
}


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str                              # table in BQ (no project/dataset)
    parquet: str                              # filename in clean/ and on GCS
    clustering_fields: list[str] = field(default_factory=list)

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet


TABLES: list[Table] = [
    Table(
        bq_name="josaa_fact_cutoffs",
        parquet="josaa_fact_cutoffs.parquet",
        clustering_fields=["year", "round", "seat_type"],
    ),
]
