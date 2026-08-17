#!/usr/bin/env python3
"""
Kerala NEET-UG (KEAM/CEE) 2025 Phase-3 allotment parser -> closing-rank cutoffs.

Kerala's allotment file lists a KERALA STATE RANK, not a NEET AIR, so on its own
it is not comparable to the other states. We convert it using the KEAM 2025
"State Medical Rank List" (mbbsranklist.pdf), which carries, per candidate:
    ApplNo | NEET Score | NEET Rank (AIR) | State Rank
We build ApplNo->AIR (exact) and State-Rank->AIR (fallback) maps from it and map
each allotment row to a real NEET AIR.

Allotment columns (extract_tables, 8-col):
  SlNo | ApplNo | Rank(=State Rank) | College | Course | Candidate Cat | Allotted Cat | Option

Cutoff = MAX AIR per (college, allotted category). rank_space = 'NEET AIR'
(converted). Rows whose rank/applno can't be mapped are reported, not guessed.
"""
from __future__ import annotations
import argparse, csv, re, sys, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _institute import program_from_name

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "kerala.pdf"
DEFAULT_RANKLIST = ROOT / "source" / "kerala_ranklist.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_kerala_2025_cutoffs.csv"

# Verified MBBS/BDS overrides for colleges whose name defeats the heuristic
# (confirmed against NMC/NDC listings). Keyed on a distinctive name substring.
PROGRAM_OVERRIDES = {
    "Azeezia Institute of Medi": "MBBS",   # NMC medical college, 100 MBBS seats
    "MES Dental College": "BDS",           # NDC dental college, 100 BDS seats
}


def resolve_program(college: str) -> str:
    for frag, prog in PROGRAM_OVERRIDES.items():
        if frag.lower() in college.lower():
            return prog
    return program_from_name(college)


def build_crosswalk(ranklist: Path):
    """ApplNo->AIR and StateRank->AIR from the KEAM state medical rank list."""
    appl2air, state2air = {}, {}
    with pdfplumber.open(ranklist) as pdf:
        for page in pdf.pages:
            for tb in page.extract_tables() or []:
                for r in tb:
                    cells = [(c or "").strip() for c in r]
                    # record: [Sl., ApplNo, Score, NEETRank(AIR), StateRank]
                    if (
                        len(cells) >= 5
                        and re.match(r"\d+\.?$", cells[0])
                        and cells[1].isdigit()
                    ):
                        appl = cells[1]
                        air = cells[3].replace(",", "")
                        srank = cells[4].replace(",", "")
                        if air.isdigit() and srank.isdigit():
                            appl2air[appl] = int(air)
                            state2air[int(srank)] = int(air)
    return appl2air, state2air


def parse(src: Path, appl2air, state2air):
    buckets = {}
    n = miss = 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for tb in page.extract_tables() or []:
                for r in tb:
                    if not r or not str(r[0]).strip().isdigit() or len(r) < 8:
                        continue
                    appl = str(r[1]).strip()
                    srank = str(r[2]).strip().replace(",", "")
                    college = (r[3] or "").replace("\n", " ").strip()
                    cat = (r[6] or "").strip()  # allotted category
                    if not college or not cat:
                        continue
                    # convert state rank/applno -> NEET AIR
                    air = appl2air.get(appl)
                    if air is None and srank.isdigit():
                        air = state2air.get(int(srank))
                    if air is None:
                        miss += 1
                        continue
                    n += 1
                    key = (college, cat)
                    if air > buckets.get(key, 0):
                        buckets[key] = air
    return buckets, n, miss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--ranklist", type=Path, default=DEFAULT_RANKLIST)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    appl2air, state2air = build_crosswalk(args.ranklist)
    print(f"crosswalk: {len(appl2air)} ApplNo->AIR, {len(state2air)} StateRank->AIR")

    buckets, n, miss = parse(args.src, appl2air, state2air)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Category", "Academic Program Name",
                    "Seat Type", "Round", "Closing Rank", "rank_space"])
        for (college, cat), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([college, cat, resolve_program(college), "State Quota",
                        "P3", air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} rows "
          f"({miss} unmapped rows dropped)")
    print("  colleges:", len({k[0] for k in buckets}))
    print("  categories:", len({k[1] for k in buckets}))


if __name__ == "__main__":
    main()
