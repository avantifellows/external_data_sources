"""
NIRF source configuration — the single source of truth.

Everything downstream (build_clean.py, upload_to_gcs.py, load_bq.py) reads
from here:
- where the raw parquet files land locally
- where build_clean.py writes the clean parquets
- the canonical GCS bucket + prefix where they're staged
- the BQ destination project / dataset / table mapping
- the documented grain of each table (used by build_clean.py to deduplicate)
- per-table column rename maps (source col → BQ-friendly name)

GCS layout (matches the repo convention — raw/ for traceability, clean/ for BQ):
  gs://avantifellows-external-data/nirf/raw/<parquet>     the Dataful-derived inputs
  gs://avantifellows-external-data/nirf/clean/<parquet>   what load_bq.py loads

Pipeline:
  gs://…/nirf/raw/*.parquet  →  raw/*.parquet  →  build_clean.py  →  clean/*.parquet
                                                                          │  upload_to_gcs.py
                                                                          ▼
                                       gs://avantifellows-external-data/nirf/clean/*.parquet
                                                                          │  load_bq.py
                                                                          ▼
                                       avantifellows.external_data_sources.nirf_fact_*

When NIRF publishes new data, replace the parquet files in nirf/raw/ with the
same filenames and re-run build_clean.py + upload_to_gcs.py + load_bq.py.
Overwrite-in-place is intentional: NIRF data is mostly additive (new year
appends rows; historical years rarely change), and BQ's 7-day time travel
covers short rollbacks.

⚠️ The raw parquets are NOT raw NIRF data — see README.md "Data provenance".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT      = Path(__file__).resolve().parent.parent
RAW       = ROOT / "raw"
CLEAN     = ROOT / "clean"
EXTRACTED = ROOT / "extracted"

# First-party haul (fetch_dcs.py): ranking/band/participant pages and the
# per-institute DCS PDFs, archived verbatim under raw/dcs/ and staged to
# gs://avantifellows-external-data/nirf/raw/dcs/ as per-year zips by
# upload_to_gcs.py --dcs-raw. parse_dcs.py turns them into extracted/ CSVs.
DCS_RAW = RAW / "dcs"

# Seed lists used by fetch_dcs.py CDN probing, with their provenance:
#   *_bq_ranked_ids.txt      — every AISHE-style code that ever appeared in
#                              nirf_fact_rankings (the Dataful vintage)
#   *_amogh_aishe_list.txt   — Amogh's AISHE-matched 2024 Engineering
#                              participant list (NIRF Extractor project)
#   *_crosswalk_aishe_codes.txt — AISHE codes bridged by the curated JoSAA
#                              matches in metadata/build_overall_college_mapping.py
#                              (Aug 2026) — surfaced 6 more CDN-hosted institutes
# Both are unioned with ids harvested from the saved ranking pages; the CDN
# probe is what decides membership, the seeds only widen the candidate pool.
DCS_SEEDS = DCS_RAW / "seeds"

# ranking_category values that are FIRST-PARTY in nirf_fact_rankings: rows for
# these come from nirfindia.org pages (extracted/nirf_rankings_official.csv);
# every other category still carries the Dataful vintage. See build_clean.py.
FIRST_PARTY_CATEGORIES = ("Engineering", "Medical")

# ─── GCS ────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "nirf"                          # gs://{bucket}/{prefix}/{raw,clean}/*.parquet

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Table registry ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str                              # table in BQ (no project/dataset)
    parquet: str                              # filename in raw/, clean/ and on GCS
    grain: tuple[str, ...]                    # documented grain; build_clean dedups on it
    column_renames: dict[str, str]            # source col → BQ col (only cols that need it)
    derived: bool = False                     # True = built by build_clean, no raw/ input
    extracted_csv: str | None = None          # first-party input in extracted/ (DCS tables)
    supersede_on: tuple[str, ...] | None = None  # key that later editions supersede

    @property
    def extracted_path(self) -> Path:
        return EXTRACTED / self.extracted_csv if self.extracted_csv else None

    @property
    def gcs_uri(self) -> str:
        """Clean parquet on GCS — the object load_bq.py reads."""
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def raw_gcs_uri(self) -> str:
        """Raw parquet on GCS — kept for traceability; fetch into raw/ to rebuild."""
        return f"gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/{self.parquet}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        """Clean parquet written by build_clean.py; read by upload_to_gcs.py."""
        return CLEAN / self.parquet

    @property
    def raw_path(self) -> Path:
        return RAW / self.parquet


# `nirf_fact_aggregate` is pivoted from `nirf_fact_master`, so its measure
# columns inherit master's `category` values — which contain spaces and `%`
# signs that BigQuery won't accept as identifiers. build_clean.py renames them
# so the clean parquet, the GCS file and the BQ table all agree.
AGGREGATE_RENAMES = {
    "Median salary of placed graduates":                    "median_salary",
    "Number of first year students intake":                 "first_year_intake",
    "Number of first year students admitted":               "first_year_admitted",
    "Number of students admmited through lateral entry":    "lateral_entry_admitted",
    "Number of students graduating in min stipulated time": "graduating_on_time",
    "Number of students placed":                            "students_placed",
    "Number of students selected for higher studies":       "higher_studies_selected",
    "Percentage Placed (%)":                                "percentage_placed",
    "Admission Rate (%)":                                   "admission_rate",
}

# How nirf_fact_aggregate is rebuilt from the deduplicated master.
AGGREGATE_PIVOT_INDEX = ["institute_id", "ranking_category", "ranking_year",
                         "academic_year", "type"]
AGGREGATE_JOIN_KEYS   = ["institute_id", "ranking_year", "ranking_category"]

TABLES: list[Table] = [
    Table(
        bq_name="nirf_fact_rankings",
        parquet="nirf_rankings.parquet",
        grain=("ranking_year", "ranking_category", "institute_id"),
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_master",
        parquet="nirf_master.parquet",
        grain=("ranking_year", "ranking_category", "institute_id",
               "type", "academic_year", "category"),
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_strength",
        parquet="nirf_strength.parquet",
        grain=("ranking_year", "ranking_category", "institute_id",
               "programme", "category"),
        column_renames={},
    ),
    Table(
        bq_name="nirf_fact_aggregate",
        parquet="nirf_aggregate.parquet",
        grain=("ranking_year", "ranking_category", "institute_id",
               "academic_year", "type"),
        column_renames=AGGREGATE_RENAMES,
        derived=True,          # rebuilt from master + rankings, no raw/ input
    ),

    # ── First-party DCS tables ──────────────────────────────────────────────
    # Parsed from the per-institute "Data Submitted by Institution" PDFs on
    # nirfindia.org (2019-2025 editions, Engineering + Medical). Each edition
    # restates the 3 trailing academic years and NIRF revises figures between
    # editions, so overlapping keys get a `superseded` flag (TRUE unless the
    # row comes from the newest edition reporting that key). extracted/ CSVs
    # are the parse_dcs.py output; raw PDFs live in raw/dcs/ and on GCS.
    Table(
        bq_name="nirf_fact_dcs_placements",
        parquet="nirf_dcs_placements.parquet",
        grain=("edition_year", "discipline", "institute_id", "program_level",
               "graduating_academic_year"),
        column_renames={},
        derived=True,
        extracted_csv="dcs_placements.csv",
        supersede_on=("discipline", "institute_id", "program_level",
                      "graduating_academic_year"),
    ),
    Table(
        bq_name="nirf_fact_dcs_intake",
        parquet="nirf_dcs_intake.parquet",
        grain=("edition_year", "discipline", "institute_id", "program_level",
               "academic_year"),
        column_renames={},
        derived=True,
        extracted_csv="dcs_intake.csv",
        supersede_on=("discipline", "institute_id", "program_level",
                      "academic_year"),
    ),
    Table(
        bq_name="nirf_fact_dcs_strength",
        parquet="nirf_dcs_strength.parquet",
        grain=("edition_year", "discipline", "institute_id", "program_level"),
        column_renames={},
        derived=True,
        extracted_csv="dcs_strength.csv",
    ),
    Table(
        bq_name="nirf_fact_dcs_institution",
        parquet="nirf_dcs_institution.parquet",
        grain=("edition_year", "discipline", "institute_id"),
        column_renames={},
        derived=True,
        extracted_csv="dcs_institution.csv",
    ),
    Table(
        bq_name="nirf_dim_participants",
        parquet="nirf_participants.parquet",
        grain=("ranking_year", "discipline", "institute_name", "city"),
        column_renames={},
        derived=True,
        extracted_csv="nirf_participants.csv",
    ),
]

# extracted/nirf_rankings_official.csv is not its own table — build_clean.py
# splices it INTO nirf_fact_rankings, replacing the Dataful rows for
# FIRST_PARTY_CATEGORIES and adding rank_band / rank_raw / record_source.
RANKINGS_OFFICIAL_CSV = EXTRACTED / "nirf_rankings_official.csv"
