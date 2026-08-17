"""
Goa NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Directorate of Technical Education, Govt of Goa.
           https://dte.goa.gov.in
DTE Goa publishes round-wise PDFs but they aren't conveniently URL-able
for programmatic access. We aggregate from careers360 (which carries
clean R1/R2/R3 opening+closing AIR by category for Goa Medical College —
the only state govt MBBS college in Goa) and clearly mark NOT OFFICIAL.

Govt MBBS colleges: Goa Medical College, Bambolim (~180 seats).
Govt BDS colleges: Goa Dental College, Bambolim (~40 seats; not in
                   third-party data).

Outputs (`_THIRDPARTY` suffix). See `_thirdparty_pipeline.py` for
schema + behavior.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="GA", state_name="Goa")
