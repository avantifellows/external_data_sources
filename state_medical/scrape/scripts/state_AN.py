"""
Andaman & Nicobar Islands (UT) NEET UG — closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Andaman & Nicobar Islands Institute of Medical Sciences
           (ANIIMS), Port Blair. UT govt MBBS, MoHFW-controlled.
           Most seats counselled via MCC AIQ (since the UT has small
           local population — A&N domicile pool is tiny). Effectively
           a 100% AIQ college for cross-country candidates.

Source: careers360.com — 2025 R1 + R2 + R3 AIQ closing AIR by category.

Govt MBBS colleges in A&N:
  - ANIIMS Port Blair — 114 seats (~17 AIQ + 97 A&N domicile;
    domicile pool not separately publishable from 3rd-party data)

Outputs (`_THIRDPARTY` suffix). AIQ-only data captured.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="AN", state_name="Andaman & Nicobar Islands")
