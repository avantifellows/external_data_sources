#!/usr/bin/env python3
"""
Gujarat NEET-UG 2025 cutoffs parser.

Gujarat publishes a PRE-COMPUTED "Institutewise Last Rank" grid: one row per
(college, quota), with category as column-groups (OPEN/SC/ST/SE/EW), each group
= Percentile, Score, Rank, MeritNo. We reshape wide -> long: one output row per
(college, quota, category), carrying the closing NEET Rank (AIR) and NEET Score
(Gujarat is also a score->rank calibration source, so we keep score).

Quota codes (Inst.Label suffix): GQ=State/Govt, MQ=Management, NQ=NRI, LQ=other.
rank_space = 'NEET AIR'.

Anchor: AMED (B.J Medical Ahmedabad) OPEN closing rank = 4016 @ score 577.
"""
from __future__ import annotations
import argparse, csv, re, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "gujarat.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_gujarat_2025_cutoffs.csv"

CATEGORIES = ["OPEN", "SC", "ST", "SE", "EW"]      # column-group order in the grid
GROUP_WIDTHS = [4, 5, 5, 5, 5]                      # OPEN=4 cells, others=5
QUOTA = {"GQ": "State Quota", "MQ": "Management Quota", "NQ": "NRI Quota", "LQ": "Other"}


def clean(s):
    return (s or "").replace("\n", " ").strip()


def parse(src: Path):
    out, program = [], None
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for tb in page.extract_tables() or []:
                for r in tb:
                    label = clean(r[0])
                    if label in ("MEDICAL", "DENTAL"):
                        program = "MBBS" if label == "MEDICAL" else "BDS"
                        continue
                    m = re.match(r"^(\S+)\s*-\s*(GQ|MQ|NQ|LQ)$", label)
                    if not m:
                        continue
                    inst_label, quota_code = m.group(1), m.group(2)
                    name = clean(r[1])
                    cells = [clean(c) for c in r[2:]]
                    pos = 0
                    for cat, w in zip(CATEGORIES, GROUP_WIDTHS):
                        grp = cells[pos:pos + w]
                        pos += w
                        if len(grp) < 3:
                            continue
                        pct, score, rank = grp[0], grp[1], grp[2]
                        rank = rank.replace(",", "")
                        if not rank.isdigit() or int(rank) == 0:
                            continue
                        out.append({
                            "Institute": name, "Institute Code": inst_label,
                            "Category": cat, "Academic Program Name": program,
                            "Seat Type": QUOTA[quota_code], "Round": "R3",
                            "Closing Rank": int(rank),
                            "NEET Score": score if score.isdigit() else "",
                            "Percentile": pct, "rank_space": "NEET AIR",
                        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    out = parse(args.src)
    cols = ["Institute", "Institute Code", "Category", "Academic Program Name",
            "Seat Type", "Round", "Closing Rank", "NEET Score", "Percentile", "rank_space"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in sorted(out, key=lambda x: x["Closing Rank"]):
            w.writerow(row)
    print(f"wrote {args.out}: {len(out)} rows")
    print("  programs:", dict(Counter(r["Academic Program Name"] for r in out)))
    print("  quotas:", dict(Counter(r["Seat Type"] for r in out)))
    bj = [r for r in out if r["Institute Code"] == "AMED" and r["Category"] == "OPEN"]
    print("  ANCHOR AMED OPEN:", [(r["Closing Rank"], r["NEET Score"]) for r in bj])


if __name__ == "__main__":
    main()
