#!/usr/bin/env python3
"""
raw/<date>/ (fetch.py) → clean/ parquet for BQ:

  ndc_dim_dental_colleges  one row per BDS college: name, state, city, PIN,
                           address, year established, Govt/Private, the body
                           that runs it, attached hospital, website, and the
                           list page's permitted BDS seats (2025-26).
  ndc_fact_dental_seats    college x course (BDS/MDS/PG Diploma) x speciality
                           for the newest academic year: approved, recognised,
                           intake, permitted and admitted seats (the seats
                           grid's first page, complete only for that year).

Left out on purpose: the principal's name and e-mail (a person, not the
college) and the hostel / dental-chair / built-area grids (their newest years
sit on later grid pages the fetch doesn't page through).

Checks before writing: one details page per list row, college names agree
between list and details page, ids unique, no duplicate seat rows.

Usage:
  python3 scripts/build_clean.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, latest_raw

P = "MainContent_"
REVIEWED = {(x["details_name"], x["list_name"]) for x in json.loads(
    (Path(__file__).resolve().parent / "reviewed_name_pairs.json").read_text())["pairs"]}


def ws(x):
    x = re.sub(r"\s+", " ", str(x or "")).strip()
    return None if x in ("", "N/A", "NA", "-") else x


def num(x):
    x = ws(x)
    return int(x) if x and re.fullmatch(r"\d+", x) else None


def year_of(est):
    m = re.match(r"(\d{4})", str(est or ""))
    return int(m.group(1)) if m else None


SAME = {"govt": "government", "&": "and", "instt": "institute", "inst": "institute",
        "sci": "sciences", "science": "sciences", "res": "research", "hosp": "hospital",
        "coll": "college", "ctr": "centre", "center": "centre", "dr": "", "of": "", "the": ""}


def words(x):
    out = []
    for w in re.findall(r"[a-z0-9&]+", str(x or "").lower()):
        w = SAME.get(w, w)
        if w:
            out.append(w)
    return out


def same_college(details_name, list_name):
    d, l = set(words(details_name)), set(words(list_name))
    return bool(d) and len(d & l) / len(d) >= 0.6


def parse_list(html):
    """row id (ctlNN) -> list-page fields"""
    s = BeautifulSoup(html, "lxml")
    t = s.find("table", id="gvSearchCollegelist")
    out = {}
    for tr in t.find_all("tr"):
        btn = tr.find("input", attrs={"name": re.compile(r"imgbtnEdit1$")})
        if not btn:
            continue
        row = re.search(r"\$ctl(\d+)\$", btn["name"]).group(1)
        tds = tr.find_all("td", recursive=False)
        seats = None
        inner = tds[5].find("table")
        if inner:
            for itr in inner.find_all("tr"):
                c = [ws(x.get_text(" ")) for x in itr.find_all("td")]
                if c and c[0] == "BDS":
                    seats = num(c[-1])
        out[row] = {
            "list_sl_no": num(tds[0].get_text()),
            "list_name": ws(tds[1].get_text(" ")),
            "state": ws(tds[2].get_text(" ")),
            "established": ws(tds[3].get_text(" ")),
            "college_type": ws(tds[4].get_text(" ")),
            "bds_permitted_seats_2025_26": seats,
        }
    return out


def ids(s):
    return {el["id"]: ws(el.get_text(" ")) for el in s.find_all(id=True)}


def text(s, id_):
    return s.get(P + id_)


def grid(s, gid, fields):
    out, i = [], 0
    while f"{P}{gid}_{fields[0]}_{i}" in s:
        out.append({f: s.get(f"{P}{gid}_{f}_{i}") for f in fields})
        i += 1
    return out


def main() -> None:
    day = latest_raw()
    fetched_on = day.name
    index = json.loads((day / "index.json").read_text())
    lst = parse_list((day / "list.html").read_text(encoding="utf-8"))
    assert set(lst) == set(index), (len(lst), len(index), sorted(set(lst) ^ set(index))[:5])

    colleges, seats, mismatched = [], [], []
    for row, cid in sorted(index.items(), key=lambda kv: lst[kv[0]]["list_sl_no"]):
        s = ids(BeautifulSoup((day / "details" / f"{row}.html").read_text(encoding="utf-8"), "lxml"))
        L = lst[row]
        name = text(s, "txtCollegeName")
        # the list prints "<name>, <city>", the details page the name alone and
        # spelt its own way ("Govt. ... &" / "GOVERNMENT ... AND"): most of the
        # details name's words must be in the list name, or the page is
        # another college's
        if not same_college(name, L["list_name"]) and (name, L["list_name"]) not in REVIEWED:
            mismatched.append((row, name, L["list_name"]))
        colleges.append({
            "fetched_on": fetched_on,
            "ndc_id": cid,
            "list_sl_no": L["list_sl_no"],
            "college": L["list_name"],
            "college_short": name,
            "state": text(s, "lblState") or L["state"],
            "city": text(s, "txtCity"),
            "pin": text(s, "txtZipCode"),
            "address_line1": text(s, "txtAddresLine1"),
            "address_line2": text(s, "txtAddress2"),
            "established": L["established"] or text(s, "lblEstablishmentYear"),
            "year_established": year_of(L["established"] or text(s, "lblEstablishmentYear")),
            "college_type": text(s, "lblStatus") or L["college_type"],
            "admin_authority": text(s, "lblType"),
            "hospital_attached": text(s, "txtHospitalAttached"),
            "hospital_type": text(s, "lblhosptype"),
            "website": text(s, "txtWebsite"),
            "bds_permitted_seats_2025_26": L["bds_permitted_seats_2025_26"],
        })
        for g in grid(s, "gvCollegeSpecialisation",
                      ["lblSCourseName", "lblCSpcl", "lblCAcademicYr", "lblApprovedSeats",
                       "lblRecognisedSeats", "lblTotal_Intake", "lblPermittedSeats", "lblAdmittedSeats"]):
            seats.append({
                "fetched_on": fetched_on,
                "ndc_id": cid,
                "course": g["lblSCourseName"],
                "speciality": g["lblCSpcl"],
                "academic_year": g["lblCAcademicYr"],
                "approved_seats": num(g["lblApprovedSeats"]),
                "recognised_seats": num(g["lblRecognisedSeats"]),
                "intake_capacity": num(g["lblTotal_Intake"]),
                "permitted_seats": num(g["lblPermittedSeats"]),
                "admitted_seats": num(g["lblAdmittedSeats"]),
            })

    if mismatched:
        for m in mismatched:
            print("  list vs details name:", m)
        raise SystemExit(f"{len(mismatched)} details pages don't name their list row's college")
    dim = pd.DataFrame(colleges)
    fact = pd.DataFrame(seats)
    for c in ("list_sl_no", "year_established", "bds_permitted_seats_2025_26"):
        dim[c] = dim[c].astype("Int64")
    for c in ("approved_seats", "recognised_seats", "intake_capacity", "permitted_seats", "admitted_seats"):
        fact[c] = fact[c].astype("Int64")
    assert dim.ndc_id.is_unique
    key = ["ndc_id", "course", "speciality", "academic_year"]
    # the site prints a few rows twice, identical: keep one; two rows for one
    # key with different numbers would be a real conflict
    exact = int(fact.duplicated().sum())
    fact = fact.drop_duplicates().reset_index(drop=True)
    print(f"  dropped {exact} exact duplicate seat row(s) the site prints twice")
    # the grid's first page is complete only for the newest year; older years
    # appear only where a college had few rows, so summing them would mislead
    newest = fact.academic_year.max()
    print(f"  keeping academic year {newest} only ({(fact.academic_year != newest).sum()} older rows dropped)")
    fact = fact[fact.academic_year == newest].reset_index(drop=True)
    dup = fact[fact.duplicated(key, keep=False)]
    assert dup.empty, dup.head()

    CLEAN.mkdir(parents=True, exist_ok=True)
    dim.to_parquet(CLEAN / "ndc_dim_dental_colleges.parquet", index=False)
    fact.to_parquet(CLEAN / "ndc_fact_dental_seats.parquet", index=False)
    print(f"ndc_dim_dental_colleges: {len(dim)} colleges, {dim.state.nunique()} states, "
          f"BDS 2025-26 permitted seats {int(dim.bds_permitted_seats_2025_26.sum())}")
    print(dim.college_type.value_counts().to_string())
    print(f"ndc_fact_dental_seats: {len(fact)} rows; years {sorted(fact.academic_year.dropna().unique())}")
    print(fact.groupby(["academic_year", "course"]).permitted_seats.sum().to_string())


if __name__ == "__main__":
    main()
