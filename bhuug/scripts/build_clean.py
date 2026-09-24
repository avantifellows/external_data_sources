#!/usr/bin/env python3
"""
Build bhuug_fact_cutoffs from BHU's UG admission 2025 allocation summaries.

Built from the team's CSV (Round 1 + Spot Round 2) and CHECKED against both
official PDFs: every (programme, faculty/college, quota, score) row must
appear in the matching PDF, in order. The only tolerated difference is
spacing ("(Maintained by BHU) (Paid Fee Course)" vs "...BHU)(Paid...").

Labels:
- BHU names its own units generically ("Faculty of Arts"), which says
  nothing on its own. `college` carries the university: "Faculty of Arts,
  Banaras Hindu University"; BHU's admitted colleges read "Arya Mahila PG
  College, Varanasi (BHU)" so a "BHU" search finds them. Printed text stays
  in `college_raw`.
- "(Paid Fee Course)" / "(Special Fee Course)" are seat types, not colleges:
  split into `fee_type` ('regular', 'paid', 'special'); `unit` is the
  faculty/college without them.
- programme spelling made consistent ("Science(Honours)" -> "Science
  (Honours)", "(Hons)" -> "(Honours)", "Earth science"); printed text in
  `program_raw`.
- quota -> `category`: UR (general), OBC, SC, ST, EWS, PWD, WARD (BHU
  employees' wards).

Scores are BHU's CUET-based merit score for the programme; the scale
differs by programme, so compare scores only within one programme.

Usage:
  python3 scripts/build_clean.py            # build + write parquet
  python3 scripts/build_clean.py --dry-run  # build + report only
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, RAW, RAW_FILES, TABLES, YEAR

ROUNDS = {"Round 1": 1, "Spot Round 2": 2}
PDF_OF_ROUND = {"Round 1": 0, "Spot Round 2": 1}  # index into RAW_FILES
QUOTA = {"general": "UR", "obc": "OBC", "sc": "SC", "st": "ST", "ews": "EWS",
         "pwd": "PWD", "ward": "WARD"}
BHU = "Banaras Hindu University"
# unit as printed -> (display name, kind, city)
UNITS = {
    "Faculty of Arts": (f"Faculty of Arts, {BHU}", "BHU faculty", "Varanasi"),
    "Faculty of Science": (f"Faculty of Science, {BHU}", "BHU faculty", "Varanasi"),
    "Faculty of Social Sciences": (f"Faculty of Social Sciences, {BHU}", "BHU faculty", "Varanasi"),
    "Faculty of Commerce": (f"Faculty of Commerce, {BHU}", "BHU faculty", "Varanasi"),
    "Faculty of Law": (f"Faculty of Law, {BHU}", "BHU faculty", "Varanasi"),
    "Faculty of Agriculture": (f"Faculty of Agriculture, {BHU}", "BHU faculty", "Varanasi"),
    "Sanskrit Vidya Dharma Vigyan Sankaya": (f"Sanskrit Vidya Dharma Vigyan Sankaya, {BHU}", "BHU faculty", "Varanasi"),
    "Department of Radio-Diagnosis Imaging": (f"Department of Radio-Diagnosis & Imaging, IMS, {BHU}", "BHU faculty", "Varanasi"),
    "Department of Radiotherapy and Radiation Medicine": (f"Department of Radiotherapy & Radiation Medicine, IMS, {BHU}", "BHU faculty", "Varanasi"),
    "Rajiv Gandhi South Campus": (f"Rajiv Gandhi South Campus, {BHU}, Mirzapur", "BHU faculty", "Mirzapur"),
    "Mahila Maha Vidyalaya (Maintained by BHU)": (f"Mahila Maha Vidyalaya, {BHU}", "BHU faculty", "Varanasi"),
    "Arya Mahila PG College": ("Arya Mahila PG College, Varanasi (BHU)", "BHU admitted college", "Varanasi"),
    "Vasanta College for Women": ("Vasanta College for Women, Varanasi (BHU)", "BHU admitted college", "Varanasi"),
    "Vasant Kanya Mahavidyalaya": ("Vasant Kanya Mahavidyalaya, Varanasi (BHU)", "BHU admitted college", "Varanasi"),
    "D.A.V Post Graduate College": ("D.A.V. Post Graduate College, Varanasi (BHU)", "BHU admitted college", "Varanasi"),
}
FEE = re.compile(r"\s*\((Paid|Special) Fee Course\)\s*$")


def fetch_raw() -> None:
    """GCS is canonical; download any raw file missing locally."""
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.local_path.relative_to(RAW.parent)} from {rf.gcs_uri}")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"\)\s+\(", ")(", str(s))).strip()


def pdf_rows(pdf: Path, colleges: list[str]) -> list[tuple]:
    """(programme, college, quota, score) per allotment line, in order.
    The college is found as the longest known college name ending the text
    before the quota — layout spacing between the two columns is unreliable."""
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    line = re.compile(r"^\s*(?P<pc>\S.*?)\s+(?P<q>" + "|".join(QUOTA) + r")\s+(?P<s>\d+(?:\.\d+)?)\s*$")
    out = []
    for l in text.splitlines():
        m = line.match(l)
        if not m:
            continue
        pc = norm(m["pc"])
        col = next((c for c in colleges if pc.endswith(" " + c)), None)
        if col is None:
            raise SystemExit(f"{pdf.name}: no known college ends {pc!r}")
        out.append((pc[:-len(col) - 1].strip(), col, m["q"], round(float(m["s"]), 5)))
    return out


def fix_program(p: str) -> str:
    """Consistent spelling; the printed text stays in program_raw."""
    p = re.sub(r"Science\(", "Science (", p)
    p = p.replace("(Hons)", "(Honours)").replace("Earth science", "Earth Science")
    return p


def build(path: Path) -> pd.DataFrame:
    s = pd.read_csv(path)
    s.columns = ["round", "program", "college", "quota", "score"]
    assert set(s["round"]) <= set(ROUNDS), set(s["round"]) - set(ROUNDS)
    assert set(s.quota) <= set(QUOTA), set(s.quota) - set(QUOTA)
    raw = s.college.map(norm)
    unit = raw.str.replace(FEE, "", regex=True)
    bad = set(unit) - set(UNITS)
    assert not bad, f"unknown units (add to UNITS): {bad}"
    fee = raw.str.extract(FEE)[0].str.lower().fillna("regular")
    return pd.DataFrame({
        "year": YEAR,
        "round": s["round"],
        "round_order": s["round"].map(ROUNDS),
        "program_raw": s.program.map(norm),
        "program": s.program.map(norm).map(fix_program),
        "college_raw": raw,
        "unit": unit,
        "fee_type": fee,
        "college": unit.map(lambda u: UNITS[u][0]),
        "kind": unit.map(lambda u: UNITS[u][1]),
        "city": unit.map(lambda u: UNITS[u][2]),
        "category": s.quota.map(QUOTA),
        "min_score": s.score.astype(float),
    })


def check(df: pd.DataFrame, pdfs: list[Path]) -> None:
    grain = ["round", "program_raw", "college_raw", "category"]
    assert not df.duplicated(grain).any(), "duplicate grain rows"
    colleges = sorted(set(df.college_raw), key=len, reverse=True)
    for rnd, i in PDF_OF_ROUND.items():
        got = pdf_rows(pdfs[i], colleges)
        want = [(r.program_raw, r.college_raw, {v: k for k, v in QUOTA.items()}[r.category],
                 round(r.min_score, 5)) for r in df[df["round"] == rnd].itertuples()]
        if got != want:
            first = next((j for j, (a, b) in enumerate(zip(got, want)) if a != b), min(len(got), len(want)))
            raise SystemExit(f"{rnd}: CSV and PDF differ at row {first} "
                             f"(PDF {len(got)} rows, CSV {len(want)}): "
                             f"{got[first] if first < len(got) else None} vs {want[first] if first < len(want) else None}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Build + report; write nothing")
    args = ap.parse_args()

    fetch_raw()
    df = build(RAW_FILES[2].local_path)
    check(df, [RAW_FILES[0].local_path, RAW_FILES[1].local_path])
    print(f"bhuug_fact_cutoffs: {len(df):,} rows, {df.unit.nunique()} faculties/colleges, "
          f"{df.program.nunique()} programmes; every row matches its round's PDF")
    print("  fee_type:", df.fee_type.value_counts().to_dict())
    if args.dry_run:
        return
    t = TABLES[0]
    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(t.local_path, index=False)
    print(f"  wrote {t.local_path.relative_to(CLEAN.parent)}")


if __name__ == "__main__":
    main()
