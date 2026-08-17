#!/usr/bin/env python3
"""
Telangana NEET-UG (KNRUHS) 2025 mop-up allotment parser -> closing-rank cutoffs.

Space-aligned TEXT report (no ruled table). Structure:

  COLL :: OMCH - OSMANIA MEDICAL COLLEGE, HYDERABAD   <- section header (college)
  CRS  :: MBBS - ...                                  <- course
  RANK ROLL_NO STUDENT_NAME CAT SX ... <ALLOT-CODE>    <- one row per candidate
  4846 4201306421 BOGGARAPU ... OC M OPEN-GEN-P1

We carry the current college forward from each "COLL ::" header. RANK is the NEET
All India Rank. The trailing ALLOT-CODE encodes the SEAT:
  <category>-<GEN|FEM>-[<sub-pool>-...]-P<phase>
    category : OPEN / BCA..BCE / SC / SC2 / SC3 / ST / MIN ...
    GEN|FEM  : general vs female-reserved seat  (the (W) equivalent)
    sub-pool : OPTIONAL horizontal reservations — PHO (physically handicapped),
               CAP (children of armed personnel), MSM (Muslim-minority), NCC, ...
    P1/P2/P3 : counselling phase

CRITICAL: the sub-pool is a DISTINCT seat pool with its own (much deeper) cutoff.
Folding it into the bare category and taking MAX makes Osmania OPEN close at
439,096 (a PHO seat) when the real OPEN-general mop-up cutoff is ~20,152. So we
keep the sub-pool in the category: "OPEN" stays the general pool, "OPEN (PHO)" /
"OPEN (CAP)" are separate rows at their true ranks. Nothing is trimmed.

Cutoff = MAX AIR per (college, category+sub-pool, is_female). rank_space = 'NEET AIR'.
"""
from __future__ import annotations
import argparse, csv, re, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "telangana.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_telangana_2025_cutoffs.csv"

COLL_RE = re.compile(r"COLL\s*::\s*(\S+)\s*-\s*(.+)$")
DATA_RE = re.compile(r"^(\d+)\s+(\d{10})\s+(.*)$")
# trailing allotment code: CATEGORY-(GEN|FEM)[-<sub-pool>...]-P<n>
# Capture the leading category, the GEN/FEM split, AND the optional sub-pool
# segment(s) in between (PHO/CAP/MSM/NCC/...). The sub-pool must stay in the
# bucket key — collapsing it inflates the base category to the sub-pool's deep
# rank (Osmania OPEN 439k from a PHO seat).
ALLOT_RE = re.compile(r"([A-Z0-9]+)-(GEN|FEM)((?:-[A-Z]+)*)-P(\d+)\s*$")


def parse(src: Path):
    buckets = {}          # (code, name, category, is_female) -> max AIR
    current = None        # (code, name)
    n = skip = 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for raw in (page.extract_text() or "").split("\n"):
                line = raw.strip()
                cm = COLL_RE.search(line)
                if cm:
                    current = (cm.group(1).strip(), cm.group(2).strip())
                    continue
                dm = DATA_RE.match(line)
                if not dm:
                    continue
                air = int(dm.group(1))
                am = ALLOT_RE.search(dm.group(3))
                if not am or not current:
                    skip += 1
                    continue
                base = am.group(1)                     # OPEN / BCB / SC2 / ST / MIN
                is_female = am.group(2) == "FEM"
                sub = am.group(3).strip("-")           # PHO / CAP / MSM / '' (general)
                category = f"{base} ({sub})" if sub else base
                code, name = current
                # Key on the KNRUHS college CODE (unique) so distinct colleges that
                # share a bare display name (e.g. several "GOVT MEDICAL COLLEGE")
                # never merge into one bucket.
                key = (code, name, category, is_female)
                n += 1
                if air > buckets.get(key, 0):
                    buckets[key] = air
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
        # Emit an explicit State column so the assembler trusts this clean name
        # and does NOT run split_institute on it — that heuristic strips 3-word
        # city segments ("... BHADRADRI KOTHAGUDEM") and collapses ~30 distinct
        # "GOVT MEDICAL COLLEGE, <city>" into one bare "GOVT MEDICAL COLLEGE".
        w.writerow(["Institute", "State", "Institute Code", "Category",
                    "Is Female Seat", "Academic Program Name", "Seat Type",
                    "Round", "Closing Rank", "rank_space"])
        for (code, name, cat, female), air in sorted(buckets.items(), key=lambda x: x[1]):
            w.writerow([name, "Telangana", code, cat, "Yes" if female else "No",
                        "MBBS", "State Quota", "MopUp", air, "NEET AIR"])
    print(f"wrote {args.out}: {len(buckets)} buckets ({skip} rows skipped)")
    print("  colleges:", len({(c, nm) for c, nm, *_ in buckets}))
    print("  categories:", dict(Counter(k[2] for k in buckets)))
    print("  female-seat buckets:", sum(1 for k in buckets if k[3]))


if __name__ == "__main__":
    main()
