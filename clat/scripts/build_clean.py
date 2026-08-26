"""
Build clat_fact_cutoffs from the consortium's own Cut-Off Rank Tables.

Each final-list PDF ends with an official per-category summary (seats, AIR
cut-off, category-rank cut-off). That table — not our own aggregation of the
candidate rows — is the authority: the consortium attributes overlay admits
(PwD/Women/NCC…) to the overlay row, so a naive max-per-vertical derivation
disagrees with it by construction. The candidate-level extract is kept
alongside for audits.

'**' in the source (seats with no published cutoff) becomes NULL —
seats_filled stays, the rank is honestly absent.

The category code is decomposed demographic-table-style into
(category_canonical, domicile_state, subgroup, is_women_row, is_pwd_row,
special_quota) so the app can drive a five-value category dropdown + a
home-state dropdown + two toggles instead of a 168-value picker.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, CLEAN_PARQUET, EXTRACTED

STATE = {
    "AP": "Andhra Pradesh", "AS": "Assam", "BH": "Bihar", "BR": "Bihar",
    "CHT": "Chhattisgarh", "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana",
    "HP": "Himachal Pradesh", "JD": "Jharkhand", "JH": "Jharkhand",
    "KA": "Karnataka", "KL": "Kerala", "MP": "Madhya Pradesh",
    "MH": "Maharashtra", "OD": "Odisha", "PB": "Punjab", "RJ": "Rajasthan",
    "TN": "Tamil Nadu", "TR": "Tripura", "UP": "Uttar Pradesh",
    "UK": "Uttarakhand", "WB": "West Bengal", "DNH": "Dadra and Nagar Haveli and Daman and Diu",
    "TL": "Telangana", "TG": "Telangana",
}
SPECIAL = {"NCC", "CAP", "ESP", "CDP", "DFF", "DSC", "TFF", "FF", "SP",
           "DOM", "XS", "WXS", "KM", "TIB"}
OBC_LIKE = {"BC", "BCM", "BCO", "EBC", "MBC", "SBC", "SEBC", "DTA", "DTB",
            "DTC", "DV", "NT", "NTB", "NTC", "NTD", "VJ", "DNT", "OBC"}


def decompose(code: str, label: str):
    toks = code.split("-")
    state = sub = special = None
    women = pwd = False
    if toks and re.fullmatch(r"G\d", toks[-1]):
        sub = toks[-1]; toks = toks[:-1]
    if len(toks) > 1 and toks[-1] in STATE:
        state = STATE[toks[-1]]; toks = toks[:-1]
    head = "-".join(toks)
    lab = label.lower()
    if head == "W" or lab.startswith("women"):
        women = True
        head = toks[1] if len(toks) > 1 else "General"
    if "PWD" in code:
        pwd = True
    base = head.split("-")[0]
    if base in SPECIAL:
        special = head
        canon = None
    elif base in ("General", "GC", "GEN") or "general" in lab.split("(")[0].lower():
        canon = "GEN"
    elif base == "EWS":
        canon = "EWS"
    elif base in OBC_LIKE:
        canon = "OBC" if base == "OBC" else "OBC-like"
        if base.startswith("BC") and len(head) > 2:
            sub = sub or head
    elif base == "SC":
        canon = "SC"
    elif base == "ST":
        canon = "ST"
    elif base == "PWD":
        canon = None
    elif base == "SCO":
        canon = "SC"      # SC (Others) — Tamil Nadu's SC minus Arunthathiyar
    elif re.match(r"most backward|backward class", lab):
        canon = "OBC-like"  # TN labels whose printed code got line-wrapped
    else:
        canon = None
        special = special or head
    return canon, state, sub, women, pwd, special


# An NLU's state-roster rows sometimes print without the state suffix
# (GNLU's plain 'SEBC'; TN labels whose code got line-wrapped). Those rows
# are the NLU's OWN-state quota by construction, so the domicile falls back
# to the university's home state. All-India codes never take this fallback.
NLU_STATE = [
    ("DSNLU", "Andhra Pradesh"), ("NLUJA", "Assam"), ("CNLU", "Bihar"),
    ("HNLU", "Chhattisgarh"), ("Silvassa", "Dadra and Nagar Haveli and Daman and Diu"),
    ("Goa", "Goa"), ("Gandhinagar", "Gujarat"), ("DBRANLU", "Haryana"),
    ("Sonepat", "Haryana"), ("HPNLU", "Himachal Pradesh"),
    ("NUSRL", "Jharkhand"), ("NLSIU", "Karnataka"), ("NUALS", "Kerala"),
    ("MPDNLU", "Madhya Pradesh"), ("NLIU", "Madhya Pradesh"),
    ("MNLU", "Maharashtra"), ("NLUO", "Odisha"), ("RGNUL", "Punjab"),
    ("Jodhpur", "Rajasthan"), ("TNNLU", "Tamil Nadu"),
    ("NLUT", "Tripura"), ("RMLNLU", "Uttar Pradesh"),
    ("RPNLUP", "Uttar Pradesh"), ("WBNUJS", "West Bengal"),
    ("NALSAR", "Telangana"),
]
ALL_INDIA_CODES = {"General", "EWS", "OBC", "SC", "ST", "PWD", "W"}


def nlu_state(college: str) -> str | None:
    for key, st in NLU_STATE:
        if key in college:
            return st
    return None


def main() -> None:
    o = pd.read_csv(EXTRACTED / "clat_cutoff_tables_2026.csv")
    dec = [decompose(str(r.category_code), str(r.category_label))
           for r in o.itertuples()]
    o["category_canonical"] = [d[0] for d in dec]
    o["domicile_state"]     = [d[1] for d in dec]
    o["subgroup"]           = [d[2] for d in dec]
    o["is_women_row"]       = [d[3] for d in dec]
    o["is_pwd_row"]         = [d[4] for d in dec]
    o["special_quota"]      = [d[5] for d in dec]
    # women/PwD overlay rows are horizontal quotas, not domicile-restricted —
    # never state-ify them
    fallback = (o.domicile_state.isna()
                & o.category_canonical.notna()
                & ~o.is_women_row & ~o.is_pwd_row
                & ~o.category_code.isin(ALL_INDIA_CODES))
    o.loc[fallback, "domicile_state"] = o.loc[fallback, "college"].map(nlu_state)
    print(f"  domicile inferred from the NLU's own state on "
          f"{int(fallback.sum())} suffix-less state-roster rows")
    o["rank_basis"] = "CLAT 2026 All India Rank"
    o["list_basis"] = "5th (final) allotment list, 2026-05-20"

    grain = ["year", "college", "program", "category_label"]
    dupes = o[o.duplicated(grain, keep=False)]
    assert dupes.empty, f"duplicate grain rows:\n{dupes.head().to_string()}"

    def anchor(coll, code, col, want):
        s = o[o.college.str.contains(coll) & (o.category_code == code)
              & (o.program == "B.A. LL.B. (Hons.)")]
        got = s[col].iloc[0] if len(s) else None
        assert got == want, f"anchor {coll}/{code} {col}: {got} != {want}"
    anchor("NLSIU", "General", "air_cutoff", 120)
    anchor("NLSIU", "General", "seats", 121)
    anchor("DSNLU", "BC-D-AP", "air_cutoff", 7967)
    anchor("DSNLU", "PWD", "air_cutoff", 43433)

    print(f"  {len(o):,} rows | anchors ok | canonical coverage "
          f"{o.category_canonical.notna().mean()*100:.0f}% "
          f"(rest = special quotas/PwD rows, kept with canonical NULL)")
    print("  '**' rows (seats, no published cutoff):",
          int(o.air_cutoff.isna().sum()))
    CLEAN.mkdir(exist_ok=True)
    o.to_parquet(CLEAN_PARQUET, index=False)
    print(f"wrote {CLEAN_PARQUET} ({len(o):,} × {len(o.columns)})")


if __name__ == "__main__":
    main()
