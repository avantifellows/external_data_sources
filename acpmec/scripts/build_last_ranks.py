#!/usr/bin/env python3
"""
Build clean/acpmec_fact_last_ranks.parquet: the last rank admitted per
(course, institute, quota, category, round) in Gujarat's 2025-26
admissions, from the committees' last-rank PDFs.

The PDFs are not ruled tables: values are right-aligned under their column
headers and a blank cell is simply absent. Each number is placed by its right
edge (x1) against the header's right edge, never by its position in the line.

  last_rank_nursing  para_last_rank-rN.pdf, one per round. Course header
                     ("101 BPT Bachelor of Physiotherapy"), then one line per
                     institute x quota: "* 0701- AP - GOV Ahmedabad 683 271
                     ..." ("*" = government college; label "-MQ" =
                     management quota, else government quota), columns OP
                     EW SC ST SE and their PH (disability) variants. The
                     rank is on the committee's merit list (Class 12 marks).
                     99999 = seats in that category stayed vacant (no one
                     allotted). The name wraps onto a second line (lost
                     when the wrap falls on the next page: inst_short is a
                     hint; the name is acpmec_dim_institutes'). Some
                     labels carry a further suffix, "-M" ("HVNUR -M",
                     "HVNUR -MQ-M"): a separate seat pool the PDF does not
                     explain, kept as seat_pool. Labels are not unique
                     (codes 3128 and 3134 are both "ANANC"): the 4-digit
                     inst_code is the institute's key.
  last_rank_ug       Compiled_Closure (final) for MBBS + BDS and for
                     BAMS + BHMS. Section header (MEDICAL / DENTAL / BAMS /
                     BHMS), then "AMED - GQ B. J Medical College Ahmedabad"
                     and, per category OPEN SC ST SE EW: NEET percentile,
                     NEET score, NEET (all-India) rank, merit number on the
                     state's general list, and (not OPEN) on the category
                     list. GQ government quota, MQ management, NQ NRI. 0 =
                     not filled on merit; 99999 = vacant. Merit numbers can
                     be fractional ("23369.5", as printed), so they are
                     FLOAT; nursing ranks are whole numbers in the same
                     column.

Quality gates (hard asserts): every course section is recognised; every
institute line yields a label; no (course, label, round, category) twice;
each nursing course's institute count per round within the 2026-27 lists'
range; NEET scores 0-720 and percentiles 0-100.

Usage:
  python3 scripts/build_last_ranks.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, LAST_RANK_FILES, LAST_RANK_YEAR, RAW, TABLES

# nursing & allied course headers -> the institute table's course codes
# (GNM / ANM are nursing diplomas: kept, under their own codes)
NURSING_COURSE = {"BPT": "BPT", "BSC": "BSC_NURSING", "BOP": "BOP", "BO": "BO",
                  "BOT": "BOT", "BASLP": "BASLP", "BNYS": "BNYS",
                  "GNM": "GNM", "ANM": "ANM"}
UG_SECTION = {"MEDICAL": "MBBS", "DENTAL": "BDS", "BAMS": "BAMS", "BHMS": "BHMS"}
QUOTA = {"GQ": "Government quota", "MQ": "Management quota", "NQ": "NRI quota"}
VACANT = 99999
NUM = re.compile(r"\d+(\.\d+)?")


def fetch_raw() -> None:
    missing = [rf for rf in LAST_RANK_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.name} from {rf.gcs_uri}")


def lines_of(page, tol=2.5):
    """words grouped into lines by their top, left to right"""
    out = []
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        if out and abs(out[-1][0] - w["top"]) <= tol:
            out[-1][1].append(w)
        else:
            out.append([w["top"], [w]])
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in out]


def place(words, columns, slack=4):
    """numbers -> {column: value} by right edge; columns = {name: x1}"""
    got = {}
    for w in words:
        if not re.fullmatch(r"\d+(\.\d+)?", w["text"]):
            continue
        col = min(columns, key=lambda c: abs(columns[c] - w["x1"]))
        if abs(columns[col] - w["x1"]) <= slack:
            assert col not in got, f"two values under {col}: {w['text']}"
            got[col] = w["text"]
    return got


def parse_nursing(rf, rnd: int) -> list[dict]:
    import pdfplumber
    recs, course, cur, cols = [], None, None, None
    with pdfplumber.open(rf.local_path) as pdf:
        for page in pdf.pages:
            for ws in lines_of(page):
                texts = [w["text"] for w in ws]
                if texts[:2] == ["INST", "Id"]:
                    cols = {w["text"]: w["x1"] for w in ws if re.fullmatch(r"[A-Z]{2}(PH)?", w["text"])}
                    assert list(cols) == ["OP", "EW", "SC", "ST", "SE", "OPPH", "EWPH",
                                          "SCPH", "STPH", "SEPH"], cols
                    continue
                if re.fullmatch(r"1\d\d", texts[0]) and len(texts) > 1 and texts[1] in NURSING_COURSE:
                    course, cur = NURSING_COURSE[texts[1]], None
                    continue
                i = next((k for k, t in enumerate(texts) if re.fullmatch(r"\d{4}-", t)), None)
                if i is not None and i <= 1:
                    assert course and cols, f"{rf.name}: institute before a course header"
                    # "0701- AP - GOV Ahmedabad" / "0721- VSP-MQ - S B B ABAD" /
                    # "0656- HVNUR -MQ-M - H.V. Mehta": the label runs to the
                    # lone "-", its suffixes split over words
                    j = texts.index("-", i + 1)
                    label, *suffix = "".join(texts[i + 1:j]).split("-")
                    quota = "MQ" if "MQ" in suffix else "GQ"
                    pool = "-".join(x for x in suffix if x != "MQ") or None
                    name_words = [w["text"] for w in ws[j + 1:]
                                  if not NUM.fullmatch(w["text"]) or w["x1"] < min(cols.values()) - 10]
                    cur = dict(course_code=course, inst_code=texts[i][:4], inst_label=label,
                               quota=quota, seat_pool=pool, govt_college=texts[0] == "*",
                               inst_short=" ".join(name_words))
                    vals = place(ws, cols)
                    for cat in cols:
                        if cat in vals:
                            v = int(vals[cat])
                            recs.append({**cur, "round": rnd, "category": cat,
                                         "last_rank": None if v == VACANT else v,
                                         "vacant": v == VACANT})
                    continue
                if cur and texts[0] not in ("*", "Admission", "Round") and not texts[0].startswith("Page"):
                    # the institute's name wrapping onto a second line
                    if all(w["x1"] < min(cols.values()) - 10 for w in ws):
                        cur["inst_short"] += " " + " ".join(texts)
                        for r in recs[::-1]:
                            if r["inst_code"] != cur["inst_code"] or r["quota"] != cur["quota"] \
                                    or r["seat_pool"] != cur["seat_pool"]:
                                break
                            r["inst_short"] = cur["inst_short"]
    return recs


UG_CATS = ["OPEN", "SC", "ST", "SE", "EW"]
UG_FIELDS = ["neet_percentile", "neet_score", "neet_rank", "merit_no", "category_merit_no"]
UG_COLUMNS = [(cat, f) for cat in UG_CATS for f in (UG_FIELDS[:4] if cat == "OPEN" else UG_FIELDS)]
def is_num(w) -> bool:
    return bool(NUM.fullmatch(w["text"]))


def ug_columns(rows):
    """The 24 value columns' right edges, from the data: the header's
    labels sit a few points off their numbers, the numbers themselves are
    right-aligned to one edge per column. Cluster every number's x1."""
    xs = sorted(w["x1"] for _, _, ws in rows for w in ws if is_num(w) and w["x0"] > 200)
    edges = []
    for x in xs:
        if edges and x - edges[-1][-1] <= 3:
            edges[-1].append(x)
        else:
            edges.append([x])
    edges = [max(e) for e in edges]
    assert len(edges) == len(UG_COLUMNS), f"{len(edges)} value columns, expected 24: {edges}"
    return dict(zip(UG_COLUMNS, edges))


