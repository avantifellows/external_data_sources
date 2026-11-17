#!/usr/bin/env python3
"""
NMC's live MBBS college list (raw/nmc_mbbs_colleges_<date>.json, from
fetch_live.py) → clean/mbbs_colleges.parquet → BQ nmc_fact_mbbs_colleges.

One row per college. `college_code` is NMC's own code (state/serial/
management/version, e.g. "AN/001/G/1") and is unique per fetch; it is the key
to carry, not the name, which NMC edits (renames are written into the name:
"Dharanidhar Medical College (previously Government Medical College,
Keonjhar)").

Checks, before writing:
  - row count = the response's pagination total, codes unique
  - SUM(approved_seats) = the response's total_seats
  - management_type is Government / Private / Trust only

Usage:
  python3 scripts/clean_live.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, TABLES, latest_live_raw

TABLE = next(t for t in TABLES if t.bq_name == "nmc_fact_mbbs_colleges")

# NMC spells a few states its own way; the warehouse's other tables use these
STATE = {
    "Chattisgarh": "Chhattisgarh",
    "Orissa": "Odisha",
    "Pondicherry": "Puducherry",
    "Jammu & Kashmir": "Jammu and Kashmir",
}


def ws(x):
    return re.sub(r"\s+", " ", str(x)).strip() if x is not None else None


def main() -> None:
    src = latest_live_raw()
    fetched_on = re.search(r"(\d{4}-\d{2}-\d{2})", src.name).group(1)
    d = json.loads(src.read_text())
    rows = []
    for x in d["data"]:
        state = ws(x.get("state_name"))
        rows.append({
            "fetched_on": fetched_on,
            "college_code": ws(x.get("college_code")),
            "nmc_college_id": x.get("college_id"),
            "college": ws(x.get("college_name")),
            "state_raw": state,
            "state": STATE.get(state, state),
            "university": ws(x.get("university_name")),
            "management_type": ws(x.get("management_type")),
            "year_of_inception": x.get("year_of_inception_of_college") or x.get("inception_year"),
            "lop_date": x.get("lop_date"),
            "approved_seats": x.get("approved_seat"),
            "previous_approved_seats": x.get("previous_approved_seat"),
            "approval_date": x.get("approval_date"),
            "recognition_status": ws(x.get("recognition_status")),
            "source_updated_date": x.get("updated_date"),
        })
    df = pd.DataFrame(rows)
    for c in ("year_of_inception", "approved_seats", "previous_approved_seats", "nmc_college_id"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")

    total = d["pagination"]["total"]
    assert len(df) == total, (len(df), total)
    assert df.college_code.is_unique, df.college_code[df.college_code.duplicated()].tolist()
    assert int(df.approved_seats.sum()) == int(d["total_seats"]), (df.approved_seats.sum(), d["total_seats"])
    assert set(df.management_type) <= {"Government", "Private", "Trust"}, set(df.management_type)

    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(TABLE.local_path, index=False)
    print(f"  ✓ {TABLE.local_path.name}: {len(df)} colleges, {int(df.approved_seats.sum())} seats, "
          f"{df.state.nunique()} states (fetched {fetched_on})")
    print(df.management_type.value_counts().to_string())


if __name__ == "__main__":
    main()
