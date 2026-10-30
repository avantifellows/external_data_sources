#!/usr/bin/env python3
"""
Build clean/acpmec_dim_institutes.parquet: one row per (course, institute)
that Gujarat's admission committees list for 2026-27, with the institute's
type, affiliating university, annual intake and tuition fee.

The PDFs are ruled tables, so pdfplumber's table extraction reads them
cell by cell. Three layouts:

  dental          Seat Matrix Dental: Type (a merged cell over a group:
                  "Govt. Dental Colleges", "SFI Dental Colleges"), CODE,
                  INSTITUTE NAME, Intake, AIQ, MQ, NRI, Govt. Quota, then
                  category splits; a Total per group and a GRAND TOTAL. A
                  second table on the same page (a category break-up of a
                  few seats) is skipped by its width.
  ayush           BAMS / BHMS lists: Sr. No., name, College Code, Type
                  (Govt / GIA / SFI), University, seat intake AIQ GQ MQ NRI
                  [FOREIGN STUDENT, BAMS only] Total, affiliation, permission
                  (NCISM / NCH), tuition fee per quota in lakh rupees.
  nursing_allied  one file per course: SR NO, COURSE, INST TYPE (GOV/SFI),
                  INST CODE (4 digits), INST LABEL, name, address (Gujarati,
                  not kept: the extracted text is garbled), university,
                  INTAKE, ancillary fees, FEES BY FRC (annual tuition fixed
                  by the Fee Regulatory Committee). pdfplumber reports a few
                  one-page tables twice: rows dedupe on (course, inst code).

Quality gates (hard asserts):
  - every file's parsed intake sums to the Total row the committee prints
    (blank intake cells are null: the Occupational Therapy file has no
    intake column, and the BO / BPT files leave three cells blank)
  - serial numbers run 1..N with no gap (checked once by hand for 2026-27)
  - no duplicate (course, inst_label)
  - per-course institute counts as of the 2026-27 lists

Usage:
  python3 scripts/build_clean.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (ACADEMIC_YEAR, CLEAN, COMMITTEE, COURSE_NAMES, GCS_BUCKET,
                     RAW, RAW_FILES, TABLES)

# institutes per course in the 2026-27 lists; a refresh that changes these
# must change them here in the same commit, with the reason
EXPECTED = {"BSC_NURSING": 299, "BPT": 68, "BHMS": 48, "BAMS": 43, "BDS": 13,
            "BO": 8, "BASLP": 3, "BOT": 1, "BOP": 1, "BNYS": 1}

OWNERSHIP = {
    "GOV": "Government", "GOVT": "Government", "GIA": "Government-aided",
    "SFI": "Self-financed",
}


def fetch_raw() -> None:
    """GCS is canonical; download any raw PDF missing locally."""
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.local_path.relative_to(RAW.parent)} from {rf.gcs_uri}")


def tables(path: Path) -> list[list[str]]:
    import pdfplumber
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for t in page.extract_tables():
                rows += [[re.sub(r"\s+", " ", c or "").strip() for c in r] for r in t]
    return rows


def num(v) -> int | None:
    t = str(v or "").replace(",", "").replace(" ", "")
    return int(float(t)) if re.fullmatch(r"\d+(\.\d+)?", t) else None


def lakh(v) -> int | None:
    """'0 .04' / '5.16' / '5.16 Lakh' (lakh rupees) -> rupees"""
    m = re.match(r"(\d+(?:\.\d+)?)", str(v or "").replace(" ", ""))
    return round(float(m.group(1)) * 100_000) if m else None


def printed_total(rows, col) -> int:
    tot = [num(r[col]) for r in rows if r and (r[0] == "Total" or r[1] == "Total")]
    tot = [t for t in tot if t is not None]
    if not tot:
        raise SystemExit("no Total row")
    return tot[0]


def parse_dental(rf) -> tuple[list[dict], int]:
    rows = [r for r in tables(rf.local_path) if len(r) == 14]
    out, kind = [], None
    for r in rows:
        if r[0] and "TOTAL" not in r[0].upper():
            kind = r[0]
        if not r[1] or r[1].upper() in ("CODE", "TOTAL") or num(r[3]) is None:
            continue
        raw_type = "GOV" if kind.startswith("Govt") else "GIA" if "GIA" in kind or "Aided" in kind else "SFI"
        out.append(dict(inst_label=r[1], institute_name=r[2], affiliated_university=None,
                        inst_type_raw=kind, ownership=OWNERSHIP[raw_type], intake=num(r[3]),
                        seats_aiq=num(r[4]), seats_mq=num(r[5]), seats_nri=num(r[6]),
                        seats_gq=num(r[7]), permission=None, tuition_fee_inr=None))
    total = next(num(r[3]) for r in rows if r[0].upper() == "GRAND TOTAL")
    return out, total


def parse_ayush(rf) -> tuple[list[dict], int]:
    rows = tables(rf.local_path)
    head = next(r for r in rows if "AIQ" in r)
    i_aiq = head.index("AIQ")
    i_tot = head.index("Total")
    out = []
    for r in rows:
        if not re.fullmatch(r"\d+\.?", r[0] or "") or len(r) <= i_tot:
            continue
        out.append(dict(inst_label=r[2], institute_name=r[1], affiliated_university=r[4] or None,
                        inst_type_raw=r[3], ownership=OWNERSHIP[r[3].upper()],
                        intake=num(r[i_tot]), seats_aiq=num(r[i_aiq]), seats_gq=num(r[i_aiq + 1]),
                        seats_mq=num(r[i_aiq + 2]), seats_nri=num(r[i_aiq + 3]),
                        permission=r[i_tot + 2] or None,
                        tuition_fee_inr=lakh(r[i_tot + 3])))
    total = printed_total([r for r in rows if len(r) > i_tot], i_tot)
    return out, total


def parse_nursing(rf) -> tuple[list[dict], int]:
    rows = tables(rf.local_path)
    head = next(r for r in rows if r and r[0] == "SR NO")
    # the 2026-27 Occupational Therapy file prints no INTAKE column
    i_int = head.index("INTAKE") if "INTAKE" in head else None
    i_frc = head.index("FEES BY FRC")
    out, seen = [], set()
    totals = []
    for r in rows:
        if len(r) != len(head):
            continue
        if i_int is not None and not r[0] and not r[3] and num(r[i_int]) is not None:
            totals.append(num(r[i_int]))
            continue
        if not re.fullmatch(r"\d+", r[0]) or (r[1], r[3]) in seen:
            continue
        seen.add((r[1], r[3]))
        out.append(dict(inst_code=r[3], inst_label=r[4], institute_name=r[5],
                        affiliated_university=r[7] or None, inst_type_raw=r[2],
                        ownership=OWNERSHIP[r[2].upper()],
                        intake=None if i_int is None else num(r[i_int]),
                        seats_aiq=None, seats_gq=None, seats_mq=None, seats_nri=None,
                        permission=None, tuition_fee_inr=num(r[i_frc])))
    if i_int is None:
        return out, None
    if not totals:
        raise SystemExit(f"{rf.name}: no total row")
    # a table reported twice prints its total twice
    return out, totals[0]


PARSERS = {"dental": parse_dental, "ayush": parse_ayush, "nursing_allied": parse_nursing}


def clean_name(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip().rstrip(".").strip()
    return re.sub(r"\s+,", ",", t)


def build() -> pd.DataFrame:
    fetch_raw()
    recs = []
    for rf in RAW_FILES:
        rows, total = PARSERS[rf.kind](rf)
        got = sum(r["intake"] or 0 for r in rows)
        if total is None:
            print(f"  {rf.name:40s} {len(rows):>4} institutes, no intake printed")
        else:
            assert got == total, f"{rf.name}: parsed intake {got} != printed total {total}"
            print(f"  {rf.name:40s} {len(rows):>4} institutes, intake {got:>5} (= printed total)")
        for r in rows:
            r.setdefault("inst_code", None)
            r.update(academic_year=ACADEMIC_YEAR, course_code=rf.course,
                     course_name=COURSE_NAMES[rf.course],
                     committee=COMMITTEE.get(rf.course, "nursing_allied"),
                     source_file=rf.name, source_url=rf.url)
            r["institute_name"] = clean_name(r["institute_name"])
        recs += rows
    df = pd.DataFrame(recs)[[
        "academic_year", "committee", "course_code", "course_name", "inst_code",
        "inst_label", "institute_name", "affiliated_university", "inst_type_raw",
        "ownership", "intake", "seats_aiq", "seats_gq", "seats_mq", "seats_nri",
        "permission", "tuition_fee_inr", "source_file", "source_url"]]
    for c in ["intake", "seats_aiq", "seats_gq", "seats_mq", "seats_nri", "tuition_fee_inr"]:
        df[c] = df[c].astype("Int64")

    dup = df[df.duplicated(["course_code", "inst_label"], keep=False)]
    assert dup.empty, f"duplicate (course, label):\n{dup}"
    counts = df.course_code.value_counts().to_dict()
    assert counts == EXPECTED, f"institute counts changed: {counts}"
    assert df.institute_name.str.len().min() > 5
    assert df.ownership.notna().all()
    return df


def main() -> None:
    df = build()
    CLEAN.mkdir(parents=True, exist_ok=True)
    out = TABLES[0].local_path
    df.to_parquet(out, index=False)
    print(f"\n{len(df)} rows -> {out}")
    print(df.groupby(["course_code", "ownership"]).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
