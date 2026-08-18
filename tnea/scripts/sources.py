"""
TNEA (Tamil Nadu Engineering Admissions) — source configuration.

WHAT THIS SOURCE IS
  Final-round cutoffs for every TNEA seat bucket: the last admitted candidate's
  composite mark (/200) AND state merit rank, per college x branch x community.
  2025 cycle: 3,457 college-branch rows x 7 communities -> 14,910 real cells
  (an em-dash cell means no admission in that bucket, and becomes no row).

PROVENANCE
  raw/TN_TNEA_2025_cutoff_marks.csv        the portal's mark-cutoff table
  raw/TN_TNEA_2025_state_merit_ranks.csv   the portal's rank-cutoff table
  Both pulled from the official TNEA results portal with
  ../scrape/scripts/tn_console_extract.js (sakshi1755, imported via PR #83).
  Government-college classification comes from the official DOTE college-code
  list -- the code sets live in ../scrape/scripts/state_TN.py and are lifted
  from there at build time so there is exactly one copy.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "raw", ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "tnea"
BQ_PROJECT, BQ_DATASET, BQ_LOCATION = "avantifellows", "external_data_sources", "asia-south1"

TABLE = "tnea_fact_cutoffs"
PARQUET = "tnea_fact_cutoffs.parquet"
RAW_FILES = ["TN_TNEA_2025_cutoff_marks.csv", "TN_TNEA_2025_state_merit_ranks.csv"]

GCS_CLEAN_URI = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{PARQUET}"
BQ_TABLE_ID = f"{BQ_PROJECT}.{BQ_DATASET}.{TABLE}"
