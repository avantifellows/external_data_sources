"""
Nagaland NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Directorate of Technical Education, Nagaland +
           Nagaland Institute of Medical Sciences and Research (NIMSR),
           Phreibagei, Kohima. https://nimsr.nagaland.gov.in
NIMSR is Nagaland's first and only state govt medical college (first
intake 2024-25). State pool is heavily reserved for Naga tribes (ST).

Sources:
  - mbbscouncil.com — 2025 R1 AIQ score-based cutoffs (no AIR)
  - pw.live — 2024 last-round AIQ closing AIR for UR/OBC/ST
  State-quota category-wise data not yet on aggregators.

Govt MBBS colleges:
  - NIMSR Kohima — 100 seats (85 state pool + 15 AIQ)

Outputs (`_THIRDPARTY` suffix). Single quota (AIQ) for now.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="NL", state_name="Nagaland")
