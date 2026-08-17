"""
Dadra & Nagar Haveli + Daman & Diu (UT) NEET UG — closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: U.T. Administration of DNH & DD via NAMO Medical Education
           & Research Institute (NAMO MC), Silvassa.
           https://namomeridnhdd.in
NAMO MC is the only state govt MBBS in DNH-DD (first batch ~2024).
DNH-DD seats are routed through Gujarat NEET counselling (ACPUGMEC) for
the state pool, in addition to 15% MCC AIQ.

Source: careers360.com — 2024 AIQ R1 + Final closing AIR;
        Gujarat-counselling state pool by category (range upper-bounds).

Govt MBBS colleges:
  - NAMO MC Silvassa — ~150 MBBS seats

Outputs (`_THIRDPARTY` suffix). Two-quota grouping captured.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="DD", state_name="Dadra & Nagar Haveli + Daman & Diu")
