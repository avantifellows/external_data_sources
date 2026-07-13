"""
Parse the NMC UG (MBBS) seat-matrix PDF into the single denormalized fact
(clean/mbbs_seats.parquet → BQ nmc_fact_mbbs_seats).

The PDF is one table per page (35 pages), all with the same 8-column layout:

  Sl.No. | State | Name and Address of Medical College / Medical Institution
         | District | University Name | Management of College
         | Year of Inception of College | Annual Intake (Seats)

Cells carry embedded newlines (the source wraps long names across lines), so
every text cell is whitespace-normalized (\\s+ → single space). We keep rows
whose Sl.No is a digit (skipping the title row, the repeated column header, and
the grand-total footer row), and forward-fill State if a row's State cell is
blank.

Grain: (snapshot, sl_no) — one row per MBBS medical college.

Usage:
  python3 scripts/clean_nmc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import PDF, SNAPSHOT, TABLES

# Column positions in the 8-column page table.
C_SLNO, C_STATE, C_COLLEGE, C_DISTRICT, C_UNIVERSITY, C_MGMT, C_YEAR, C_SEATS = range(8)

COLUMNS = [
    "snapshot", "sl_no", "state", "college", "district", "university",
    "management_category", "management", "year_of_inception", "annual_intake_seats",
]


def _norm(s) -> str:
    """Collapse embedded newlines + runs of whitespace to single spaces."""
    if s is None:
        return ""
    return re.sub(r"\s+", " ", str(s)).strip()


def _to_int(s):
    """First integer found in a cell (digits only), else None."""
    digits = re.sub(r"[^\d]", "", str(s) if s is not None else "")
    return int(digits) if digits else None


def _mgmt_category(mgmt: str) -> str:
    """Normalize the published `management` text into a coarse ownership bucket.

    Govt is checked first so 'Govt- Society' / 'Govt. Society' classify as
    Government (they are state-managed). Order of the rest is by specificity.
    """
    m = (mgmt or "").lower()
    if m.startswith("govt"):
        return "Government"
    if "deemed" in m:
        return "Deemed"
    if "trust" in m:
        return "Trust"
    if "society" in m:
        return "Society"
    if "private" in m:
        return "Private"
    return "Other"


def _year(s):
    """A 4-digit year found in the cell, else None.

    Some rows have the management value wrap across the column boundary (e.g.
    'Govt. Societ' | 'y 2024'), polluting the year cell with a stray leading
    'y '. Pulling the first 4-digit run recovers the year cleanly.
    """
    m = re.search(r"\b(\d{4})\b", str(s) if s is not None else "")
    return int(m.group(1)) if m else None


def build_df() -> pd.DataFrame:
    rows = []
    last_state = ""
    with pdfplumber.open(PDF) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages:
            for tbl in page.extract_tables():
                if not tbl:
                    continue
                for r in tbl:
                    if not r or len(r) < 8:
                        continue
                    sl_no = (r[C_SLNO] or "").strip()
                    if not sl_no.isdigit():
                        # title row, repeated header, or grand-total footer
                        continue
                    state = _norm(r[C_STATE])
                    if state:
                        last_state = state
                    else:
                        state = last_state  # forward-fill
                    rows.append({
                        "snapshot": SNAPSHOT,
                        "sl_no": int(sl_no),
                        "state": state,
                        "college": _norm(r[C_COLLEGE]),
                        "district": _norm(r[C_DISTRICT]),
                        "university": _norm(r[C_UNIVERSITY]),
                        "management_category": _mgmt_category(_norm(r[C_MGMT])),
                        "management": _norm(r[C_MGMT]),
                        "year_of_inception": _year(r[C_YEAR]),
                        "annual_intake_seats": _to_int(r[C_SEATS]),
                    })

    df = pd.DataFrame(rows, columns=COLUMNS)
    # De-dupe on the grain (a page break never splits a row here, but enforce it).
    df = df.drop_duplicates(["snapshot", "sl_no"], keep="first").reset_index(drop=True)
    print(f"  parsed {n_pages} pages → {len(df):,} college rows")
    return df


def main() -> None:
    df = build_df()

    # Pandas nullable integers — year_of_inception is nullable (rare misses).
    for col in ["sl_no", "year_of_inception", "annual_intake_seats"]:
        df[col] = df[col].astype("Int64")

    out = TABLES[0].local_path
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False, engine="pyarrow")

    total_seats = int(df["annual_intake_seats"].sum())
    print(f"\nnmc → {out.name}: {len(df):,} rows")
    print(f"  total annual intake (MBBS seats) = {total_seats:,}")
    print(f"  states/UTs = {df['state'].nunique()}")
    govt = df["management"].str.startswith("Govt").sum()
    print(f"  management: {govt:,} Govt* | {len(df) - govt:,} other")
    print("  by management:")
    for m, n in df["management"].value_counts().items():
        seats = int(df.loc[df["management"] == m, "annual_intake_seats"].sum())
        print(f"    {m:<16} {n:>4} colleges  {seats:>8,} seats")


if __name__ == "__main__":
    main()
