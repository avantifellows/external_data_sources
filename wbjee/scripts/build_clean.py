#!/usr/bin/env python3
"""
Build clean/wbjee_fact_cutoffs.parquet from the raw OR-CR HTML reports.

Grain: (year, round, institute, program, seat_type, quota, category_raw) —
every published bucket, every round, verbatim. No aggregation: the fact table
is the truth; consumers pick rounds.

college_type is ported from the audited futures-v2 state_WB classifier:
name-pattern govt matching is acceptable HERE because West Bengal's government
engineering colleges literally carry "Government" in their names (including
WBJEEB's own recurring typo "Goverment"), state public universities are a
short exhaustive list, and the private-deemed list guards the generic
"University" match. This is a whitelist, not fuzzy matching.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import sources as S

# ── college_type (ported verbatim from futures-v2 state_cet/scrape/state_WB.py) ──
WB_STATE_PUB_UNIVS = [
    "Jadavpur University", "University of Calcutta", "University Of Calcutta",
    "Calcutta University", "Maulana Abul Kalam Azad University of Technology",
    "MAKAUT", "Aliah University", "Indian Institute of Engineering Science",
    "IIEST", "Kaji Nazrul University", "University of Kalyani",
    "UNIVERSITY OF KALYANI", "University Institute of Technology, Burdwan University",
    "UNIVERSITY INSTITUTE OF TECHNOLOGY, BURDWAN UNIVERSITY",
    "West Bengal University of Animal",
]
WB_PRIVATE_DEEMED = [
    "Adamas University", "BRAINWARE UNIVERSITY", "JIS University", "Jis University",
    "Seacom Skills University", "Sister Nivedita University", "Swami Vivekananda University",
    "THE NEOTIA UNIVERSITY", "The Neotia University", "Techno India University",
    "Amity University", "Sharda University", "Lovely Professional", "Vidyamandir",
]


def college_type(name: str) -> str:
    if not name:
        return None
    upper = name.upper()
    if any(p.upper() in upper for p in WB_PRIVATE_DEEMED):
        return "Private/Deemed"
    for p in WB_STATE_PUB_UNIVS:
        if p.upper() in upper:
            return "State-Univ-Dept"
    if re.search(r"\b(GOVERNMENT|GOVT\.?|GOVERMENT)\b.*\b(COLLEGE OF (ENGINEERING|ENGG)|ENGINEERING COLLEGE|ENGINEERING AND MANAGEMENT)\b", upper):
        return "Govt"
    if re.search(r"^(COOCH BEHAR|JALPAIGURI|ALIPURDUAR|KALYANI|MURSHIDABAD|RAMKRISHNA)\s+(GOVERNMENT|GOVERMENT)", upper):
        return "Govt"
    if re.search(r"^(GOVERNMENT|GOVERMENT)\s", upper):
        return "Govt"
    if "MURSHIDABAD COLLEGE OF ENGINEERING" in upper:
        return "Govt-Aided"
    return "Private/SF"


def normalise_category(c: str) -> tuple[str, str]:
    """category_raw -> (canonical, sub_pool). 2026 merged OBC-A/OBC-B into 'OBC';
    both vocabularies map here, each year's raw string preserved elsewhere."""
    c = str(c).strip()
    pwd = "(PwD)" in c
    base = c.replace("(PwD)", "").strip()
    if base == "Open":
        return ("GEN", "PwD" if pwd else "")
    if base == "EWS":
        return ("EWS", "PwD" if pwd else "")
    if base in ("OBC", "OBC - A", "OBC - B"):
        sub = {"OBC - A": "OBC-A", "OBC - B": "OBC-B"}.get(base, "")
        return ("OBC-NCL", (sub + (" PwD" if pwd else "")).strip())
    if base == "SC":
        return ("SC", "PwD" if pwd else "")
    if base == "ST":
        return ("ST", "PwD" if pwd else "")
    if base == "Tuition Fee Waiver":
        return ("OTHER", "TFW")
    return ("OTHER", c)


def main():
    frames = []
    for y in S.YEARS:
        df = pd.read_html(S.RAW / f"WBJEE_{y}_ORCR.html", attrs={"id": "ORCRGridView"})[0]
        n_source = len(df)
        df.columns = [str(c).strip() for c in df.columns]
        if "Seat Type" not in df.columns:      # 2021: the split began in 2022
            df["Seat Type"] = None
        out = pd.DataFrame({
            "exam_year": y,
            "round": df["Round"].astype(str).str.strip(),
            "institute": df["Institute"].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
            "program": df["Program"].astype(str).str.strip(),
            "stream": df["Stream"].astype(str).str.strip(),
            "seat_type": df["Seat Type"],
            "quota": df["Quota"].astype(str).str.strip(),
            "category_raw": df["Category"].astype(str).str.strip(),
            "opening_rank": pd.to_numeric(df["Opening Rank"], errors="coerce"),
            "closing_rank": pd.to_numeric(df["Closing Rank"], errors="coerce"),
        })
        # 2021 additionally encodes TFW in the PROGRAM string ("... - TFW", "(TFW)")
        # while later years use the Category column; one boolean covers both.
        tfw_in_program = out["program"].str.contains(r"\bTFW\b", regex=True)
        cats = out["category_raw"].map(normalise_category)
        out["category"] = cats.map(lambda t: t[0])
        out["sub_pool"] = cats.map(lambda t: t[1])
        out["tfw"] = tfw_in_program | (out["category_raw"] == "Tuition Fee Waiver")
        out["college_type"] = out["institute"].map(college_type)
        assert len(out) == n_source, f"{y}: lost rows in transform"
        frames.append(out)
        print(f"  {y}: {len(out):5} rows, {out.institute.nunique():3} institutes, "
              f"rounds={out['round'].nunique()}, govt-scope rows="
              f"{(out.college_type.isin(['Govt','Govt-Aided','State-Univ-Dept'])).sum()}")

    df = pd.concat(frames, ignore_index=True)
    dupes = df.duplicated().sum()
    assert dupes == 0, f"{dupes} exact duplicate rows"    # the KCET lesson
    # One fractional rank in six years: Jadavpur ECE, 2021 Round 3, Home State
    # Open — WBJEEB's report prints Opening Rank "66.1" (closing is a clean 161).
    # A data-entry stray in the source; rounded, and the only row it touches.
    df["opening_rank"] = df["opening_rank"].round().astype("Int64")
    df["closing_rank"] = df["closing_rank"].round().astype("Int64")
    S.CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(S.CLEAN / S.PARQUET, index=False)
    print(f"\nwrote clean/{S.PARQUET}: {len(df):,} rows, {df.exam_year.nunique()} years")
    print("  category_raw by year (the 2026 OBC merge, visible):")
    for y in (2025, 2026):
        obc = sorted(df[(df.exam_year == y) & (df.category == 'OBC-NCL')].category_raw.unique())
        print(f"    {y}: {obc}")


if __name__ == "__main__":
    main()
