"""
Central config for all JNV pipeline scripts.
GCS paths, BQ identifiers, and table definitions all live here.
"""

from dataclasses import dataclass
from pathlib import Path
import sys

JNV_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(JNV_DIR.parent))  # external_data_sources root

# ── GCS ───────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "jnv"

# ── BigQuery ──────────────────────────────────────────────────────────────────
BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"

# ── Table definitions ─────────────────────────────────────────────────────────

@dataclass
class Table:
    name: str          # used as GCS filename stem and BQ table suffix
    local_path: Path   # local file to upload (CSV or parquet)

    @property
    def gcs_path(self):
        return f"{GCS_PREFIX}/clean/{self.name}.parquet"

    @property
    def gcs_uri(self):
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def bq_table_id(self):
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.name}"


# Clean table loaded into BigQuery
JEE_CLEAN = Table(
    name="jnv_fact_jee_results",
    local_path=JNV_DIR / "clean" / "jee_clean.csv",
)

NEET_CLEAN = Table(
    name="jnv_fact_neet_results",
    local_path=JNV_DIR / "clean" / "neet_clean.csv",
)

JNVST_CLEAN = Table(
    name="jnv_fact_selection_test_results",
    local_path=JNV_DIR / "clean" / "jnvst_clean.csv",
)

EI_ASSET_TEST_CLEAN = Table(
    name="jnv_fact_ei_asset_test_results",
    local_path=JNV_DIR / "clean" / "ei_asset_test_clean.csv",
)

# ── Raw file definitions (Excel → parquet on GCS) ─────────────────────────────

@dataclass
class RawFile:
    file: str              # filename under raw/<subdir>/
    sheet: str             # primary sheet to extract
    subdir: str = "jee_mains"  # subfolder under raw/ and GCS raw/

    @property
    def gcs_path(self):
        stem = Path(self.file).stem.lower().replace(" ", "_")
        return f"{GCS_PREFIX}/raw/{self.subdir}/{stem}.parquet"

    @property
    def local_path(self):
        return JNV_DIR / "raw" / self.subdir / self.file


# Primary sheet for each raw file (mirrors codemap source definitions)
RAW_MAINS_FILES = [
    RawFile("JEE Mains 2021.xlsx",                                            "FullData"),
    RawFile("JEE Mains 2022.xlsx",                                            "Full Data"),
    RawFile("JEE Mains 2023.xlsx",                                            "Sheet1"),
    RawFile("JEE Mains 2024.xlsx",                                            "JEE Mains"),
    RawFile("JEE 2025 - All JNV Candidates.xlsx",                             "JEE 2025 - All JNV Candidates"),
    RawFile("JEE 2026 - All Passing Candidates passing 2025 or later.xlsx",   "Sheet1"),
    RawFile("JEE 2026 - Passing Candidates graduating before 2025.xlsx",      "Sheet1"),
]

RAW_ADV_FILES = [
    RawFile("JEE Advanced 2024.xlsx",   "Sheet1", subdir="jee_advanced"),
    RawFile("JEE Advanced 2025 .xlsx",  "Sheet1", subdir="jee_advanced"),
]

RAW_NEET_FILES = [
    RawFile("NEET 2021.xlsx",  "Total Students Applied", subdir="neet"),
    RawFile("NEET 2022.xlsx",  "Full Data",              subdir="neet"),
    RawFile("NEET 2023.xlsx",  "Sheet1",                 subdir="neet"),
    RawFile("NEET 2024.xlsx",  "Sheet1",                 subdir="neet"),
    RawFile("NEET 2025.xlsx",  "Sheet1",                 subdir="neet"),
]

RAW_JNVST_FILES = [
    RawFile("JNVST 2018 11-09-2025.xlsx", "JNVST 2018", subdir="jnvst"),
]

RAW_EI_ASSET_TEST_FILES = [
    RawFile("EI_Asset_Test.xlsx", "student_scores", subdir="ei_asset_test"),
]

# Legacy alias kept so upload_to_gcs.py and load_bq.py continue to work
# until they are updated to use the new names.
RAW_FILES = RAW_MAINS_FILES