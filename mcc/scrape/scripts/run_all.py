"""
Run the full national-pool pipeline end-to-end.

  cd scripts && python3 run_all.py

Re-parses all source PDFs/HTML and regenerates everything in
../extracted_data/. Idempotent. Takes ~3-4 minutes (most of it spent on
the 1,107-page R1 PDF).
"""
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
STAGES = [
    "01_parse_nmc_mbbs.py",
    "02_parse_dci_bds.py",
    "03_combine_govt_colleges.py",
    "04_parse_mcc_seat_matrix.py",
    "05_parse_r1_closing_ranks.py",
]


def main():
    t0 = time.time()
    for stage in STAGES:
        print(f"\n{'='*70}\n{stage}\n{'='*70}")
        t = time.time()
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / stage)],
            cwd=SCRIPTS_DIR,
        )
        if result.returncode != 0:
            print(f"\n{stage} failed (exit {result.returncode})")
            sys.exit(result.returncode)
        print(f"  ({time.time()-t:.0f}s)")
    print(f"\nDone in {time.time()-t0:.0f}s.")


if __name__ == "__main__":
    main()
