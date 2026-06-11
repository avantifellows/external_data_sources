"""
Chandigarh (UT) NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Government Medical College & Hospital, Sector 32, Chandigarh
           (GMCH-32) — `https://gmch.gov.in`. UT-pool counselling
           handled in-house. PGIMER also has 50 MBBS but uses its own
           non-NEET PGIMER-MBBS exam (excluded from this NEET DB).

Source mix (preserved in source/CH/):
  - collegedekho.com — 2024 UT-pool (state quota 85%) UR/OBC/SC
  - kollegeapply.com — 2024 AIQ R1 + R2 UR/OBC/EWS/SC/ST

Govt MBBS colleges in Chandigarh (UT):
  - GMCH-32 — 150 seats (~127 UT-pool + 23 AIQ; PwD horizontal)

Outputs (`_THIRDPARTY` suffix). Two-quota grouping captured.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="CH", state_name="Chandigarh")
