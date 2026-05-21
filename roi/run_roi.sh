#!/usr/bin/env bash
# Build the RoI wage curves end to end: three per-source extracts → one table.
# Run from anywhere; paths are resolved relative to this script.
set -euo pipefail
cd "$(dirname "$0")"

echo "── 1/3  NIRF ranked-tier pay + placement ──────────────────────────────"
python3 scripts/nirf_tiers.py
echo
echo "── 2/3  AISHE annual UG graduate universe ─────────────────────────────"
python3 scripts/aishe_grads.py
echo
echo "── 3/3  Combine → wage_curves.csv (PLFS computed in-memory) ───────────"
python3 scripts/wage_curves.py
echo
echo "(PLFS: run 'python3 scripts/plfs_baseline.py' to inspect the 8-group table.)"
