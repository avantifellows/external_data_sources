"""
Puducherry NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Centralized Admission Committee (CENTAC), Govt of Puducherry.
           https://www.centacpuducherry.in
CENTAC publishes round-wise PDFs on its dashboard but they aren't
indexable / auto-fetchable. We aggregate from neetugguidance.in for
IGMC&RI Puducherry (the headline state-quota govt MBBS) and clearly
mark NOT OFFICIAL.

Govt MBBS colleges:
  - IGMC&RI Puducherry (Indira Gandhi MC&RI) — state-quota seats via
    CENTAC. ~150 MBBS seats.
  - JIPMER Puducherry — 100% central, already in MCC AIQ database.
  - Pondicherry Institute of Medical Sciences (PIMS), MGMC&RI Sri
    Balaji Vidyapeeth — deemed/private, not state govt.

Outputs (`_THIRDPARTY` suffix). See `_thirdparty_pipeline.py` for
schema + behavior.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="PD", state_name="Puducherry")
