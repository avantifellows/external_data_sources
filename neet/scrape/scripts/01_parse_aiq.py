#!/usr/bin/env python3
"""
AIQ (All India Quota / MCC) NEET-UG 2025 cutoffs — CORRECT version (v2).

Source: the R1 seat-allotment result (aiq_r1.pdf), a flat 8-col ledger with one
row per allotted candidate:

    SNo | AIR | Quota | Institute | Course | SeatCategory | CandCategory | Status

WHY R1 ALONE (no R3 union anymore):
  The R1 result already carries EVERY allotted candidate WITH their seat category
  and candidate category, so it is a complete, category-labelled baseline. The
  old code also folded in the R3 "journey ledger" (aiq.pdf) via a fragile
  16-col semantic parse; that added nothing correct and mis-attributed high-AIR
  rows, so it is dropped.

THE BUG THIS FIXES (Open closing wildly too high, e.g. AIIMS Delhi Open 9332,
MAMC Open 1,031,573):
  The MCC AIQ file mixes MULTIPLE seat POOLS under column 3 "Quota":
    - 'Open Seat Quota'        -> the 15% All-India national merit pool
    - 'All India'              -> central/deemed-university AIQ seats
    - 'Delhi University Quota' / 'IP University Quota'  -> Delhi-domicile 85% pool
      (MCC runs 100% counselling for Delhi colleges: 15% AIQ + 85% DU/IP)
    - 'Deemed/Paid Seats Quota', 'Foreign Country Quota', 'Internal-...'  -> niche
  The old parser ignored the Quota column and pooled every quota into one
  category bucket, taking MAX AIR. So AIIMS Delhi's Open closing absorbed its 7
  Foreign-Country-Quota rows (AIR up to 9332) and MAMC's Open absorbed its 85%
  Delhi-University-Quota rows (AIR up to ~1M). Real published AIQ cutoffs
  (AIIMS Delhi Open 48, MAMC Open 103) come from 'Open Seat Quota'/'All India'
  ONLY. We now keep the Quota as the Seat Type and bucket per quota, so each
  pool's closing rank is separate and correct.

OTHER FIXES:
  - Bucket key uses the CLEAN institute name (+ state), not the raw address blob,
    so PDF line-wrap typos in the address/email ('CIV IL'->'CIVIL',
    'g mail.com'->'gmail.com') no longer split one college into two buckets.
  - A seat annotation that rode on the pincode ('110095 (Female Seat only)')
    is parsed out into its own 'Seat Note' column instead of corrupting State.

Closing rank per (clean institute, state, seat type, seat category, course)
    = MAX AIR.  rank_space = 'NEET AIR' (national).
"""
from __future__ import annotations
import csv, sys, warnings
from collections import defaultdict
from pathlib import Path
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _institute import split_institute

warnings.filterwarnings("ignore")
_ROOT = Path(__file__).resolve().parent.parent  # neet/scrape/
R1 = sys.argv[1] if len(sys.argv) > 1 else str(_ROOT / "source" / "aiq_r1.pdf")
OUT = sys.argv[2] if len(sys.argv) > 2 else str(_ROOT / "extracted_data" / "neet_aiq_2025_cutoffs.csv")

# Social/reservation categories, as they appear in the SEAT-category column (col5).
CATEGORIES = {"Open", "OBC", "EWS", "SC", "ST",
              "Open PwD", "OBC PwD", "EWS PwD", "SC PwD", "ST PwD"}

# The AIQ file mixes ~25 distinct seat POOLS under column 3 "Quota". Only the
# genuine national merit pools are the "All India Quota" cutoffs a student
# anywhere compares against; every other pool is domicile- or institution-
# restricted (Delhi/IP/Puducherry domicile; AMU/Jamia internal; Jain/Muslim
# minority; ESI; deemed/paid; foreign). We keep the Quota as the Seat Type and
# bucket per-quota, so a restricted pool's (looser) ranks never contaminate the
# AIQ cutoff. The generator promotes only NATIONAL_POOLS into the served data.
NATIONAL_POOLS = {
    "Open Seat Quota",
    "All India",
    "B.Sc Nursing All India",
    "(AMU) Self finance All India",
}


def clean(s):
    return (s or "").replace("\n", " ").strip()


def norm_course(s):
    s = clean(s).upper()
    if s.startswith("B.SC") or "NURSING" in s:
        return "BSc Nursing"
    return "BDS" if s.startswith("BDS") else "MBBS"


def seat_type_for(quota):
    """National merit pools collapse to the single 'All India' seat type; every
    other pool keeps its raw quota text as a distinct seat type (so nothing is
    silently dropped and nothing contaminates the AIQ cutoff)."""
    return "All India" if quota in NATIONAL_POOLS else (quota or "All India")


def parse_r1(path):
    """Return buckets[(name, state, seat_type, seat_cat, course)] -> (max_air, note).

    Layout: [SNo, AIR, Quota, Institute, Course, SeatCat, CandCat, Status].
    """
    buckets = {}
    n = skip = 0
    quotas_seen = defaultdict(int)
    with pdfplumber.open(path) as pdf:
        for pi in range(2, len(pdf.pages)):  # skip legend pages 0-1
            for t in pdf.pages[pi].extract_tables() or []:
                for r in t:
                    if not r or not str(r[0]).strip().isdigit() or len(r) < 8:
                        continue
                    air = clean(r[1]).replace(",", "")
                    quota = clean(r[2])
                    inst_raw = clean(r[3])
                    course = norm_course(r[4])
                    seat_cat = clean(r[5])
                    if not air.isdigit() or not inst_raw or seat_cat not in CATEGORIES:
                        skip += 1
                        continue
                    air = int(air)
                    name, address, state, note = split_institute(inst_raw)
                    seat_type = seat_type_for(quota)
                    quotas_seen[quota] += 1
                    key = (name, state, seat_type, seat_cat, course)
                    prev = buckets.get(key)
                    if prev is None or air > prev[0]:
                        buckets[key] = (air, note or (prev[1] if prev else ""))
                    n += 1
    return buckets, n, skip, quotas_seen


def main():
    buckets, n, skip, quotas_seen = parse_r1(R1)
    print(f"R1: {n:,} rows used ({skip} skipped); {len(buckets):,} buckets")
    print("  quota distribution:")
    for q, c in sorted(quotas_seen.items(), key=lambda x: -x[1]):
        print(f"    {c:7,}  {q!r} -> seat type {seat_type_for(q)!r}")

    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "State", "Seat Note", "Category",
                    "Academic Program Name", "Seat Type", "Round",
                    "Closing Rank", "rank_space"])
        for (name, state, seat_type, cat, course), (air, note) in sorted(
            buckets.items(), key=lambda x: x[1][0]
        ):
            w.writerow([name, state, note, cat, course, seat_type,
                        "R1", air, "NEET AIR"])
    print(f"wrote {OUT}: {len(buckets):,} buckets")

    # anchors: must match published cutoffs now
    print("\nANCHORS (All India seat type, MBBS):")
    for want in ("AIIMS, New Delhi", "Maulana Azad", "MADRAS MEDICAL"):
        print(f"  {want}:")
        for (name, state, st, cat, course), (air, _) in sorted(buckets.items()):
            if want.upper() in name.upper() and course == "MBBS" and st == "All India":
                print(f"     {cat:10} = {air:,}")


if __name__ == "__main__":
    main()
