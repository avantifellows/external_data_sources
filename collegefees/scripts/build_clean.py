"""
Clean the hand-collected fee sheet into collegefees_costs.parquet.

What it does, and why:

1. DROPS MHT-CET entirely (an empty template — 2 of 111 colleges filled;
   shipping it would present 0.5% coverage as coverage) and drops rows with
   no fee data at all (unfilled template rows, not zero-fee colleges).

2. REBUILDS demographics from Demo_ID. The sheet's Gender/Caste columns are
   scrambled on ~31% of rows (a row can say Demo_ID='SC_PwD' but
   Caste='OBC-NCL'); Demo_ID is internally consistent and is the key the
   collectors actually worked from. JoSAA ids parse as
   {OPEN,EWS,OBC_NCL,SC,ST} × _PwD × _F; KCET ids are KEA seat-code pairs
   ('2AG2AH_KCET') — the caste code is parsed out, the pair kept verbatim.

3. REPAIRS the waived-total bug. On some tuition-waived rows the total
   column kept the FULL total instead of total-minus-tuition (verified
   against IIT Delhi's own PDF: waived total is 22,400, not 1,22,400).
   Where tuition = 0 and a full-fee sibling exists for the same
   (college, course), the total is recomputed as the sibling's
   total − tuition; total_was_corrected marks every repaired row.

4. ANNUALISES. Fees are quoted per semester or per year depending on the
   college; annual_* columns put everyone on one axis (semester × 2) so a
   comparison query can't silently mix the two. NITK-style nuance: the
   quoted figure is the FIRST semester/year — later terms are usually lower
   because one-time charges (admission, deposits) drop off. These are
   entry-year costs, not steady-state.

Usage:
  python3 scripts/build_clean.py [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, CLEAN_PARQUET, GRAIN, RAW_CSV

FREQ_PER_YEAR = {"Every semester": 2, "Every year": 1}

# intake anchors — numbers verified against the colleges' own fee documents
ANCHORS = [
    # counselling, college_id, course contains, demo_id, column, value
    ("JOSAA", "U-0100", "Computer Science", "OPEN",  "total_fee", 122400),
    ("JOSAA", "U-0100", "Computer Science", "SC",    "total_fee",  22400),  # repaired row
    ("JOSAA", "U-0237", "Computer Science", "OPEN",  "total_fee",  99070),
    ("JOSAA", "U-0237", "Computer Science", "OPEN",  "hostel_mess_fee", 8820),
    ("JOSAA", "U-0384", "Food Technology",  "OPEN",  "total_fee",  33000),
    ("JOSAA", "U-0046", "Mechanical",       "OPEN",  "total_fee",  21990),
]


def parse_demo(counselling: str, demo: str) -> tuple[str | None, bool | None, bool | None]:
    """→ (category, is_female, is_pwd). KCET encodes neither gender nor PwD."""
    if counselling == "JOSAA":
        is_f = demo.endswith("_F")
        core = demo[:-2] if is_f else demo
        is_pwd = core.endswith("_PwD")
        if is_pwd:
            core = core[:-4]
        return core, is_f, is_pwd
    if counselling == "KCET":
        m = re.match(r"(1|2A|2B|3A|3B|GM|SC|ST)", demo)
        return (m.group(1) if m else None), None, None
    return None, None, None


def build() -> pd.DataFrame:
    df = pd.read_csv(RAW_CSV, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    n0 = len(df)

    df = df[df["Counselling"] != "MHTCET"]
    df = df.drop_duplicates()
    dupes = n0 - len(df)

    out = pd.DataFrame({
        "counselling":  df["Counselling"],
        "college_id":   df["College ID"].astype(str).str.strip(),
        "college_name": df["College Name"].str.strip(),
        "course_name":  df["Course Name"].str.strip(),
        "branch_id":    df["Branch_ID"],
        "demo_id":      df["Demo_ID"].astype(str).str.strip(),
        "tuition_fee":  pd.to_numeric(df["Tuition Fees (INR)"], errors="coerce"),
        "total_fee":    pd.to_numeric(df["Tuition + Exam + ECAs + Development Fee"],
                                      errors="coerce"),
        "fee_frequency": df["Frequency of Payment.1"].str.strip(),
        "hostel_available": df["Hostel Availability"].map(
            {"Yes": True, "No": False}),
        "hostel_mess_fee": pd.to_numeric(df["Hostel and mess fee (INR)"],
                                         errors="coerce"),
        "hostel_fee_frequency": df["Frequency of Payment.2"].str.strip(),
        "source_url":   df["Source Link"].str.strip(),
    })

    # unfilled template rows carry no information — drop, don't ship as zeroes
    filled = out[["tuition_fee", "total_fee", "hostel_mess_fee"]].notna().any(axis=1)
    out = out[filled].copy()

    parsed = [parse_demo(c, d) for c, d in zip(out["counselling"], out["demo_id"])]
    out["category"]  = [p[0] for p in parsed]
    out["is_female"] = [p[1] for p in parsed]
    out["is_pwd"]    = [p[2] for p in parsed]

    # one canonical display name per college id (the sheet has up to 6 spellings)
    canon = out.groupby("college_id")["college_name"].agg(
        lambda s: s.value_counts().idxmax())
    out["college_name"] = out["college_id"].map(canon)

    # ── repair the waived-total bug ─────────────────────────────────────────
    key = ["counselling", "college_id", "course_name"]
    full = out[out["tuition_fee"] > 0]
    other = (full["total_fee"] - full["tuition_fee"]).groupby(
        [full[k] for k in key]).median().rename("other_fees")
    out = out.merge(other, left_on=key, right_index=True, how="left")
    bad = (
        (out["tuition_fee"] == 0)
        & out["other_fees"].notna()
        & (out["total_fee"] > out["other_fees"] * 1.5)
    )
    out["total_was_corrected"] = bad
    out.loc[bad, "total_fee"] = out.loc[bad, "other_fees"]
    out = out.drop(columns="other_fees")
    print(f"  repaired {int(bad.sum()):,} waived rows whose total kept the full fee")

    # ── annualise ───────────────────────────────────────────────────────────
    out["annual_total_fee"] = out["total_fee"] * out["fee_frequency"].map(FREQ_PER_YEAR)
    out["annual_hostel_mess_fee"] = (
        out["hostel_mess_fee"] * out["hostel_fee_frequency"].map(FREQ_PER_YEAR))

    # ── grain ───────────────────────────────────────────────────────────────
    grain = list(GRAIN)
    before = len(out)
    out = out.drop_duplicates(grain + ["total_fee", "tuition_fee",
                                       "hostel_mess_fee"])
    same_val = before - len(out)

    # Real conflicts come in two audited shapes:
    #   a) WAIVER DUPLICATES — an SC/ST/PwD bucket quoted both waived and at
    #      full tuition. The colleges' own documents (IIT Delhi, NITK) say
    #      these categories are tuition-exempt, so the waived row wins.
    #   b) PAID VARIANTS — both rows charge tuition but totals differ a few
    #      thousand (optional charges). Keep the HIGHER total: for a student
    #      budgeting, the conservative number is the honest default.
    dup_mask = out.duplicated(grain, keep=False)
    if dup_mask.any():
        waiver_cat = out["is_pwd"].fillna(False) | out["category"].isin(["SC", "ST"])
        out["_pref"] = 0
        # (a): waived row wins for waiver categories, paid row otherwise
        out.loc[dup_mask & waiver_cat & (out["tuition_fee"] == 0), "_pref"] = 2
        out.loc[dup_mask & ~waiver_cat & (out["tuition_fee"] > 0), "_pref"] = 2
        n_conf = int(out[dup_mask].groupby(grain).ngroups)
        out = (out.sort_values(["_pref", "total_fee"], ascending=False)
                  .drop_duplicates(grain, keep="first")
                  .drop(columns="_pref"))
        print(f"  resolved {n_conf:,} conflicting seat-buckets "
              f"(waiver duplicates → waived row; paid variants → higher total); "
              f"collapsed {same_val:,} same-value repeats")

    print(f"  {n0:,} sheet rows → {len(out):,} clean "
          f"({dupes:,} exact dupes, MHT-CET and unfilled rows dropped)")
    for c in ("JOSAA", "KCET"):
        s = out[out["counselling"] == c]
        print(f"    {c}: {len(s):,} rows, {s['college_id'].nunique()} colleges")

    # ── anchors ─────────────────────────────────────────────────────────────
    for cns, cid, course, demo, col, want in ANCHORS:
        s = out[(out.counselling == cns) & (out.college_id == cid)
                & out.course_name.str.contains(course)
                & (out.demo_id == demo)]
        got = s[col].iloc[0] if len(s) else None
        assert got == want, f"anchor {cid}/{course}/{demo} {col}: {got} != {want}"
    print(f"  {len(ANCHORS)} anchors verified against source documents")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    df = build()
    if args.dry_run:
        print("[dry-run] not writing")
        return
    CLEAN.mkdir(exist_ok=True)
    df.to_parquet(CLEAN_PARQUET, index=False)
    print(f"wrote {CLEAN_PARQUET} ({len(df):,} rows × {len(df.columns)} cols)")


if __name__ == "__main__":
    main()
