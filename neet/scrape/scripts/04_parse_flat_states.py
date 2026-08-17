#!/usr/bin/env python3
"""
Flat per-student NEET 2025 parsers for states whose PDFs extract as clean tables
with the All-India Rank present directly (no state-rank conversion needed):
West Bengal (R1), Madhya Pradesh (R1), Punjab (R2).

Each: cutoff = MAX AIR per (institute, allotted category, program, quota). The
states genuinely differ in column layout, so one CONFIG per state + one generic
pivot. rank_space = 'NEET AIR' for all three.

Usage: 04_parse_flat_states.py <state>            (uses default src/out)
       04_parse_flat_states.py <state> --src X --out Y
       04_parse_flat_states.py --all                (all three)
"""
from __future__ import annotations
import argparse, csv, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "source"
OUT_DIR = ROOT / "extracted_data"

# Per-state column map (0-based indices into the extracted row) + which round.
CONFIGS = {
    # WB: ROUND|AIR|CHOICE|INSTITUTE|COURSE|ALLOTTED QUOTA|ALLOTTED CATEGORY|CAND CAT|STATUS
    "westbengal": dict(ncols=9, air=1, institute=3, course=4, quota=5, category=6, round="R1"),
    # MP: SNO|ROLL|NAME|AI RANK|AISCORE|COMMON|MP STATE|DOMICILE|ELIG CAT|INST TYPE|COURSE|COLLEGE|ALLOTTED CAT
    "mp": dict(ncols=13, air=3, institute=11, course=10, quota=9, category=12, round="R1"),
    # Punjab: Sno|Mno|Roll|NEETRank|Name|Father|Marks|CatApplied|AllotCollege|AllotCourse|AllotQuota|AllotCat|Shifted...
    "punjab": dict(ncols=16, air=3, institute=8, course=9, quota=10, category=11, round="R2"),
}


# Category values that are NOT a real state category — they mark All-India-Quota
# seats surrendered into state counselling. AIQ is covered comprehensively by the
# national file (01_parse_aiq.py), so we drop these from the STATE dataset to keep
# the state category list clean.
NON_STATE_CATEGORIES = {"AIQ", "ALL INDIA", "ALL INDIA QUOTA"}

# Tokens that are a seat QUOTA, not a social category. When one of these lands in
# the category column (some state PDFs put the allotted-quota there), route it to
# the Seat Type and blank the social category — it is an open-to-all pay/quota
# seat, not a reservation. NRI/management ranks running to ~1M are expected for
# these pools and must NOT sit in the category facet (they polluted the per-state
# category dropdown and read as a fake "NRI category").
QUOTA_AS_CATEGORY = {
    "NRI": "NRI Quota",
    "MGMT": "Management Quota", "MANAGEMENT": "Management Quota",
    "MGT": "Management Quota", "PAID": "Management Quota",
}


def clean(s):
    return (s or "").replace("\n", " ").strip()


def norm_program(s):
    # strip dots/spaces so 'M.B.B.S.' and 'B.D.S' normalize like 'MBBS'/'BDS'
    s = clean(s).upper().replace(".", "").replace(" ", "")
    if "BDS" in s:
        return "BDS"
    if "MBBS" in s:
        return "MBBS"
    return None  # not a real program (e.g. 'NOT ALLOTTED') -> row skipped


def parse_state(state, src: Path, out: Path):
    cfg = CONFIGS[state]
    buckets, n, skip = {}, 0, 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables() or []:
                for r in t:
                    if not r or not str(r[0]).strip().isdigit() or len(r) < cfg["ncols"]:
                        if r and str(r[0]).strip().isdigit():
                            skip += 1
                        continue
                    air = clean(r[cfg["air"]]).replace(",", "")
                    inst = clean(r[cfg["institute"]])
                    prog = norm_program(r[cfg["course"]])
                    quota = clean(r[cfg["quota"]])
                    cat = clean(r[cfg["category"]])
                    if not air.isdigit() or not inst or not cat or prog is None:
                        skip += 1
                        continue
                    if cat.upper() in NON_STATE_CATEGORIES:
                        skip += 1  # AIQ seat — covered by the national file
                        continue
                    # A quota marker in the category column is a seat TYPE, not a
                    # social category: move it to quota, neutralize the category.
                    if cat.upper() in QUOTA_AS_CATEGORY:
                        quota = QUOTA_AS_CATEGORY[cat.upper()]
                        cat = "Open"
                    n += 1
                    key = (inst, cat, prog, quota)
                    buckets[key] = max(buckets.get(key, 0), int(air))
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "Category", "Academic Program Name",
                    "Seat Type", "Round", "Closing Rank", "rank_space"])
        for (inst, cat, prog, quota), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([inst, cat, prog, quota, cfg["round"], air, "NEET AIR"])
    print(f"{state}: {len(buckets)} buckets from {n} rows ({skip} skipped) -> {out.name}")
    print("  programs:", dict(Counter(k[2] for k in buckets)),
          "| colleges:", len({k[0] for k in buckets}),
          "| categories:", len({k[1] for k in buckets}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state", nargs="?", choices=list(CONFIGS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--src", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    states = list(CONFIGS) if args.all else [args.state]
    for st in states:
        src = args.src or SRC_DIR / f"{st}.pdf"
        out = args.out or OUT_DIR / f"neet_{st}_2025_cutoffs.csv"
        parse_state(st, src, out)


if __name__ == "__main__":
    main()
