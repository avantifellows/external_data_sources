"""
Meghalaya NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: NEIGRIHMS Shillong (North Eastern Indira Gandhi Regional
           Institute of Health & Medical Sciences), central autonomous
           body under MoHFW. Acts as both AIQ host and Meghalaya state-
           pool host. Shillong Medical College (newer, 50 seats from
           2023) not in third-party data.

Source: collegedekho.com — 2024 NEIGRIHMS by category × {AIQ, state
quota 85%}. State-quota figures cited as ranges; we capture the upper
bound (= closing rank).

Govt MBBS colleges in Meghalaya:
  - NEIGRIHMS Shillong — 100 MBBS (50 → 100 from 2025)
  - Shillong Medical College — newer, 50 seats (no 3rd-party data yet)

Outputs (`_THIRDPARTY` suffix). Two-quota grouping captured.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="ML", state_name="Meghalaya")
