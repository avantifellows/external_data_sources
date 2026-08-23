"""
College fees source configuration — the single source of truth.

WHAT THIS SOURCE IS. A hand-collected compilation (Amogh's team, Aug 2026) of
tuition/total/hostel fees for counselling-relevant colleges, transcribed from
each college's OWN published fee structure (the source_url on every row —
mostly 2025-26 documents, a few 2026-27). The sheet is the raw layer we
archive; the true originals are the linked college pages, which we do NOT
mirror (a few were spot-verified and saved during intake — see README).

Verification (Aug 2026): 4 of 4 fetchable source documents matched the sheet
exactly (IIT Delhi, NITK Surathkal, SLIET, NERIST) — tuition, first-semester
total, and hostel/mess figures all agree to the rupee. One systematic
transcription bug exists and is repaired in build_clean.py: on some
tuition-waived rows (SC/ST/PwD), the total column kept the FULL total instead
of dropping the waived tuition (IIT Delhi's own PDF: waived total is 22,400,
not 1,22,400).

Coverage is deliberately uneven and shipped honestly:
  JoSAA   ~98% of rows filled, 111 colleges — effectively complete
  KCET    25 of 148 colleges filled — PARTIAL, kept with eyes open
  MHT-CET ~0% filled — an empty template, dropped entirely
"""
from __future__ import annotations

from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
RAW   = ROOT / "raw"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "collegefees"

BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"

RAW_CSV       = RAW / "college_fee_hostel_details_2025-26.csv"
CLEAN_PARQUET = CLEAN / "collegefees_costs.parquet"

BQ_TABLE   = f"{BQ_PROJECT}.{BQ_DATASET}.collegefees_fact_costs"
GCS_RAW    = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/raw/{RAW_CSV.name}"
GCS_CLEAN  = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{CLEAN_PARQUET.name}"

# grain: one row per seat-bucket's fee quote
GRAIN = ("counselling", "college_id", "course_name", "demo_id")
