"""
Run all state pipelines end-to-end (19 official + 14 third-party = 33).

  cd scripts && python3 run_all.py

Re-parses every state's source PDFs / loads each state's THIRDPARTY_*.csv
and regenerates outputs in ../extracted_data/. Idempotent — same inputs
produce same outputs.

Total runtime: ~13 minutes (Maharashtra and UP dominate).

Each state script is independent — failure in one doesn't stop others.
A summary is printed at the end with row counts per state.

The trailing 8 scripts (state_OD, HR, GA, PD, TR, MN, MZ, DL) consume
third-party aggregator data (their official portals are unreachable or
not crawler-friendly) and emit outputs suffixed `_THIRDPARTY`. They share
a thin helper module `_thirdparty_pipeline.py`. See each script docstring
for sourcing notes.

Note: the UP pipeline reads from the pre-scraped raw CSV (`source/UP/
UP_all_allotments_2025_raw.csv`) rather than re-scraping from the live
ASP.NET portal. Re-scrape via Chrome MCP if you need a fresh pull (see
state_UP.py docstring + CLAUDE.md "UP scraping recipe").
"""
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
STATES = [
    "state_KA.py",  # Karnataka — Tier 1 (fastest)
    "state_TN.py",  # Tamil Nadu
    "state_MH.py",  # Maharashtra (slow — 4-5 min)
    "state_TG.py",  # Telangana
    "state_WB.py",  # West Bengal
    "state_GJ.py",  # Gujarat
    "state_RJ.py",  # Rajasthan (uses 2024 data)
    "state_UP.py",  # Uttar Pradesh (uses pre-scraped raw CSV)
    "state_KL.py",  # Kerala — Tier 2
    "state_MP.py",  # MP
    "state_AP.py",  # AP
    "state_BR.py",  # Bihar — Tier 3
    "state_CG.py",  # Chhattisgarh
    "state_JK.py",  # J&K
    "state_PB.py",  # Punjab
    "state_HP.py",  # Himachal Pradesh
    "state_UK.py",  # Uttarakhand
    "state_JH.py",  # Jharkhand
    "state_AS.py",  # Assam
    # Below: third-party / unofficial data — outputs suffixed `_THIRDPARTY`
    "state_OD.py",  # Odisha — third-party only (OJEE 2025 site rolled to 2026)
    "state_HR.py",  # Haryana — third-party only (uhsrugcounselling.com offline)
    "state_GA.py",  # Goa — third-party (DTE Goa PDFs not URL-able)
    "state_PD.py",  # Puducherry — third-party (CENTAC PDFs gated)
    "state_TR.py",  # Tripura — third-party (NIC portal needs session)
    "state_MN.py",  # Manipur — third-party (DHS PDFs not auto-fetchable)
    "state_MZ.py",  # Mizoram — third-party (DHTE PDFs unstable URLs)
    "state_DL.py",  # Delhi — third-party (FMSC state quota only)
    "state_CH.py",  # Chandigarh (UT) — third-party (GMCH-32; AIQ + UT pool)
    "state_ML.py",  # Meghalaya — third-party (NEIGRIHMS; AIQ + state quota)
    "state_AR.py",  # Arunachal Pradesh — third-party (TRIHMS; AIQ + APST pool)
    "state_NL.py",  # Nagaland — third-party (NIMSR; AIQ-only data so far)
    "state_AN.py",  # A&N Islands (UT) — third-party (ANIIMS; AIQ-only)
    "state_DD.py",  # Dadra & Nagar Haveli + Daman & Diu (UT) — third-party (NAMO MC)
]


def main():
    t0 = time.time()
    results = []
    for stage in STATES:
        print(f"\n{'='*70}\n{stage}\n{'='*70}")
        t = time.time()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / stage)],
            cwd=SCRIPTS_DIR,
        )
        elapsed = time.time() - t
        ok = result.returncode == 0
        results.append((stage, ok, elapsed))
        print(f"  {'OK' if ok else 'FAIL'} ({elapsed:.0f}s)")

    # Final stages: cross-state normalization
    #   1. state_rank_to_air.py      — builds per-state state_rank → AIR
    #      curves (KL, JK, GJ per-category, TN, JH score-bridge)
    #   2. normalize_round_depth.py  — applies tier-stratified round
    #      multipliers for R1/R2-only states
    # See: extracted_data/METHODOLOGY_round_normalization.md
    for stage in ["state_rank_to_air.py", "normalize_round_depth.py"]:
        print(f"\n{'='*70}\n{stage} (cross-state)\n{'='*70}")
        t = time.time()
        r = subprocess.run([sys.executable, str(SCRIPTS_DIR / stage)],
                            cwd=SCRIPTS_DIR)
        elapsed = time.time() - t
        results.append((stage, r.returncode == 0, elapsed))
        print(f"  {'OK' if r.returncode == 0 else 'FAIL'} ({elapsed:.0f}s)")

    print(f"\n{'='*70}\nDone in {time.time()-t0:.0f}s\n{'='*70}")
    for stage, ok, elapsed in results:
        marker = "✓" if ok else "✗"
        print(f"  {marker} {stage:25s} ({elapsed:5.0f}s)")
    if not all(ok for _, ok, _ in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
