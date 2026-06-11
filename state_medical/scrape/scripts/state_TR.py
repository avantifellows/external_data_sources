"""
Tripura NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: DME Tripura.
           https://dme.tripura.gov.in
Counselling on NIC-hosted `trmcc.admissions.nic.in`. Round PDFs
require active session; not crawler-indexed. We aggregate from
neetugguidance.in (AGMC by category) + careers360 (R1 closing summary).

Govt MBBS colleges:
  - Agartala Government Medical College (AGMC) — ~125 MBBS seats
  - Tripura Medical College & Dr BRAM Teaching Hospital — govt-aided
    society, ~100 MBBS

Outputs (`_THIRDPARTY` suffix).
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="TR", state_name="Tripura")
