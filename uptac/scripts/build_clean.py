#!/usr/bin/env python3
"""
Parse the UPTAC OR-CR pages (raw/pages/*.html) into uptac_fact_cutoffs.

One row per grid row: round x institute x programme x branch x category x
seat gender, with opening / closing rank (and min / max score where the
programme is score-based). "-" means no one was allotted that cell in that
round; such rows are KEPT with NULL ranks (the seat exists) and
allotted = FALSE.

Labels (from UPTAC's 2025-26 Information Brochure, §5):
- category code = parent + sub-category, e.g. OPGL, SCPH:
    parent: OP (open), BC (OBC from U.P.), SC, ST, EWS (all "from U.P.")
    sub:    NO (none), GL (female from U.P., up to 20%), FF (dependants of
            freedom fighters, 2%), AF (children of defence personnel, 5%),
            PH (divyangjan, 5%)
  plus TFW (tuition fee waiver). Split into parent_category /
  sub_category; category_raw keeps the code.
- branch suffixes are seat pools, not branches: "(Shift I)" / "(Shift II)"
  -> shift; "(FW)" -> tfw. `branch` is the name without them.
- institute display names: UPTAC prints most in capitals with clipped
  words ("MARATHWADA INSTT. OF TECHNOLOGY,BULANDSHAHAR") and some cities
  twice; `institute` is readable, `institute_raw` is as printed.
- seat pools in branch names ("(Self Finance)", "(Collaboration & Twining
  Program)") -> seat_pool; two typos fixed ("Techonology").
- rank_basis: 'JEE Main rank' (B.Tech rounds 1-4, and the special round's
  JEE seats), 'UPTAC round merit rank' (remark "UPTAC ROUND III/VI RANK":
  seats filled on Class 12 marks, CUET, NATA, JEE Paper 2 — UPTAC's own
  list, scores in min/max_score), 'unspecified' (no exam named). Never
  compare ranks across bases.
- rounds: round_label as printed ("R1: First Round"); round_no from it.

Checks: every page parses to 13 cells a row; Sr.No runs 1..N with no gap
or repeat; the grain is unique.

Usage:
  python3 scripts/build_clean.py            # parse + write parquet
  python3 scripts/build_clean.py --dry-run  # parse + report only
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, GCS_PREFIX, PAGES, RAW, TABLES, YEAR

COLS = ["sr_no", "round_label", "institute", "programme", "branch_raw", "category_raw",
        "seat_gender", "exam", "opening_rank", "closing_rank", "min_score", "max_score", "remark"]
PARENTS = ("EWS", "OP", "BC", "SC", "ST")  # EWS first: "EWSAF" must not read as E + WSAF
SUBS = {"NO": None, "GL": "Female (UP)", "FF": "Freedom fighter dependant",
        "AF": "Defence personnel ward", "PH": "Divyangjan"}
SHIFT = re.compile(r"\s*\((Shift\s+[IV]+)\)", re.I)
FW = re.compile(r"\s*\(FW\)\s*$")
# seat pools that ride in the branch name
POOLS = {"Self Finance": "Self finance", "Collaboration & Twining Program": "Collaboration / twinning"}
POOL = re.compile(r"\s*\((" + "|".join(re.escape(k) for k in POOLS) + r")\)")
BRANCH_FIX = [("Techonology", "Technology"), ("& data Science", "& Data Science")]
# display names: UPTAC prints most institutes in capitals with clipped words
ABBREV = {"ENGG": "Engineering", "ENGG.": "Engineering", "ENGINEERIN": "Engineering",
          "INSTT.": "Institute", "INSTT": "Institute", "INST.": "Institute", "TECH.": "Technology", "TECH": "Technology",
          "MGMT": "Management", "MGMT.": "Management", "MGT.": "Management", "SC.": "Science",
          "&": "&", "OF": "of", "AND": "and", "FOR": "for", "THE": "the", "IN": "in"}


# acronyms in UPTAC's names that contain vowels (vowel-less ones are caught
# by rule): seen in the 2026 list
ACRONYMS = {"ABES", "KIPM", "ACN", "IIMT", "HMFA", "NIGC", "ABSS", "AKTU", "KIET",
            "ITM", "FIT", "IET", "KNIT", "HBTU", "MMMUT", "BIET", "UIET", "IIIT"}


def display_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip()
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"(, ([A-Z][A-Z .]+))(, \2)+$", r"\1", s)  # "…, MEERUT, MEERUT"
    s = re.sub(r"\b((?:[A-Z]\.)+)(?=[A-Z]{2,})", r"\1 ", s)  # "S.R.INSTITUTE"
    # case is decided per comma part: "LUCKNOW PUBLIC COLLEGE…, Lucknow"
    return ", ".join(_caps_part(part) if part.upper() == part else part
                     for part in s.split(", "))


def _caps_part(s: str) -> str:
    words = []
    for i, w in enumerate(s.split(" ")):
        core = w.rstrip(",")
        tail = w[len(core):]
        if core in ABBREV:
            out = ABBREV[core]
            if i == 0:
                out = out[0].upper() + out[1:]
        elif core in ACRONYMS or (len(core) <= 4 and core.isalpha()
                                  and not re.search(r"[AEIOU]", core[1:])):
            out = core                      # acronym: JMS, KCC, AKTU, KIET
        elif re.fullmatch(r"[A-Z](\.[A-Z])*\.?", core):
            out = core                      # initials: B.N., S.R.
        else:
            out = "-".join(x.capitalize() for x in core.split("-"))
        words.append(out + tail)
    return " ".join(words)


def fetch_raw() -> None:
    """GCS is canonical: unzip the newest page archive if raw/pages is empty."""
    if PAGES.exists() and any(PAGES.glob("*.html")):
        return
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_BUCKET)
    zips = sorted(b.name for b in bucket.list_blobs(prefix=f"{GCS_PREFIX}/raw/") if b.name.endswith(".zip"))
    if not zips:
        raise SystemExit("no raw pages locally or in GCS — run fetch_pages.py")
    RAW.mkdir(parents=True, exist_ok=True)
    local = RAW / Path(zips[-1]).name
    bucket.blob(zips[-1]).download_to_filename(str(local))
    zipfile.ZipFile(local).extractall(PAGES)
    print(f"  fetched {zips[-1]}")


def clean_branch(b: str) -> str:
    b = POOL.sub("", SHIFT.sub("", b))
    b = FW.sub("", b).strip()
    for o, n in BRANCH_FIX:
        b = b.replace(o, n)
    return re.sub(r"\s+", " ", b)


def rank_basis(exam: str, remark: str | None) -> str:
    """Which scale a row's ranks are on — never compare across."""
    if remark and remark.startswith("UPTAC ROUND"):
        return "UPTAC round merit rank"
    if exam.upper() == "JEE-MAIN":
        return "JEE Main rank"
    return "unspecified"


