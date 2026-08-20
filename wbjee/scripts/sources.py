"""
WBJEE (West Bengal Joint Entrance Examination) — source configuration.

WHAT THIS SOURCE IS
  Opening and closing ranks for every WBJEE counselling seat bucket
  (round x institute x program x seat-type x quota x category), engineering,
  2021-2026 — six full years including the CURRENT 2026 cycle. Plus the
  pharmacy 2026 report, archived for later.

PROVENANCE
  WBJEEB publishes OR-CR reports at admissions.nic.in behind per-year enc
  tokens listed on https://wbjeeb.nic.in/ewbjee/ — public, no login. The
  fetch quirk that cost an afternoon: the enc token's '+' must be passed
  LITERALLY; percent-encoding it returns NIC's "Something went wrong" page.
  raw/ holds the served HTML verbatim, one file per year.

TWO REAL SCHEMA SHIFTS ACROSS THE YEARS (kept as facts, not smoothed over):
  - 2021 has no Seat Type column: the WBJEE-seats vs JEE(Main)-seats split
    began in 2022. seat_type is NULL for 2021.
  - 2026 merged the OBC - A / OBC - B sub-pools into a single 'OBC'.
    category_raw preserves each year's own vocabulary verbatim.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "raw", ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "wbjee"
BQ_PROJECT, BQ_DATASET, BQ_LOCATION = "avantifellows", "external_data_sources", "asia-south1"

TABLE = "wbjee_fact_cutoffs"
PARQUET = "wbjee_fact_cutoffs.parquet"
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
RAW_FILES = [f"WBJEE_{y}_ORCR.html" for y in YEARS] + ["WBJEE_pharmacy_2026_ORCR.html"]

GCS_CLEAN_URI = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{PARQUET}"
BQ_TABLE_ID = f"{BQ_PROJECT}.{BQ_DATASET}.{TABLE}"
