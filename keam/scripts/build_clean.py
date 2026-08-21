#!/usr/bin/env python3
"""
KEAM engineering last ranks, 2025-2026 -> keam/clean/keam_fact_cutoffs.parquet

Parser ported from futures-v2 state_cet/scrape/scripts/state_KL.py (the
June-handoff family), which was written against these exact PDFs: per-course
sections, a 17-column table (code, college, Type, 13 category columns,
free-text Other Categories). KEAM publishes ONLY the closing (last) rank -
there is no opening rank anywhere in the source.

Grain: one row per phase x course x college x category. Every published
phase is kept, including 2026's new 'Trial' (CEE's mock allotment run
before Phase 1) - scope on `phase` when you want "the" cutoff.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sources import ENGG_FILES  # noqa: E402

RAW, CLEAN = ROOT / "raw", ROOT / "clean"

CATEGORY_COLS = ["SM", "EZ", "MU", "LA", "DV", "VK", "BH", "BX", "KN", "KU",
                 "SC", "ST", "EW"]

# Kerala's own vocabulary. SM = State Merit (open); the nine SEBC sub-pools
# are communities, not one OBC bucket; EW = EWS. Sub-codes ride in the
# Other Categories column: FW (fee waiver), YN (Yatheem/orphan), PD (PwD),
# PT (sports), SD (new in 2026, kept verbatim).
def normalise_category(c: str) -> tuple[str, str]:
    c = c.strip().upper()
    if c == "SM":
        return ("GEN", "")
    if c in ("EZ", "MU", "LA", "DV", "VK", "BH", "BX", "KN", "KU"):
        return ("OBC-NCL", c)
    if c == "SC":
        return ("SC", "")
    if c == "ST":
        return ("ST", "")
    if c == "EW":
        return ("EWS", "")
    return ("OTHER", c)


def parse_engg_pdf(path: Path, year: int, phase: str) -> list[dict]:
    rows: list[dict] = []
    # current_course carries ACROSS pages: a course's table often spills onto
    # the next page with no repeated header, and resetting per page (as the
    # futures-v2 parser did) orphans those rows to course=None - which then
    # collide as duplicates when two spilled courses share a college.
    current_course = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r:
                        continue
                    # course header: single populated leading cell
                    if r[0] and not r[2] and not (len(r) > 3 and r[3]):
                        current_course = (r[0] or "").strip()
                        continue
                    if r[0] in ("Name of College", None) and any(c == "SM" for c in r[2:5]):
                        continue
                    code = (r[0] or "").strip()
                    if not (2 <= len(code) <= 6 and code.replace("/", "").isalnum()):
                        continue
                    name = (r[1] or "").replace("\n", " ").strip()
                    coll_type = (r[2] or "").strip().upper()
                    if coll_type not in ("G", "S"):
                        continue
                    base = {
                        "exam_year": year,
                        "phase": phase,
                        "course": current_course,
                        "college_code": code,
                        "college_name": name,
                        "college_type_raw": coll_type,
                        # Kerala's Type column collapses Govt + Govt-Aided into 'G'
                        "college_type": "Govt" if coll_type == "G" else "Private/SF",
                    }
                    for i, cat in enumerate(CATEGORY_COLS):
                        v = ((r[3 + i] or "") if 3 + i < len(r) else "").strip()
                        if not v or v in ("-", "--"):
                            continue
                        try:
                            rank = int(v.replace(",", ""))
                        except ValueError:
                            continue
                        canon, sub = normalise_category(cat)
                        rows.append({**base, "category_raw": cat, "category": canon,
                                     "sub_pool": sub, "closing_rank": rank})
                    if len(r) > 16 and r[16]:
                        for m in re.finditer(r"([A-Z]{1,3}):(\d+)", r[16]):
                            canon, sub = normalise_category(m.group(1))
                            rows.append({**base, "category_raw": m.group(1),
                                         "category": canon, "sub_pool": sub,
                                         "closing_rank": int(m.group(2))})
    return rows


def main() -> None:
    CLEAN.mkdir(exist_ok=True)
    all_rows: list[dict] = []
    for fname, year, phase in ENGG_FILES:
        rows = parse_engg_pdf(RAW / fname, year, phase)
        print(f"  {fname:32s} {year} {phase:6s}: {len(rows):6,} rows")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df["closing_rank"] = df["closing_rank"].astype("int64")

    key = ["exam_year", "phase", "course", "college_code", "category_raw"]
    dupes = df.duplicated(key).sum()
    assert dupes == 0, f"{dupes} duplicate buckets"

    print(f"\n  total {len(df):,} rows | years {sorted(df.exam_year.unique())}")
    print("  phases:", df.groupby(['exam_year', 'phase']).size().to_dict())
    print("  college_type:", df.college_type.value_counts().to_dict())
    print("  category_raw:", sorted(df.category_raw.unique()))

    # anchor: CET Thiruvananthapuram (TVE) CSE, SM - Kerala's hardest seat
    a = df[(df.college_code == "TVE") & df.course.str.contains("Computer Science", na=False)
           & (df.category_raw == "SM") & (df.phase == "P2")]
    print("\n  anchor TVE CSE SM @P2:", a[["exam_year", "closing_rank"]].to_dict("records"))

    out = CLEAN / "keam_fact_cutoffs.parquet"
    df.to_parquet(out, index=False)
    print(f"\n  -> {out} ({out.stat().st_size:,}B)")


if __name__ == "__main__":
    main()
