#!/usr/bin/env python3
"""
Build clean/tnea_fact_cutoffs.parquet from the two raw portal pulls.

Grain: (year, code, branch, category_raw) — one row per seat bucket that
actually admitted someone. An em-dash cell in the portal means no admission in
that bucket and produces NO row (absence is a fact, not missing data).

Design notes, in the order they bit:
  - TWO METRICS PER ROW, opposite directions (the gujcet precedent):
    cutoff_mark is the TNEA composite out of 200 (HIGHER = harder);
    closing_rank is the TN state merit rank (LOWER = harder).
  - college_type comes from the official DOTE college-code sets in
    ../scrape/scripts/state_TN.py — lifted by regex at build time so the
    scraper file stays the single copy. Codes, never names.
  - (SS) in a branch name = a Self-Supporting section: a costlier
    self-financed stream INSIDE a govt/aided college. Same seat-vs-college
    lesson as NEET — flagged in its own column, never silently mixed.
  - district is derived from the college string (the "X District" tail, a
    spelling-variant map, and a small town map). 415/423 colleges resolve;
    the 8 misses include The Nilgiris, and stay NULL.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import sources as S

CATS = ["OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"]
CANON = {"OC": "GEN", "BC": "OBC", "BCM": "OBC", "MBC": "OBC",
         "SC": "SC", "SCA": "SC", "ST": "ST"}
YEAR = 2025

# ── college_type: lift the DOTE code sets from the scraper (single copy) ──
def load_code_sets():
    src = (S.ROOT / "scrape/scripts/state_TN.py").read_text()
    def grab(name):
        block = src.split(f"{name} = {{")[1].split("}")[0]
        return {int(x) for x in re.findall(r"^\s*(\d+),", block, re.M)}
    govt = (grab("UNIVERSITY_DEPT_CODES") | grab("GOVT_COLLEGE_CODES")
            | grab("CENTRAL_GOVT_INSTITUTE_CODES") | grab("CONSTITUENT_COLLEGE_CODES"))
    return govt, grab("GOVT_AIDED_COLLEGE_CODES")

GOVT_CODES, AIDED_CODES = load_code_sets()

def college_type(code: int) -> str:
    if code in GOVT_CODES:
        return "Govt"
    if code in AIDED_CODES:
        return "Govt-Aided"
    return "Private/SF"

# ── district from the college string ──
DISTS = ["Ariyalur","Chengalpattu","Chennai","Coimbatore","Cuddalore","Dharmapuri",
         "Dindigul","Erode","Kancheepuram","Kanniyakumari","Karur","Krishnagiri",
         "Madurai","Mayiladuthurai","Namakkal","Perambalur","Pudukkottai",
         "Ramanathapuram","Salem","Sivaganga","Thanjavur","Theni","Thiruvallur",
         "Thiruvarur","Thoothukkudi","Tiruchirappalli","Tirunelveli","Tiruppur",
         "Tiruvannamalai","Vellore","Viluppuram","Virudhunagar"]
VAR = {"villupuram":"Viluppuram","villuppuram":"Viluppuram","tuticorin":"Thoothukkudi",
       "thoothukudi":"Thoothukkudi","kanyakumari":"Kanniyakumari","trichy":"Tiruchirappalli",
       "tiruchirapalli":"Tiruchirappalli","kanchipuram":"Kancheepuram","tirupur":"Tiruppur",
       "tiruvallur":"Thiruvallur","thiruvarur":"Thiruvarur","nagapattinam":"Mayiladuthurai",
       "nagappattinam":"Mayiladuthurai","sivagangai":"Sivaganga","pudukottai":"Pudukkottai",
       "tenkasi":"Tirunelveli","ranipet":"Vellore","tirupattur":"Vellore",
       "kallakurichi":"Viluppuram","tanjore":"Thanjavur"}
TOWN = {"karaikudi":"Sivaganga","sriperumbudur":"Kancheepuram","avadi":"Thiruvallur",
        "hosur":"Krishnagiri","poonamallee":"Thiruvallur","gummidipoondi":"Thiruvallur",
        "kavaraipettai":"Thiruvallur","arni":"Tiruvannamalai","guindy":"Chennai",
        "tambaram":"Chengalpattu","chromepet":"Chengalpattu","padur":"Chengalpattu",
        "kelambakkam":"Chengalpattu","vandalur":"Chengalpattu","oragadam":"Kancheepuram",
        "maduravoyal":"Chennai","mamallapuram":"Chengalpattu","pallavaram":"Chengalpattu",
        "perundurai":"Erode","sathyamangalam":"Erode","pollachi":"Coimbatore",
        "sholinganallur":"Chennai"}

def district(name: str) -> str | None:
    n = " " + name.lower().replace(",", " ").replace("-", " ") + " "
    m = re.findall(r"([a-z][a-z. ]{2,28}?)\s+district", n)
    for tok in (m[-1].split()[::-1] if m else []):
        for d in DISTS:
            if d.lower() == tok:
                return d
        if tok in VAR:
            return VAR[tok]
    best, bestpos = None, -1
    for key, d in ([(d.lower(), d) for d in DISTS] + list(VAR.items()) + list(TOWN.items())):
        p = n.rfind(" " + key + " ")
        if p > bestpos:
            bestpos, best = p, d
    return best

# ── build ──
def fetch_raw():
    """raw/ locally, else pull from GCS (the canonical home)."""
    missing = [f for f in S.RAW_FILES if not (S.RAW / f).exists()]
    if missing:
        from google.cloud import storage
        S.RAW.mkdir(parents=True, exist_ok=True)
        b = storage.Client().bucket(S.GCS_BUCKET)
        for f in missing:
            b.blob(f"{S.GCS_PREFIX}/raw/{f}").download_to_filename(S.RAW / f)
            print(f"  fetched raw/{f} from GCS")

def num(v):
    v = str(v or "").replace(",", "").replace("—", "").strip()
    return float(v) if re.fullmatch(r"\d+(\.\d+)?", v) else None

def main():
    fetch_raw()
    marks = pd.read_csv(S.RAW / S.RAW_FILES[0], encoding="utf-8-sig")
    ranks = pd.read_csv(S.RAW / S.RAW_FILES[1], encoding="utf-8-sig")
    for df in (marks, ranks):
        df.columns = [c.strip() for c in df.columns]
    key = ["Code", "College", "Branch"]
    j = marks.merge(ranks, on=key, suffixes=("_mark", "_rank"), validate="1:1")
    assert len(j) == len(marks) == len(ranks), "mark/rank tables disagree on buckets"

    out = []
    for _, r in j.iterrows():
        code = int(r["Code"])
        college = re.sub(r"\s+", " ", str(r["College"])).strip()
        branch = re.sub(r"\s+", " ", str(r["Branch"])).strip()
        ss = "(SS)" in branch
        ct, dist = college_type(code), district(college)
        for cat in CATS:
            mark, rank = num(r[f"{cat}_mark"]), num(r[f"{cat}_rank"])
            if mark is None and rank is None:
                continue                       # em-dash bucket: no admission, no row
            out.append(dict(
                exam_year=YEAR, code=code, college=college, district=dist,
                branch=branch, self_supporting=ss,
                category=CANON[cat], category_raw=cat,
                cutoff_mark=mark, closing_rank=int(rank) if rank is not None else None,
                college_type=ct,
            ))
    df = pd.DataFrame(out)
    df["closing_rank"] = df["closing_rank"].astype("Int64")
    S.CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(S.CLEAN / S.PARQUET, index=False)

    print(f"wrote clean/{S.PARQUET}: {len(df):,} rows")
    print(f"  colleges {df.code.nunique()}  branches {df.branch.nunique()}")
    print(f"  college_type: {df.college_type.value_counts().to_dict()}")
    print(f"  category_raw: {df.category_raw.value_counts().to_dict()}")
    print(f"  self_supporting rows: {int(df.self_supporting.sum())}")
    print(f"  district NULL: {int(df.district.isna().sum())} rows "
          f"({df[df.district.isna()].code.nunique()} colleges)")
    print(f"  mark range {df.cutoff_mark.min()}–{df.cutoff_mark.max()}, "
          f"rank range {df.closing_rank.min()}–{df.closing_rank.max()}")

if __name__ == "__main__":
    main()
