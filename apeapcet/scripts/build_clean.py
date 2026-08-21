#!/usr/bin/env python3
"""
AP EAPCET 2025 consolidated last ranks -> apeapcet_fact_cutoffs.parquet

Source: APSCHE's 60-page "APEAPCET-2025 ADMISSIONS LAST RANK DETAILS" —
one row per college x branch, 22 rank columns (11 categories x 2 genders),
melted here to long. LAST rank only (no opening rank exists).

Category vocabulary (2025): OC, SC-I/II/III (AP implemented SC
sub-classification in 2025 — 2022's single SC column is gone), ST,
BC-A..BC-E, OC_EWS; each x BOYS/GIRLS. Two footnotes from the source that
matter downstream:
  - "Girls are also eligible for Boys seats": the BOYS column is in effect
    the open-to-all pool; GIRLS is the 33% women's-reservation pool.
  - The Convener marks the table as informational, "shall in no way reflect
    the rank upto which seat can be allotted in the present academic year".

college_type comes from the source's own `type` column, decoded empirically
(no name heuristics): UNIV = government university constituent colleges
(AU/SVU/JNTU campuses, agri colleges); SF / SS = self-finance /
self-supporting seat pools INSIDE those campuses (same college, higher
fees — TNEA's (SS) lesson); PVT = private unaided; PU = private university.
branch_code stays verbatim (the source ships no code->name legend; display
names are a UI concern, not warehouse data).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sources import RAW_FILES  # noqa: E402

RAW, CLEAN = ROOT / "raw", ROOT / "clean"

RANK_COLS = ["OC_BOYS", "OC_GIRLS", "SCI_BOYS", "SCI_GIRLS", "SCII_BOYS",
             "SCII_GIRLS", "SCIII_BOYS", "SCIII_GIRLS", "ST_BOYS", "ST_GIRLS",
             "BCA_BOYS", "BCA_GIRLS", "BCB_BOYS", "BCB_GIRLS", "BCC_BOYS",
             "BCC_GIRLS", "BCD_BOYS", "BCD_GIRLS", "BCE_BOYS", "BCE_GIRLS",
             "OC_EWS_BOYS", "OC_EWS_GIRLS"]

TYPE_MAP = {"UNIV": "Univ-Govt", "SF": "Univ-SelfFin", "SS": "Univ-SelfSup",
            "PVT": "Private", "PU": "Private-Univ"}


def canon(cat: str) -> tuple[str, str]:
    if cat == "OC":
        return ("GEN", "")
    if cat == "OC_EWS":
        return ("EWS", "")
    if cat in ("SCI", "SCII", "SCIII"):
        return ("SC", cat)                      # AP's 2025 SC sub-classification
    if cat == "ST":
        return ("ST", "")
    if cat.startswith("BC"):
        return ("OBC-NCL", cat)                 # AP's BC sub-list, not central OBC
    return ("OTHER", cat)


def main() -> None:
    CLEAN.mkdir(exist_ok=True)
    fname, _, year = RAW_FILES[0]
    rows: list[dict] = []
    with pdfplumber.open(RAW / fname) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or not (r[0] or "").strip().isdigit():
                        continue
                    assert len(r) == 30, f"unexpected column count {len(r)}"
                    type_raw = (r[3] or "").strip()
                    base = {
                        "exam_year": year,
                        "college_code": (r[1] or "").strip(),
                        "college_name": (r[2] or "").replace("\n", " ").strip(),
                        "type_raw": type_raw,
                        "college_type": TYPE_MAP[type_raw],
                        "inst_region": (r[4] or "").strip(),
                        "district": (r[5] or "").strip(),
                        "local_area": (r[6] or "").strip(),
                        "branch_code": (r[7] or "").strip(),
                    }
                    for i, col in enumerate(RANK_COLS):
                        v = (r[8 + i] or "").strip()
                        if not v:
                            continue
                        cat, gender = col.rsplit("_", 1)
                        c, sub = canon(cat)
                        rows.append({**base, "category_raw": col,
                                     "category_code": cat, "category": c,
                                     "sub_pool": sub, "gender": gender.title(),
                                     "closing_rank": int(v)})

    df = pd.DataFrame(rows)
    # local_area IS part of the grain: private universities (PU) publish one
    # row per local-area pool (AU and SVU) per branch, with different ranks.
    key = ["college_code", "branch_code", "local_area", "category_raw"]
    dupes = df.duplicated(key).sum()
    assert dupes == 0, f"{dupes} duplicate buckets"

    print(f"  {len(df):,} rows | {df.college_code.nunique()} colleges | "
          f"{df.branch_code.nunique()} branches")
    print("  type:", df.type_raw.value_counts().to_dict())
    print("  gender:", df.gender.value_counts().to_dict())

    # anchor: AU College of Engineering CSE, OC Boys - AP's marquee public seat
    a = df[(df.college_code == "AUCE") & (df.branch_code == "CSE")
           & (df.category_raw == "OC_BOYS")]
    print("  anchor AUCE CSE OC_BOYS:", a.closing_rank.tolist())

    out = CLEAN / "apeapcet_fact_cutoffs.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out} ({out.stat().st_size:,}B)")


if __name__ == "__main__":
    main()
