#!/usr/bin/env python3
"""
Normalise the JAC Chandigarh cutoff sheet into jacchd_fact_cutoffs.

The sheet is already tabular (Round, Institute, Program, Quota, Category,
Opening Rank, Closing Rank), so this is mostly labelling:

- " - TFW" on a programme is the tuition-fee-waiver seat pool, not a
  branch: split into `tfw`, programme keeps the branch. (Only the EWS
  tuition-fee-waiver category ever sits on a TFW programme; asserted.)
- category_raw is kept verbatim; `category` is a short canonical code.
  The Defence and Sports lists print positions in their own merit list
  (1-318, some with decimals like 281.1), not JEE ranks.
- rank_basis says which scale a row's ranks are on: 'JEE Main Paper 1'
  (B.E.), 'JEE Main Paper 2' (CCA's B.Arch), or 'category merit list'.
  Never compare ranks across bases.

Usage:
  python3 scripts/build_clean.py            # build + write parquet
  python3 scripts/build_clean.py --dry-run  # build + report only
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, RAW, RAW_FILES, TABLES, YEAR

ROUND_ORDER = {"Round 1": 1, "Round 2": 2, "Round 3": 3,
               "Special Round": 4, "SPOT Round": 5}

INSTITUTES = {  # as printed -> (short name, city, state)
    "Chandigarh College of Engineering & Technology, Chandigarh":
        ("CCET", "Chandigarh", "Chandigarh"),
    "Chandigarh College of Architecture, Chandigarh":
        ("CCA", "Chandigarh", "Chandigarh"),
    "University Institute of Engineering and Technology, Panjab University, Chandigarh":
        ("UIET Chandigarh", "Chandigarh", "Chandigarh"),
    "Dr. S.S. Bhatnagar University Institute of Chemical Engineering and Technology, Panjab University, Chandigarh":
        ("Dr. SSB UICET", "Chandigarh", "Chandigarh"),
    "University Institute of Engineering and Technology, PUSSG Regional Centre, Hoshiarpur":
        ("UIET Hoshiarpur", "Hoshiarpur", "Punjab"),
}

# first matching pattern wins; order matters (PwD / Defence before plain SC)
CATEGORY_RULES = [
    (r"^Backward Classes-PwD", "OBC-PWD"),
    (r"PwD", "PWD"),
    (r"^Open-Defence", "GEN-DEFENCE"),
    (r"^OPEN EWS-Defence", "EWS-DEFENCE"),
    (r"^Backward Classes-Defence", "OBC-DEFENCE"),
    (r"^SC-Defence", "SC-DEFENCE"),
    (r"^Defence Personel", "DEFENCE"),
    (r"Sports Person", "SPORTS"),
    (r"Tuition Fee Waiver", "EWS-TFW"),
    (r"^OPEN EWS$", "EWS"),
    (r"^OPEN$", "GEN"),
    (r"^(OBC|BC) for", "OBC"),
    (r"^SC$", "SC"),
    (r"^ST$", "ST"),
    (r"^Rural Area", "RURAL"),
    (r"^Border Area", "BORDER"),
    (r"^One Girl Child", "GIRL-CHILD"),
    (r"^Kashmiri Migrant", "KM"),
    (r"^Wards of Regular Employees of Panjab University", "PU-WARD"),
    (r"^Orphan", "ORPHAN"),
    (r"Freedom Fighters", "FREEDOM-FIGHTER"),
    (r"^Thalassemia", "THALASSEMIA"),
    (r"^Cancer", "CANCER"),
]
MERIT_LIST = {"GEN-DEFENCE", "EWS-DEFENCE", "OBC-DEFENCE", "SC-DEFENCE",
              "DEFENCE", "SPORTS"}


def fetch_raw() -> None:
    """GCS is canonical; download the raw sheet if it is missing locally."""
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.local_path.relative_to(RAW.parent)} from {rf.gcs_uri}")


def category_of(raw: str) -> str:
    for pat, code in CATEGORY_RULES:
        if re.search(pat, raw):
            return code
    raise SystemExit(f"unmapped category: {raw!r} — add a CATEGORY_RULES entry")


def degree_of(programme: str) -> str:
    if programme.startswith("Integrated B.E."):
        return "Integrated B.E.-MBA"
    if programme.startswith("Bachelor of Architecture"):
        return "B.Arch"
    if programme.startswith("B.E."):
        return "B.E."
    raise SystemExit(f"unknown degree: {programme!r}")


def build(path: Path) -> pd.DataFrame:
    s = pd.read_csv(path, dtype=str).apply(lambda c: c.str.strip())
    assert list(s.columns) == ["Round", "Institute", "Program", "Quota", "Category",
                               "Opening Rank", "Closing Rank"], s.columns.tolist()
    bad = set(s.Round) - set(ROUND_ORDER)
    assert not bad, f"unknown rounds: {bad}"
    bad = set(s.Institute) - set(INSTITUTES)
    assert not bad, f"unknown institutes: {bad}"

    tfw = s.Program.str.endswith(" - TFW")
    df = pd.DataFrame({
        "year": YEAR,
        "round": s.Round,
        "round_order": s.Round.map(ROUND_ORDER),
        "institute": s.Institute,
        "institute_short": s.Institute.map(lambda x: INSTITUTES[x][0]),
        "city": s.Institute.map(lambda x: INSTITUTES[x][1]),
        "state": s.Institute.map(lambda x: INSTITUTES[x][2]),
        "programme_raw": s.Program,
        "programme": s.Program.str.replace(r" - TFW$", "", regex=True),
        "tfw": tfw,
        "quota": s.Quota,
        "category_raw": s.Category,
        "category": s.Category.map(category_of),
        "opening_rank": pd.to_numeric(s["Opening Rank"], errors="raise"),
        "closing_rank": pd.to_numeric(s["Closing Rank"], errors="raise"),
    })
    df["degree"] = df.programme.map(degree_of)
    df["rank_basis"] = [
        "category merit list" if c in MERIT_LIST
        else "JEE Main Paper 2" if d == "B.Arch"
        else "JEE Main Paper 1"
        for c, d in zip(df.category, df.degree)]
    return df


def check(df: pd.DataFrame) -> None:
    grain = ["round", "institute", "programme_raw", "quota", "category_raw"]
    dup = df.duplicated(grain).sum()
    assert dup == 0, f"{dup} duplicate {grain} rows"
    assert set(df.quota) <= {"All India", "Home State", "Other State"}, set(df.quota)
    assert (df.opening_rank <= df.closing_rank).all(), "opening rank after closing rank"
    assert (df.closing_rank > 0).all(), "non-positive rank"
    # TFW programmes carry only the EWS fee-waiver category, and vice versa
    assert (df.tfw == (df.category == "EWS-TFW")).all(), "TFW pool / category mismatch"
    merit = df.rank_basis == "category merit list"
    assert df[merit].closing_rank.max() < 1000, "merit-list position looks like a JEE rank"
    assert df[~merit].closing_rank.min() >= 1, "rank below 1"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Build + report; write nothing")
    args = ap.parse_args()

    fetch_raw()
    df = build(RAW_FILES[0].local_path)
    check(df)
    print(f"jacchd_fact_cutoffs: {len(df):,} rows, {df.institute.nunique()} institutes, "
          f"{df.programme.nunique()} programmes, {df['round'].nunique()} rounds")
    print("  rank_basis:", df.rank_basis.value_counts().to_dict())
    print("  category:", df.category.value_counts().to_dict())
    if args.dry_run:
        return
    t = TABLES[0]
    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(t.local_path, index=False)
    print(f"  wrote {t.local_path.relative_to(CLEAN.parent)}")


if __name__ == "__main__":
    main()
