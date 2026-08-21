"""OJEE (Odisha) raw-source registry.

Authority: OJEE Cell, Odisha (ojee.nic.in). B.Tech first-year admission in
Odisha counsels on JEE (Main) ranks through OJEE counselling — the OR/CR
figures in this document are JEE Main ranks, NOT an OJEE state rank.

The 2025 B.Tech OR-CR was login-gated during its own cycle (which is why
futures-v2's state_OD.py used the 2024 file as proxy); OJEE published it
openly in May 2026 as reference for the 2026 cycle — the same
prior-year-on-the-new-portal pattern as AP. Archive on sight.

2025 file found 2026-08-22 on https://ojee.nic.in/opening-closing-rank/

REFRESH DRILL: when 2026 counselling concludes, recheck that page for
"OPENING & CLOSING RANKS - BTECH 2026" (2026 was mid-flight at capture:
B.Tech Round 2 allotted 16-07-2026).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "raw", ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "ojee"
PARQUET = "ojee_fact_cutoffs.parquet"
GCS_CLEAN_URI = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{PARQUET}"

BQ_PROJECT = "avantifellows"
BQ_LOCATION = "asia-south1"
BQ_TABLE_ID = "avantifellows.external_data_sources.ojee_fact_cutoffs"

RAW_FILES = [
    ("OD_OJEE_2025_btech_orcr.pdf",
     "https://cdnbbsr.s3waas.gov.in/s36832a7b24bc06775d02b7406880b93fc/uploads/2026/05/202605181631301089.pdf",
     2025),
]
UPLOAD_FILES = [t[0] for t in RAW_FILES]
