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
from collections import Counter
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


# ─── State canonicalisation + column-bleed repair ─────────────────────────────
# The PDF wraps the State cell mid-word, and pdfplumber assigns the wrapped tail
# to the NEXT column. That corrupts BOTH fields at once, e.g.
#     state = 'Maharashtr'   college = 'Government Medical\na\nCollege,Nashik'
#     state = 'Uttar Prade'  college = 'Autonomous State\nsh\nMedical College Sultanpur'
# Left unrepaired this produced 39 distinct "states" for 36 real ones — 156 of
# 780 colleges (20%) carried a broken state — and 11 college names had the
# state's tail letters embedded in the middle of them.
#
# Why this matters downstream: the college-mapping join is STATE-SCOPED, so a
# corrupted state means every college in it fails to match. NMC sat at 52%
# coverage, the lowest of any source, and ~42% of that gap is these rows.
# It was being patched downstream with a hardcoded corruption dict
# (_NMC_STATE_FIXUP in external_data_sources metadata/); fixing it at the parse
# step means every consumer gets clean values and the dict can go.
#
# The repair is deterministic and self-validating: a stray fragment is only
# removed from the college name if it COMPLETES the truncated state name.
CANONICAL_STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam",
    "Bihar", "Chandigarh", "Chhattisgarh", "Dadra and Nagar Haveli", "Delhi", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand",
    "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra",
    "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab",
    "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal",
]

# Historical / alternate official names still printed in the PDF.
_STATE_RENAMES = {"orissa": "Odisha", "pondicherry": "Puducherry",
                  "chattisgarh": "Chhattisgarh"}


def _state_key(s) -> str:
    """Letters only, with 'and' dropped, so 'Jammu & Kashmir', 'Jammu and
    Kashmir' and 'JammuKashmir' all collapse to one key."""
    return re.sub(r"and", "", re.sub(r"[^a-z]", "", str(s or "").lower()))


_STATE_BY_KEY: dict[str, str] = {}
for _c in CANONICAL_STATES:
    _STATE_BY_KEY.setdefault(_state_key(_c), _c)
_RENAME_BY_KEY = {_state_key(k): v for k, v in _STATE_RENAMES.items()}


def canonical_state(raw) -> str | None:
    """Resolve a possibly-truncated/renamed state cell to its canonical name.

    Exact key match, then rename, then UNIQUE prefix — the prefix rule is what
    recovers the truncations ('Maharashtr', 'Uttar Prade', 'Madhya Pra',
    'West Benga', 'Uttarakhan'). Ambiguous prefixes return None rather than
    guessing.
    """
    k = _state_key(raw)
    if not k:
        return None
    if k in _STATE_BY_KEY:
        return _STATE_BY_KEY[k]
    if k in _RENAME_BY_KEY:
        return _RENAME_BY_KEY[k]
    hits = sorted({v for key, v in _STATE_BY_KEY.items() if key.startswith(k)})
    return hits[0] if len(hits) == 1 else None


# Tails that a truncated state may have shed into the college cell, keyed by the
# truncated form. Derived from CANONICAL_STATES rather than hand-listed.
_MISSING_STATE_TAILS: dict[str, tuple[str, ...]] = {}
for _c in CANONICAL_STATES:
    _full = re.sub(r"[^A-Za-z]", "", _c)
    for _i in range(3, len(_full)):
        _MISSING_STATE_TAILS.setdefault(
            _state_key(_full[:_i]), ()
        )
        _MISSING_STATE_TAILS[_state_key(_full[:_i])] += (_full[_i:],)

# Words the interleave repair is allowed to produce. Keeping this closed means the
# repair can never invent a word that was not there.
_COMMON_COLLEGE_WORDS = {
    "university", "government", "institute", "medical", "sciences", "college",
    "hospital", "research", "autonomous", "memorial",
}


def _deinterleave(token: str, frag: str) -> str | None:
    """Strip frag's characters out of token in order.

    Returns None unless every character of frag is consumed in sequence, so a
    word that merely contains the letters (e.g. 'Deshmukh' for 'desh') is left
    alone.
    """
    out, fi = [], 0
    for ch in token:
        if fi < len(frag) and ch == frag[fi]:
            fi += 1
        else:
            out.append(ch)
    return "".join(out) if fi == len(frag) else None


def repair_state_bleed(raw_state, raw_college) -> tuple[str | None, str]:
    """Recover a state whose tail bled into the college cell, and strip that
    tail out of the college name.

    Only fires when the fragment actually completes a canonical state name, so
    it cannot corrupt a legitimate college name.
    """
    col = str(raw_college or "")
    st_letters = re.sub(r"[^A-Za-z]", "", str(raw_state or ""))
    direct = canonical_state(raw_state)

    # Worst case: the fragment is INTERLEAVED into a college word rather than left
    # on its own line — 'Madhya Pra' + 'desh' produced 'dUensihversity' (desh woven
    # through University) and 'dGeosvhernment' (through Government). Removing the
    # fragment's characters in order restores the real word. Guarded: it only
    # applies if every fragment char is consumed in sequence AND the result is a
    # plausible word, so 'Deshmukh' and ordinary text are untouched.
    for frag in _MISSING_STATE_TAILS.get(_state_key(raw_state), ()):
        for tok in re.findall(r"[A-Za-z]{6,}", col):
            fixed = _deinterleave(tok, frag)
            if fixed and fixed.lower() in _COMMON_COLLEGE_WORDS:
                col = col.replace(tok, fixed, 1)
    # Fragment lengths seen in this PDF: 1 ("a", "d", "l", "y") up to 4 ("desh").
    # Bounded at 4 so a genuine short word on its own line is not mistaken for one.
    for frag in re.findall(r"(?:^|\n)([A-Za-z]{1,4})(?=\n)", col):
        completed = canonical_state(st_letters + frag)
        # Strip the fragment whenever it completes a canonical state — even if the
        # truncated cell ALSO resolved on its own via the prefix rule. ('Uttar Prade'
        # resolves to Uttar Pradesh by prefix, but the 'sh' still has to come out of
        # 'Autonomous State sh Medical College'.) Requiring the state to be
        # unresolvable first left 10 college names polluted.
        if completed and (direct is None or completed == direct):
            return completed, re.sub(
                r"(?:^|\n)" + re.escape(frag) + r"(?=\n)", "\n", col, count=1)
    return direct, col


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
    unresolved_states: Counter[str] = Counter()
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
                    # Resolve the state to its canonical name, repairing the
                    # case where its wrapped tail bled into the college cell.
                    state, college_raw = repair_state_bleed(r[C_STATE], r[C_COLLEGE])
                    if state:
                        last_state = state
                    else:
                        # Blank cell (the PDF prints the state once per block) or
                        # an unresolvable value -> carry the previous state.
                        state = last_state
                        if _norm(r[C_STATE]):
                            unresolved_states[_norm(r[C_STATE])] += 1
                    rows.append({
                        "snapshot": SNAPSHOT,
                        "sl_no": int(sl_no),
                        "state": state,
                        "college": _norm(college_raw),
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
    if unresolved_states:
        print(f"  !! {len(unresolved_states)} state value(s) could not be canonicalised "
              f"(carried forward): {dict(unresolved_states)}")
    else:
        print(f"  states canonicalised cleanly → {df['state'].nunique()} distinct")
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
