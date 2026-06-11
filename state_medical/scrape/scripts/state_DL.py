"""
Delhi NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Faculty of Medical Sciences (FMSC), University of Delhi
           — handles 15% Delhi-domicile state quota for DU MBBS colleges.
           https://fmsc.ac.in
Other Delhi govt MBBS colleges (VMMC Safdarjung, ABVIMS-RML, ESIC
Basaidarapur, AIIMS Delhi) are 100% central — already in MCC AIQ DB.

We aggregate from careers360 for the three DU FMSC state-quota colleges
(MAMC, LHMC, UCMS) by category and clearly mark NOT OFFICIAL.

Govt MBBS colleges (state quota only, 15% Delhi-domicile):
  - MAMC (Maulana Azad Medical College)
  - LHMC (Lady Hardinge MC for Women)
  - UCMS (University College of Medical Sciences)
The other 85% of seats at these colleges + the central institutes are
in the MCC AIQ database under their respective central pools.

Outputs (`_THIRDPARTY` suffix).
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="DL", state_name="Delhi")