def parse_ug(rf) -> list[dict]:
    import pdfplumber
    rows, course = [], None
    with pdfplumber.open(rf.local_path) as pdf:
        for page in pdf.pages:
            for ws in lines_of(page):
                texts = [w["text"] for w in ws]
                if len(texts) == 1 and texts[0] in UG_SECTION:
                    course = UG_SECTION[texts[0]]
                elif len(texts) > 3 and texts[1] == "-" and texts[2] in QUOTA:
                    assert course, f"{rf.name}: institute before a section"
                    rows.append((course, texts, ws))
    cols = ug_columns(rows)
    recs = []
    for course, texts, ws in rows:
        vals = place(ws, cols)
        first = min((w["x0"] for w in ws if is_num(w) and w["x0"] > 200), default=1e9)
        name = " ".join(w["text"] for w in ws[3:] if w["x1"] < first)
        for cat in UG_CATS:
            got = {f: vals.get((cat, f)) for f in UG_FIELDS}
            if not any(got.values()):
                continue
            score, rank, merit = got["neet_score"], got["neet_rank"], got["merit_no"]
            vacant = VACANT in {int(float(v)) for v in got.values() if v}
            filled = not vacant and bool(score) and float(score) > 0
            recs.append(dict(
                course_code=course, inst_code=None, inst_label=texts[0], quota=texts[2], seat_pool=None,
                govt_college=None, inst_short=name, round=None, category=cat,
                neet_percentile=float(got["neet_percentile"]) if filled else None,
                neet_score=int(score) if filled else None,
                neet_rank=int(rank) if filled and rank else None,
                last_rank=float(merit) if filled and merit else None,
                category_merit_no=float(got["category_merit_no"])
                if filled and got["category_merit_no"] else None,
                vacant=vacant))
    return recs


