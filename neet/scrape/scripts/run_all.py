#!/usr/bin/env python3
"""Run every NEET 2025 cutoff parser in order.

Each parser reads its PDF from ../source/ and writes a clean CSV to
../extracted_data/. Requires the source PDFs to be present (gitignored).
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = [
    ["01_parse_aiq.py"],
    ["02_parse_gujarat.py"],
    ["03_parse_karnataka.py"],
    ["04_parse_flat_states.py", "--all"],
    ["05_parse_andhra.py"],
    ["06_parse_maharashtra.py"],
    ["07_parse_telangana.py"],
    ["08_parse_himachal.py"],
    ["09_parse_kerala.py"],
]


def main():
    for step in STEPS:
        print(f"\n=== {' '.join(step)} ===")
        r = subprocess.run([sys.executable, str(HERE / step[0]), *step[1:]])
        if r.returncode != 0:
            raise SystemExit(f"{step[0]} failed (exit {r.returncode})")
    print("\n✓ all parsers done.")


if __name__ == "__main__":
    main()