def num(x: str):
    x = x.strip()
    return None if x in ("", "-") else float(x.replace(",", ""))


def split_category(code: str) -> tuple[str | None, str | None]:
    if code == "TFW":
        return "TFW", None
    for p in PARENTS:
        if code.startswith(p) and code[len(p):] in SUBS:
            return ("GEN" if p == "OP" else "OBC" if p == "BC" else p), SUBS[code[len(p):]]
    return None, None


def parse() -> pd.DataFrame:
    rows = []
    for f in sorted(PAGES.glob("page_*.html")):
        s = BeautifulSoup(f.read_text(encoding="utf-8"), "html.parser")
        for tr in s.find("table").find("tbody").find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) == 1 and "No results" in cells[0]:
                continue
            if len(cells) != 13:
                raise SystemExit(f"{f.name}: row with {len(cells)} cells: {cells[:3]}")
            rows.append(cells)
    df = pd.DataFrame(rows, columns=COLS)
    df["sr_no"] = df.sr_no.astype(int)
    return df


def build(df: pd.DataFrame) -> pd.DataFrame:
    sr = df.sr_no.sort_values().tolist()
    assert sr == list(range(1, len(sr) + 1)), "Sr.No has gaps or repeats (table changed mid-scrape?)"
    cat = df.category_raw.map(split_category)
    bad = sorted(set(df.category_raw[cat.map(lambda x: x[0] is None)]))
    assert not bad, f"unknown category codes: {bad}"
    shift = df.branch_raw.str.extract(SHIFT)[0]
    out = pd.DataFrame({
        "year": YEAR,
        "round_label": df.round_label,
        "round_no": df.round_label.str.extract(r"^R(\d+)")[0].astype("Int64"),
        "institute_raw": df.institute.str.replace(r"\s+", " ", regex=True).str.strip(),
        "institute": df.institute.map(display_name),
        "programme": df.programme,
        "branch_raw": df.branch_raw,
        "branch": df.branch_raw.map(clean_branch),
        "seat_pool": df.branch_raw.str.extract(POOL)[0].map(POOLS),
        "shift": shift,
        "tfw": df.branch_raw.str.contains(FW) | (df.category_raw == "TFW"),
        "category_raw": df.category_raw,
        "parent_category": cat.map(lambda x: x[0]),
        "sub_category": cat.map(lambda x: x[1]),
        "seat_gender": df.seat_gender,
        "exam": df.exam,
        "opening_rank": df.opening_rank.map(num),
        "closing_rank": df.closing_rank.map(num),
        "min_score": df.min_score.map(num),
        "max_score": df.max_score.map(num),
        "remark": df.remark.replace("", None),
    })
    out["allotted"] = out.closing_rank.notna() | out.min_score.notna()
    out["rank_basis"] = [rank_basis(e, r) for e, r in zip(out.exam, out.remark)]
    return out


def check(out: pd.DataFrame) -> None:
    grain = ["round_label", "institute_raw", "programme", "branch_raw", "category_raw", "seat_gender", "exam"]
    dup = out.duplicated(grain, keep=False)
    assert not dup.any(), f"{dup.sum()} rows share a grain key, e.g. {out[dup].head(2).to_dict('records')}"
    both = out.opening_rank.notna() & out.closing_rank.notna()
    assert (out[both].opening_rank <= out[both].closing_rank).all(), "opening rank after closing rank"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    fetch_raw()
    out = build(parse())
    check(out)
    print(f"uptac_fact_cutoffs: {len(out):,} rows ({out.allotted.sum():,} allotted), "
          f"{out.institute.nunique()} institutes, {out.programme.nunique()} programmes, "
          f"{out.round_label.nunique()} round labels")
    if args.dry_run:
        return
    t = TABLES[0]
    CLEAN.mkdir(parents=True, exist_ok=True)
    out.to_parquet(t.local_path, index=False)
    print(f"  wrote {t.local_path.relative_to(CLEAN.parent)}")


if __name__ == "__main__":
    main()
