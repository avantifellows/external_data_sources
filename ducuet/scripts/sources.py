"""
DU CUET UG cutoffs source configuration — the single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here:
- where the raw round-wise PDFs live locally before parsing
- where the parsed parquet is written before upload
- the canonical GCS bucket + prefix where raw + clean are staged
- the BQ destination project / dataset / table mapping

Source: University of Delhi Admission Branch, "Undergraduate Admissions
2025-26" minimum-allocation-score PDFs, one per CSAS/CUET allocation round
(Round 1, Round 2, Round 3). Not published as a combined file — each round's
PDF is the University's live per-program minimum score for that round only,
and rounds are NOT cumulative (a college can quote a lower score in a later
round as it reallocates vacant seats).

GCS layout (mirrors the moe/ convention):
    gs://avantifellows-external-data/ducuet/raw/<pdf>          (traceability)
    gs://avantifellows-external-data/ducuet/clean/<table>.parquet  (loaded to BQ)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source DU round PDFs (gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)

# ─── Raw source PDFs (gitignored) ──────────────────────────────────────────
# Not fetched programmatically — DU publishes these as one-off PDFs on the
# admission branch's admission bulletin page with no stable canonical URL per
# round; download manually from https://admission.uod.ac.in/ and drop here.
ROUNDS: dict[int, Path] = {
    1: RAW / "du_cuet_ug_2025_r1.pdf",
    2: RAW / "du_cuet_ug_2025_r2.pdf",
    3: RAW / "du_cuet_ug_2025_r3.pdf",
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "ducuet"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Clean tables (parsed → GCS clean/ → loaded to BQ) ────────────────────────
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
        bq_name="ducuet_fact_cutoffs",
        parquet="ducuet_fact_cutoffs.parquet",
        grain="(college_name, program_name, category)",
    ),
]


# ─── Raw PDFs (uploaded to GCS raw/ as-is for traceability; NOT loaded to BQ) ──
@dataclass(frozen=True)
class RawFile:
    round_no: int

    @property
    def local_path(self) -> Path:
        return ROUNDS[self.round_no]

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.local_path.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


RAW_FILES: list[RawFile] = [RawFile(r) for r in ROUNDS]

# Flat filenames, for build_clean.py's fetch-from-GCS-if-missing-locally step
# (the canonical home for the raw PDFs is GCS, not this machine's raw/).
RAW_FILENAMES: list[str] = [p.name for p in ROUNDS.values()]
