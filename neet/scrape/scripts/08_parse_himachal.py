#!/usr/bin/env python3
"""
Himachal Pradesh NEET-UG (AMRU) 2025 R3 parser -> closing-rank cutoffs.

Cleanest of the state files: pdfplumber extract_tables gives tidy 8-col rows:
  Sr | Merit No | Application No | Name | Institute Name | All India Rank
     | Admission Type | Allocated Category

Cutoff = MAX AIR per (institute, category, admission-type). PDF line-wrapping
inserts stray spaces into some labels ("Economic aly Weaker Sections",
"Manageme nt Quota") which we normalise. rank_space = 'NEET AIR'.
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
DEFAULT_SRC = ROOT / "source" / "himachal.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_himachal_2025_r3_cutoffs.csv"

# normalise wrap-broken labels -> clean canonical values
# Keys are matched after removing ALL whitespace (PDF wrapping breaks words
# mid-token, e.g. "Economic aly", "Manageme nt"), so match on the despaced form.
# NOTE: 'nri' is deliberately absent — NRI is a seat QUOTA (it appears in the
# Admission Type column as "NRI Quota"), not a social category. An NRI row's
# allocated-category cell just repeats "NRI"; we neutralize it to General below
# so it doesn't pollute the category facet with a fake "NRI category".
CATEGORY_FIX = {
    "economicalyweakersections": "EWS",
    "economicallyweakersections": "EWS",
    "general": "General", "obc": "OBC", "sc": "SC", "st": "ST",
    "nri": "General",
    "childrenofjandkmigrants": "J&K Migrant",
    "singlegirlchild": "Single Girl Child",
}
ADM_FIX = {
    "hpquota": "HP Quota", "managementquota": "Management Quota",
    "nriquota": "NRI Quota",
}


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").replace("\n", " ")).strip()


def _fix(s, table):
    key = re.sub(r"\s+", "", _norm(s)).lower()
    return table.get(key, _norm(s))


def parse(src: Path):
    buckets = {}
    n = skip = 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for tb in page.extract_tables() or []:
                for r in tb:
                    if not r or not str(r[0]).strip().isdigit() or len(r) < 8:
                        continue
                    inst = _norm(r[4])
                    air = _norm(r[5]).replace(",", "")
                    adm = _fix(r[6], ADM_FIX)
                    cat = _fix(r[7], CATEGORY_FIX)
                    if not air.isdigit() or not inst or not cat:
                        skip += 1
                        continue
                    n += 1
                    key = (inst, cat, adm)
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
        w.writerow(["Institute", "Category", "Seat Type",
                    "Academic Program Name", "Round", "Closing Rank", "rank_space"])
        for (inst, cat, adm), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([inst, cat, adm, program_from_name(inst), "R3", air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} rows ({skip} skipped)")
    print("  colleges:", len({k[0] for k in buckets}))
    print("  categories:", dict(Counter(k[1] for k in buckets)))
    print("  admission types:", dict(Counter(k[2] for k in buckets)))


if __name__ == "__main__":
    main()
