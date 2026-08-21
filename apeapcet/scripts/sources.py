"""AP EAPCET raw-source registry.

Authority: APSCHE (AP State Council of Higher Education) / Convener AP EAPCET.
Portal:    https://cap.apcfss.in/  (Common Admissions Portal, 2026-27 cycle —
           replaced eapcet-sche.aptonline.in, which no longer accepts
           connections; apsche.ap.gov.in/Pdf/ URLs from 2024 are 404).

The consolidated last-rank PDF is published on the CURRENT cycle's portal as
reference material and past years' copies rot quickly (the 2022-proxy era of
futures-v2's state_AP.py exists because of exactly that). Archive on sight.

2025 file found 2026-08-21 at:
  https://cap.apcfss.in/TET-PDF/EAPCET-DOCS/EAPCET2025LASTRANKDETAILS.pdf
(referenced by the portal's own app bundle; the server soft-200s bogus paths,
so verify content-type is application/pdf when refetching.)

REFRESH DRILL: when 2026 counselling concludes, probe
  https://cap.apcfss.in/TET-PDF/EAPCET-DOCS/EAPCET2026LASTRANKDETAILS.pdf
(and the EAPCET-DOCS listing in main.js) — as of 2026-08-21 the 2026 cycle
was mid-flight (Phase 1 allotment 09-08-2026, final phase registrations
17-20 Aug) and no 2026 consolidated file existed yet.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "raw", ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "apeapcet"
PARQUET = "apeapcet_fact_cutoffs.parquet"
GCS_CLEAN_URI = f"gs://{GCS_BUCKET}/{GCS_PREFIX}/clean/{PARQUET}"

BQ_PROJECT = "avantifellows"
BQ_LOCATION = "asia-south1"
BQ_TABLE_ID = "avantifellows.external_data_sources.apeapcet_fact_cutoffs"

# (local name in raw/, upstream URL, year)
RAW_FILES = [
    ("AP_EAPCET_2025_lastranks.pdf",
     "https://cap.apcfss.in/TET-PDF/EAPCET-DOCS/EAPCET2025LASTRANKDETAILS.pdf",
     2025),
]

UPLOAD_FILES = [t[0] for t in RAW_FILES]
