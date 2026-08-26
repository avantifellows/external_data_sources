"""
CLAT source configuration — the single source of truth.

WHAT THIS IS. CLAT 2026 UG counselling allotments, derived FIRST-PARTY from
the Consortium of NLUs' per-university candidate-level allotment PDFs
(consortiumofnlus.ac.in). The consortium site rotates each cycle (it now
serves CLAT 2027), but the underlying S3 objects stay live:

  https://s3.ap-south-1.amazonaws.com/files2026.consortiumofnlus.ac.in/list{N}/UG-*.pdf

and the list pages are preserved on the Wayback Machine (snapshots archived
in raw/pages/). The 5th list (published 2026-05-20) is CUMULATIVE — it holds
every provisionally-admitted candidate (rank, admit-card no, vertical +
horizontal reservation) plus vacated seats — so final closing ranks derive
from it alone.

WHY DERIVED, NOT COPIED. A hand-me-down cutoffs CSV (clat_2026_cutoffs.csv,
~/jan2023) failed verification against these PDFs: some rows exact, others
off by thousands (DSNLU BC-E: CSV 10993 vs official 6598), and it flattened
horizontal reservations (Women/PwD/NCC) into the category column. The
Chandigarh lesson applies: derive from the official register.

PII NOTE. The PDFs carry All India Rank + admit-card numbers (no names).
They are official public documents; the raw archive stays in the private
bucket, and the extracted/clean tables carry NO candidate-level identifiers
— only aggregated closing ranks.
"""
from __future__ import annotations

from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
RAW   = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "clat"

BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"

S3_BASE = "https://s3.ap-south-1.amazonaws.com/files2026.consortiumofnlus.ac.in"
LISTS = [1, 2, 3, 4, 5]
FINAL_LIST = 5

CLEAN_PARQUET = CLEAN / "clat_cutoffs.parquet"
BQ_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.clat_fact_cutoffs"
GCS_CLEAN = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{CLEAN_PARQUET.name}"

# grain of the clean table
GRAIN = ("year", "college", "program", "vertical_raw", "horizontal_raw")
