"""
Manipur NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Directorate of Health Services, Govt of Manipur.
           https://manipurhealthdirectorate.mn.gov.in
DHS publishes round PDFs but they're not indexable for programmatic
fetch. We aggregate from pw.live (RIMS Imphal full category breakdown
2024) + careers360 (JNIMS 2023 historical category breakdown). 2025
data not yet available from any third-party source as of refresh date.

Govt MBBS colleges:
  - RIMS Imphal — Regional Institute of Medical Sciences, central
    autonomous body but state quota for Manipur (107 seats)
  - JNIMS Imphal — Jawaharlal Nehru Institute of Medical Sciences,
    state govt (~85 state quota seats)

Outputs (`_THIRDPARTY` suffix).
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="MN", state_name="Manipur")
