"""KEAM raw-source registry — every file in keam/raw/, where it came from.

Authority: Commissioner for Entrance Examinations (CEE), Kerala.
Listing pages (also archived in raw/ as provenance):
  https://cee.kerala.gov.in/keam2025/last_rank
  https://cee.kerala.gov.in/keam2026/last_rank

Fetch notes:
  - The site 403s curl's default UA; send a browser User-Agent.
  - It also 403s keam2023/keam2024 — only the last two cycles stay up,
    which is why the archive here matters.
  - The 2026 page still links 2025's medical PDFs inside HTML comments;
    those 404 under keam2026/ (Kerala's NEET-based medical rounds for
    2026 were not published as of 2026-08-21).

Engineering is the parsed stream (feeds keam_fact_cutoffs). Architecture,
B.Pharm and MBBS/allied PDFs are archived verbatim for later use.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "raw", ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "keam"
PARQUET = "keam_fact_cutoffs.parquet"
GCS_CLEAN_URI = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{PARQUET}"

BQ_PROJECT = "avantifellows"
BQ_LOCATION = "asia-south1"
BQ_TABLE_ID = "avantifellows.external_data_sources.keam_fact_cutoffs"

# (local name in raw/, upstream file under keam<year>/list/lastrank/, year, stream, phase)
RAW_FILES = [
    # 2026 — the live cycle. Engineering published through Phase 2 as of
    # 2026-08-21; 'Trial' is CEE's mock allotment, new in 2026.
    ("KEAM_2026_engg_trial.pdf", "trial_lrank.pdf", 2026, "engineering", "Trial"),
    ("KEAM_2026_engg_p1.pdf", "lastrank_p1.pdf", 2026, "engineering", "P1"),
    ("KEAM_2026_engg_p2.pdf", "lastrank_engg_p2.pdf", 2026, "engineering", "P2"),
    ("KEAM_2026_arch_p1.pdf", "lastrank_arch_p1.pdf", 2026, "architecture", "P1"),
    ("KEAM_2026_arch_p2_provisional.pdf", "lrank_arch_p2_provi.pdf", 2026, "architecture", "P2-provisional"),
    ("KEAM_2026_bpharm_p1.pdf", "lrank_p1_bpharm.pdf", 2026, "bpharm", "P1"),
    ("KEAM_2026_bpharm_p2.pdf", "lrank_bpharm_p2.pdf", 2026, "bpharm", "P2"),
    # 2025 — full cycle
    ("KEAM_2025_engg_p1.pdf", "p1_last_rank_final.pdf", 2025, "engineering", "P1"),
    ("KEAM_2025_engg_p2.pdf", "last_rank_engg_p2_final.pdf", 2025, "engineering", "P2"),
    ("KEAM_2025_arch_p1.pdf", "last_rank_arch_p1_final.pdf", 2025, "architecture", "P1"),
    ("KEAM_2025_bpharm_p1.pdf", "lrank_bpharm_final.pdf", 2025, "bpharm", "P1"),
    ("KEAM_2025_bpharm_p2.pdf", "lrank_p2_bpharm_final.pdf", 2025, "bpharm", "P2"),
]

# Kerala's MBBS/BDS and AYUSH/allied rounds are NEET-based counselling, not
# KEAM-exam admissions - "state_medical is NEET". Their 2025 phase-wise
# last-rank PDFs were captured here initially but live with the NEET source:
# gs://avantifellows-external-data/neet/raw/kerala_cee_2025_{mbbs,allied}_p*_lastranks.pdf
# (published on the open-data page under the NEET-UG dataset's Kerala group).

# what the uploader stages: every registered PDF plus the two archived listing pages
UPLOAD_FILES = [t[0] for t in RAW_FILES] + ["KEAM_2025_lastrank_page.html", "KEAM_2026_lastrank_page.html"]

# engineering PDFs that build_clean.py parses, in (file, year, phase) form
ENGG_FILES = [(f, y, p) for f, _, y, s, p in RAW_FILES if s == "engineering"]
