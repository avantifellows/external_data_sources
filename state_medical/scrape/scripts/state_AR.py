"""
Arunachal Pradesh NEET UG — state govt closing ranks pipeline.

⚠️ THIRD-PARTY / UNOFFICIAL SOURCE.

Authority: Directorate of Higher and Technical Education (DHTE) +
           Tomo Riba Institute of Health & Medical Sciences (TRIHMS),
           Naharlagun. https://trihms.com  https://apdhte.nic.in

Reservation note: TRIHMS state pool is 100% APST (Arunachal Pradesh
Scheduled Tribe). Non-APST candidates have ZERO state-pool seats —
they can only get in via the 15% AIQ.

Source: formity.ai — 2025 AIQ by category + APST state-pool closing.

Govt MBBS colleges:
  - TRIHMS Naharlagun — 100 seats (85 APST state quota + 15 AIQ)

Outputs (`_THIRDPARTY` suffix). Two-quota grouping captured.
"""
from _thirdparty_pipeline import run_thirdparty_pipeline

if __name__ == "__main__":
    run_thirdparty_pipeline(state_code="AR", state_name="Arunachal Pradesh")
