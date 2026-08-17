#!/usr/bin/env python3
"""
Karnataka NEET-UG (KEA/UGNEET) 2025 R3 parser -> closing-rank cutoffs.

Per-student allotment list, 8 clean columns:
  SL.NO | All India Rank | Course Code | College | Course Name | Category | Fees | Status

Cutoff = MAX All-India-Rank per (college, course-code, category). Course Name
encodes program + college type: 'MBBS-GOVT.'/'MBBS-PRIV.'/'MBBS-OTHERS'/'MBBS-NRI'.
Course Code (e.g. M069MG) is KEA's stable college code. rank_space = 'NEET AIR'.
"""
from __future__ import annotations
import argparse, csv, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "karnataka.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_karnataka_2025_r3_cutoffs.csv"


def clean(s):
    return (s or "").replace("\n", " ").strip()


def split_course(cn):
    cn = cn.upper().replace(" ", "")
    prog = "BDS" if cn.startswith("BDS") else "MBBS"
    seat = ("Government" if "GOVT" in cn else "Private" if "PRIV" in cn
            else "NRI" if "NRI" in cn else "Other")
    return prog, seat


def parse(src: Path):
    buckets, n, skip = {}, 0, 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables() or []:
                for r in t:
                    if not r or not str(r[0]).strip().isdigit() or len(r) < 8:
                        continue
                    n += 1
                    air = clean(r[1]).replace(",", "")
                    code = clean(r[2])
                    college = clean(r[3])
                    prog, seat = split_course(clean(r[4]))
                    cat = clean(r[5])
                    if not air.isdigit() or not college or not cat:
                        skip += 1
                        continue
                    key = (college, code, cat, prog, seat)
                    buckets[key] = max(buckets.get(key, 0), int(air))
    return buckets, n, skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    buckets, n, skip = parse(args.src)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Institute Code", "Category", "Academic Program Name",
                    "Seat Type", "Round", "Closing Rank", "rank_space"])
        for (college, code, cat, prog, seat), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([college, code, cat, prog, seat, "R3", air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} rows ({skip} skipped)")
    print("  seat types:", dict(Counter(k[4] for k in buckets)))
    print("  colleges:", len({k[0] for k in buckets}), "| categories:", len({k[2] for k in buckets}))


if __name__ == "__main__":
    main()
