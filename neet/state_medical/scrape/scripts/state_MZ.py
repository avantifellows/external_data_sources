"""
Mizoram NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Department of Higher and Technical Education (DHTE), Mizoram.
           https://dhte.mizoram.gov.in
DHTE publishes provisional merit list and round-wise allotment PDFs
but they're not stable URLs. We aggregate from careers360 (Zoram MC
General closing rank 2025) + mbbscouncil (AIQ 2025 cutoff scores) +
edufever (2023 historical scores). 2025 state-quota category-wise data
not surfaced by any aggregator.

Govt MBBS colleges:
  - Zoram Medical College, Falkawn — only one state govt MBBS,
    ~100 seats (85 state + 15 AIQ).

Outputs (`_THIRDPARTY` suffix).
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="MZ", state_name="Mizoram")