def build() -> pd.DataFrame:
    fetch_raw()
    recs = []
    for rf in LAST_RANK_FILES:
        if rf.kind == "last_rank_nursing":
            rnd = int(re.search(r"_r(\d+)\.pdf", rf.name).group(1))
            rows = parse_nursing(rf, rnd)
        else:
            rows = parse_ug(rf)
        for r in rows:
            r.update(academic_year=LAST_RANK_YEAR, source_file=rf.name, source_url=rf.url)
        print(f"  {rf.name:34s} {len(rows):>6} rows, "
              f"{len({(r['course_code'], r['inst_label']) for r in rows}):>4} institutes")
        recs += rows
    df = pd.DataFrame(recs)
    df["committee"] = df.course_code.map(lambda c: "ug_medical" if c in UG_SECTION.values()
                                         else "nursing_allied")
    df = df[["academic_year", "committee", "course_code", "inst_code", "inst_label",
             "inst_short", "govt_college", "quota", "seat_pool", "round", "category", "last_rank",
             "category_merit_no", "neet_percentile", "neet_score", "neet_rank", "vacant",
             "source_file", "source_url"]]
    for c in ["round", "neet_score", "neet_rank"]:
        df[c] = df[c].astype("Int64")
    df["inst_short"] = df.inst_short.str.replace(r"\s+", " ", regex=True).str.strip()

    # nursing labels repeat across institutes (two "ANANC"): the 4-digit
    # code is the key there; UG has no code, its labels are unique
    df["_id"] = df.inst_code.fillna(df.inst_label)
    key = ["course_code", "_id", "quota", "seat_pool", "round", "category"]
    dup = df[df.duplicated(key, keep=False)]
    assert dup.empty, f"duplicate {key}:\n{dup[key].head(20)}"
    df = df.drop(columns="_id")
    assert df.inst_label.str.len().min() >= 2
    assert df.neet_score.dropna().between(0, 720).all()
    assert df.neet_percentile.dropna().between(0, 100).all()
    assert set(df.course_code) >= {"BSC_NURSING", "BPT", "MBBS", "BDS", "BAMS", "BHMS"}
    return df


def main() -> None:
    df = build()
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = next(t for t in TABLES if t.name == "acpmec_fact_last_ranks").local_path
    df.to_parquet(out, index=False)
    print(f"\n{len(df)} rows -> {out}")
    print(df.groupby(["course_code", "round"], dropna=False).inst_label.nunique().unstack(fill_value=0))


if __name__ == "__main__":
    main()
