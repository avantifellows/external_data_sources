#!/usr/bin/env python3
"""
Pull the AICTE technical-education dashboard JSON API into raw/ as three panels.

Makes the source CSVs regenerable from scratch — no manual download. After
fetching, run clean_aicte.py → upload_to_gcs.py → load_bq.py.

API endpoint:
  https://facilities.aicte-india.org/dashboard/pages/php/dashboardserver.php

Per (year, program, level, state, institutiontype) filter, the API returns:
  records.girls / records.boys / records.faculties  (scalars for the SELECTED year)
  records.intake / .enrollment / .passed / .placed / .instituecount
                                                 (11-element arrays, years
                                                  2012-13 ... 2022-23)

So to get an 11-year time series at any cut we only need ONE query per cut (the
year arg only affects the gender / faculty scalars). We pull three panels:

  panel_national.csv    program × level × year       (8 × 11 = 88 requests)
  panel_state.csv       state × program × level      (36 × 8 = 288 requests)
  panel_inst_type.csv   institution_type × program × level  (16 × 8 = 128 requests)

For the state and inst-type panels we set year=9 (2021-22, latest reliable year
for gender) which gives 11 years of intake/enrolment/passed/placed PLUS the
2021-22 girls / boys scalar (2022-23 enrolment is incomplete in the live
dashboard). Network-bound (~440 throttled requests).

Usage:
  python3 scripts/fetch.py                 # pull all three panels
  python3 scripts/fetch.py --panel state   # one panel: national / state / inst_type
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import PANEL_INST_TYPE, PANEL_NATIONAL, PANEL_STATE, RAW

ALL_INST = [
    "Private", "Central University",
    "Deemed to be University(Govt)", "Deemed to be University(Pvt)",
    "Deemed University(Government)", "Deemed University(Private)",
    "Government", "Govt aided", "Private-Aided", "Private-Self Financing",
    "State Government University", "State Private University",
    "Unaided - Private", "University Managed",
    "University Managed-Govt", "University Managed-Private",
]
ALL_STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh",
    "Assam", "Bihar", "Chandigarh", "Chhattisgarh",
    "Dadra and Nagar Haveli", "Daman and Diu", "Delhi", "Goa", "Gujarat",
    "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Orissa", "Puducherry",
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
    "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
]

YEAR_LABEL = {
    0: "2012-13", 1: "2013-14", 2: "2014-15", 3: "2015-16", 4: "2016-17",
    5: "2017-18", 6: "2018-19", 7: "2019-20", 8: "2020-21", 9: "2021-22",
    10: "2022-23",
}

PROG_LEVELS = [
    ("Engineering and Technology", "UG"),
    ("Engineering and Technology", "PG"),
    ("Engineering and Technology", "DIPLOMA"),
    ("Management", "PG"),
    ("MCA", "PG"),
    ("Pharmacy", "UG"),
    ("Architecture", "UG"),
    ("Hotel Management and Catering", "UG"),
]

# Throttle requests gently to be a good citizen.
DELAY = 0.25  # seconds between requests


def fetch(year_idx: int, program: str, level: str,
          states=ALL_STATES, inst_types=ALL_INST) -> dict:
    params = {
        "year": year_idx,
        "institutiontype": ",".join(inst_types),
        "level": level,
        "program": program,
        "state": ",".join(states),
        "Minority": 1, "Women": 1,
    }
    qs = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    url = (
        "https://facilities.aicte-india.org/dashboard/pages/php/"
        f"dashboardserver.php?{qs}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def safe_int(v):
    if v in (None, "", "null"):
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def panel_national():
    """Pull each (program, level) once per year (gender for each year)."""
    out = []
    print("Panel national — Program × Level × Year")
    for prog, level in PROG_LEVELS:
        for yi in range(11):
            try:
                d = fetch(yi, prog, level)
            except Exception as e:
                print(f"  err {prog}/{level}/{yi}: {e}")
                continue
            rec = d.get("records", {})
            out.append({
                "program": prog, "level": level,
                "year": YEAR_LABEL[yi],
                "approved_intake": safe_int((rec.get("intake") or [None] * 11)[yi]),
                "enrolled":        safe_int((rec.get("enrollment") or [None] * 11)[yi]),
                "passed":          safe_int((rec.get("passed") or [None] * 11)[yi]),
                "placed":          safe_int((rec.get("placed") or [None] * 11)[yi]),
                "institutions":    safe_int((rec.get("instituecount") or [None] * 11)[yi]),
                "girls":           safe_int(rec.get("girls")),
                "boys":            safe_int(rec.get("boys")),
                "faculties":       safe_int(rec.get("faculties")),
            })
            time.sleep(DELAY)
    _write(PANEL_NATIONAL, out,
           ["program", "level", "year", "approved_intake", "enrolled",
            "passed", "placed", "institutions", "girls", "boys", "faculties"])


def panel_state(focal_year_idx=9):
    """For each state × (program, level): one query → 11-yr arrays + focal-year gender."""
    out = []
    print(f"Panel state — State × Program × Level (focal year {YEAR_LABEL[focal_year_idx]})")
    for state in ALL_STATES:
        for prog, level in PROG_LEVELS:
            try:
                d = fetch(focal_year_idx, prog, level, states=[state])
            except Exception as e:
                print(f"  err {state}/{prog}/{level}: {e}")
                continue
            rec = d.get("records", {})
            for yi in range(11):
                out.append({
                    "state": state,
                    "program": prog, "level": level,
                    "year": YEAR_LABEL[yi],
                    "approved_intake": safe_int((rec.get("intake") or [None] * 11)[yi]),
                    "enrolled":        safe_int((rec.get("enrollment") or [None] * 11)[yi]),
                    "passed":          safe_int((rec.get("passed") or [None] * 11)[yi]),
                    "placed":          safe_int((rec.get("placed") or [None] * 11)[yi]),
                    "institutions":    safe_int((rec.get("instituecount") or [None] * 11)[yi]),
                    "girls":           safe_int(rec.get("girls")) if yi == focal_year_idx else None,
                    "boys":            safe_int(rec.get("boys")) if yi == focal_year_idx else None,
                })
            time.sleep(DELAY)
    _write(PANEL_STATE, out,
           ["state", "program", "level", "year", "approved_intake", "enrolled",
            "passed", "placed", "institutions", "girls", "boys"])


def panel_inst_type(focal_year_idx=9):
    """For each institution-type × (program, level): one query."""
    out = []
    print(f"Panel inst_type — Institution-Type × Program × Level (focal year {YEAR_LABEL[focal_year_idx]})")
    for itype in ALL_INST:
        for prog, level in PROG_LEVELS:
            try:
                d = fetch(focal_year_idx, prog, level, inst_types=[itype])
            except Exception as e:
                print(f"  err {itype}/{prog}/{level}: {e}")
                continue
            rec = d.get("records", {})
            for yi in range(11):
                out.append({
                    "institution_type": itype,
                    "program": prog, "level": level,
                    "year": YEAR_LABEL[yi],
                    "approved_intake": safe_int((rec.get("intake") or [None] * 11)[yi]),
                    "enrolled":        safe_int((rec.get("enrollment") or [None] * 11)[yi]),
                    "passed":          safe_int((rec.get("passed") or [None] * 11)[yi]),
                    "placed":          safe_int((rec.get("placed") or [None] * 11)[yi]),
                    "institutions":    safe_int((rec.get("instituecount") or [None] * 11)[yi]),
                    "girls":           safe_int(rec.get("girls")) if yi == focal_year_idx else None,
                    "boys":            safe_int(rec.get("boys")) if yi == focal_year_idx else None,
                })
            time.sleep(DELAY)
    _write(PANEL_INST_TYPE, out,
           ["institution_type", "program", "level", "year", "approved_intake",
            "enrolled", "passed", "placed", "institutions", "girls", "boys"])


def _write(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"  ✓ wrote {len(rows)} rows → {path.name}")


PANELS = {
    "national": panel_national,
    "state": panel_state,
    "inst_type": panel_inst_type,
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", choices=list(PANELS), default=None,
                    help="Pull only this panel (default: all three)")
    args = ap.parse_args()

    chosen = [args.panel] if args.panel else list(PANELS)
    print(f"aicte fetch → {RAW}")
    for name in chosen:
        PANELS[name]()
    print("✓ done.")


if __name__ == "__main__":
    main()
