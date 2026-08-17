#!/usr/bin/env python3
"""
run_all.py — josaa-ranks pipeline.

Stages:
  01_scrape_archive.py  — JoSAA archive (years 2016–2024, all rounds)
  02_scrape_current.py  — JoSAA current cycle (2025, all rounds)
  03_consolidate.py     — union raw scrapes into per-year + all-years CSVs
  nit_hs_closing_ranks_all_categories.py  — NIT HS 5-cat derivation (downstream-consumed)
  nit_hs_closing_ranks.py                  — NIT HS OPEN-only quick view

NB: the scrape stages cache to extracted_data/raw/<year>_R<round>.csv and SKIP
files that already exist. To force a re-scrape, delete the cached files first.

Total runtime:
  - Cold (no cache): ~10–15 min (network-bound on josaa.admissions.nic.in)
  - Warm (cache hits): ~3 sec
"""
from __future__ import annotations
import importlib.util
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

STAGES = [
    ("01_scrape_archive.py",  "Scrape JoSAA archive 2016–2024 (idempotent; skips cached files)"),
    ("02_scrape_current.py",  "Scrape JoSAA 2025 current cycle (idempotent; skips cached files)"),
    ("03_consolidate.py",     "Reduce raw → per-year final-round CSVs (no all-years union — regenerate live)"),
    ("04_enrich.py",          "Enrich per-year CSVs with state/college_id/NIRF salary via college_master.csv join"),
    ("nit_hs_closing_ranks_all_categories.py",
     "NIT HS closing ranks — all 5 categories (downstream consumer in CoE Selection DB)"),
    ("nit_hs_closing_ranks.py",
     "NIT HS closing ranks — OPEN only (quick view + histogram)"),
]


def run_script(path):
    spec = importlib.util.spec_from_file_location("module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "main"):
        module.main()


def main():
    print("=" * 64)
    print("josaa-ranks — full pipeline (scrape + derivation)")
    print("=" * 64)
    overall_start = time.time()

    for name, description in STAGES:
        path = HERE / name
        if not path.exists():
            print(f"\n  ✗ MISSING: {name}")
            continue
        print(f"\n[ {name} ]  {description}")
        start = time.time()
        run_script(path)
        print(f"  ⏱  {time.time() - start:.1f}s")

    print(f"\n{'=' * 64}")
    print(f"Pipeline complete in {time.time() - overall_start:.1f}s")
    print(f"{'=' * 64}")
    print("\nKey outputs in extracted_data/:")
    print("  raw/<year>_R<round>.csv             per-(year, round) raw scrape (cached)")
    print("  josaa_<year>.csv                    per-year final-round CSVs (10 years: 2016–2025)")
    print("  josaa_<year>_enriched.csv           same + state/college_id/NIRF salary joined")
    print("  _institute_lookup.csv               institute → match-quality + canonical metadata")
    print("  nit_hs_closing_ranks_all_categories.csv  NIT HS 5-cat (downstream-consumed)")
    print("  nit_hs_closing_ranks_all_categories_wide.csv")
    print("  nit_hs_closing_ranks_scatter.png")
    print("  nit_hs_closing_ranks.csv            NIT HS OPEN sortable")
    print("  nit_hs_closing_ranks.png            OPEN distribution histogram")
    print()
    print("To union all years × all rounds at use-time (the deleted all_years.csv pattern):")
    print("  pd.concat([pd.read_csv(f) for f in sorted(Path('extracted_data/raw').glob('*.csv'))])")


if __name__ == "__main__":
    main()
