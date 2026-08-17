"""Build and validate the clean TG-EAPCET / Telangana engineering cutoff fact.

The authoritative raw CSVs are produced from the official TG-EAPCET Last Rank
Statement PDFs by ``state_TG.py`` in ``avantifellows/futures-v2``
(``state_cet/scrape/scripts/``). This step widens the govt-scope canonical
columns to ALL institute types, validates source anchors and the declared
grain, and writes deterministic Parquet bytes for GCS/BigQuery.

Raw files in ``tgeapcet/raw/``:
  TG_engg_all_cutoffs_2025.csv          required  per-phase, every inst type
  TG_engg_closing_ranks_govt_2025.csv   required  govt subset, canonical cols

WHY TWO FILES. The upstream parser emits the full canonical column set (state /
cet_name / quota / round / rank_basis / ...) only for the govt-scope subset,
and a leaner per-phase view for all institute types. BQ wants ALL colleges WITH
the canonical columns — the same choice kcet/, mhtcet/ and gujcet/ make, where
govt scope is a *query* (college_type IN (...)) rather than a pipeline
decision. So this script takes the all-types rows as the row set, re-runs the
parser's own MAX-across-phases aggregation, and reuses the parser's own
``classify_tg_college`` rather than duplicating that logic here.

THE LINE-WRAP TRAP. Institute and branch names wrap across lines in the source
PDFs, and the wrap point is NOT stable between phase files — the same seat can
appear as "ELECTRONICS AND COMMUNICATION ENGINEERING" in P1 and "ELECTRONICS
AND COMMUNICATION\\nENGINEERING" in P2. Grouping on the raw string splits one
seat into two and makes MAX() blind to the other phase (this shipped a closing
rank understated by 97,365 in review). Some wraps also split a word mid-token
("MAHABUBABA\\nD"), so collapsing whitespace to a single space is not enough —
we group on an all-whitespace-STRIPPED key and pick the most common cleanly
spaced spelling for display. Same approach as the upstream parser.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, RAW

ALL_FILE = "TG_engg_all_cutoffs_2025.csv"
GOVT_FILE = "TG_engg_closing_ranks_govt_2025.csv"
YEAR = 2025

OUTPUT_COLS = [
    "state", "cet_name", "stream", "year", "round",
    "college_code", "college_name", "place", "district",
    "college_type", "institute_type_raw", "coed",
    "branch_code", "branch_name", "affiliated_to",
    "quota", "category_raw", "category", "gender",
    "opening_rank", "closing_rank",
    "rank_basis", "source_url",
]
# One row per (college, branch, raw category, year). category_raw rather than
# category, because the canonical rollup folds BC_A..BC_E into OBC-NCL and
# SC_I..SC_III into SC and is deliberately non-unique. gender is already
# encoded inside category_raw (OC_BOYS / OC_GIRLS), so it is not a grain key.
GRAIN = ["college_code", "branch_code", "category_raw", "year"]

CANONICAL_CATEGORIES = {"GEN", "EWS", "OBC-NCL", "SC", "ST"}
COLLEGE_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept", "Private/SF"}
GOVT_SCOPE = ["Govt", "Govt-Aided", "State-Univ-Dept"]


def _load_parser():
    """Import state_TG from futures-v2 so classification stays single-sourced.

    Set TG_PARSER_DIR to point at futures-v2/state_cet/scrape/scripts. Falls
    back to a sibling checkout, which is the usual local layout.
    """
    candidates = []
    if os.environ.get("TG_PARSER_DIR"):
        candidates.append(Path(os.environ["TG_PARSER_DIR"]) / "state_TG.py")
    candidates.append(
        Path.home() / "jan2023" / "futures-v2" / "state_cet" / "scrape"
        / "scripts" / "state_TG.py"
    )
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("state_TG", p)
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(p.parent))
            spec.loader.exec_module(mod)
            print(f"Using upstream classifier: {p}")
            return mod
    raise SystemExit(
        "Could not import state_TG.py — set TG_PARSER_DIR to "
        "futures-v2/state_cet/scrape/scripts so college_type mapping stays "
        "identical to the parser."
    )


def _clean(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip()


def _match_key(s) -> str:
    return re.sub(r"\s+", "", str(s)).upper()


def build() -> pd.DataFrame:
    tg = _load_parser()

    for f in (ALL_FILE, GOVT_FILE):
        if not (RAW / f).exists():
            raise SystemExit(f"Missing required raw source: {RAW / f}")

    print(f"Reading: {ALL_FILE}")
    df = pd.read_csv(RAW / ALL_FILE)
    govt = pd.read_csv(RAW / GOVT_FILE)

    # Provenance/basis strings come from the govt file so they stay
    # byte-identical to what the parser declared — not retyped here.
    row0 = govt.iloc[0]
    for col in ("state", "cet_name", "stream", "round", "quota",
                "rank_basis", "source_url"):
        df[col] = row0[col]
    df["year"] = YEAR

    # ── collapse the PDF line-wrap variants before aggregating ───────────────
    for c in ("college_name", "branch_name", "place", "affiliated_to"):
        df[f"{c}_key"] = df[c].map(_match_key)
        df[c] = df[c].map(_clean)

    # ── MAX across phases, for ALL institute types ───────────────────────────
    # Group on college_code, not on any form of college_name. The code is the
    # identity the source guarantees; names are display-only and are picked by
    # mode below. (Two distinct codes legitimately share a name — ESUT/ESUTSF
    # are the regular and self-finance streams of the same university, TCEK and
    # TCTK are two Trinity campuses — so grouping by name would merge them.)
    #
    # The upstream parser already repairs the two PDF text defects before
    # writing this file: line-wraps whose position shifts between phase files,
    # and institute names garbled by overlapping text runs
    # ("KEAORTTHHA GSCUIDENEMCE)S" = "EARTH SCIENCES" interleaved with
    # "KOTHAGUDEM"). The whitespace-stripped keys below are belt-and-braces
    # against a wrap the parser has not seen.
    group_keys = [
        "state", "cet_name", "stream", "year", "round", "quota",
        "rank_basis", "source_url",
        "college_code", "dist", "coed",
        "college_type_raw", "branch_code", "branch_name_key",
        "category_raw", "category", "gender",
    ]
    agg = (df.groupby(group_keys, dropna=False)
           .agg(college_name=("college_name", lambda s: s.value_counts().index[0]),
                place=("place", lambda s: s.value_counts().index[0]),
                branch_name=("branch_name", lambda s: s.value_counts().index[0]),
                affiliated_to=("affiliated_to", lambda s: s.value_counts().index[0]),
                opening_rank=("closing_rank", "min"),
                closing_rank=("closing_rank", "max"))
           .reset_index())

    agg = agg.rename(columns={"dist": "district",
                              "college_type_raw": "institute_type_raw"})
    agg["college_type"] = [
        tg.classify_tg_college(t, n, a)
        for t, n, a in zip(agg["institute_type_raw"], agg["college_name"],
                           agg["affiliated_to"])
    ]

    # ── types ────────────────────────────────────────────────────────────────
    agg["year"] = agg["year"].astype("Int64")
    # INT, not float: TG publishes whole state ranks with no tie suffix (unlike
    # KEA/ACPC, which print tied ranks as .5).
    for c in ("opening_rank", "closing_rank"):
        agg[c] = pd.to_numeric(agg[c], errors="coerce").astype("Int64")
    for c in ("college_name", "branch_name", "place", "district",
              "affiliated_to", "institute_type_raw", "college_code",
              "branch_code", "coed"):
        agg[c] = agg[c].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()

    out = agg[OUTPUT_COLS].copy()

    # ── invariants ───────────────────────────────────────────────────────────
    nulls = out.isna().any()
    if nulls.any():
        raise ValueError(f"Columns contain nulls: {nulls[nulls].index.tolist()}")

    if set(out["state"]) != {"TELANGANA"}:
        raise ValueError(f"Unexpected states: {sorted(set(out['state']))}")
    bad_cat = set(out["category"]) - CANONICAL_CATEGORIES
    if bad_cat:
        raise ValueError(f"Non-canonical category values: {sorted(bad_cat)}")
    bad_type = set(out["college_type"]) - COLLEGE_TYPES
    if bad_type:
        raise ValueError(f"Unexpected college_type values: {sorted(bad_type)}")
    bad_gender = set(out["gender"]) - {"Boys", "Girls"}
    if bad_gender:
        raise ValueError(f"Unexpected gender values: {sorted(bad_gender)}")

    dup = out.duplicated(GRAIN, keep=False)
    if dup.any():
        sample = out.loc[dup, GRAIN + ["college_name", "closing_rank"]].head(10)
        raise ValueError(f"Duplicate declared grain:\n{sample.to_string(index=False)}")

    # opening_rank is the best (lowest) rank seen across phases, closing_rank
    # the worst — the reverse would mean the MAX/MIN got swapped.
    inverted = out[out["opening_rank"] > out["closing_rank"]]
    if len(inverted):
        raise ValueError(f"{len(inverted)} rows have opening_rank > closing_rank")

    # ── source anchors ───────────────────────────────────────────────────────
    # Expected to fail on a refresh. When they do, confirm the change is real
    # (TGCHE republished, or an upstream parser fix) and update in the SAME
    # commit as the cause — never relax an assertion to make a build pass.
    govt_rows = out[out["college_type"].isin(GOVT_SCOPE)]
    expected = {
        "rows": 20_449,
        "colleges": 162,
        "govt_rows": 1_936,
        "govt_colleges": 20,
    }
    actual = {
        "rows": len(out),
        "colleges": int(out["college_code"].nunique()),
        "govt_rows": len(govt_rows),
        "govt_colleges": int(govt_rows["college_code"].nunique()),
    }
    if actual != expected:
        raise ValueError(f"TG-EAPCET source anchors changed: expected {expected}, got {actual}")

    # JNTUH Hyderabad CSE, OC Boys — read off the Final Phase PDF. This is the
    # hardest govt seat in the state and the parser's own sanity check.
    jnt = out[(out["college_code"] == "JNTH")
              & (out["branch_code"] == "CSE")
              & (out["category_raw"] == "OC_BOYS")]
    if len(jnt) != 1:
        raise ValueError(f"Expected exactly 1 JNTUH CSE OC_BOYS row, got {len(jnt)}")
    if int(jnt.iloc[0]["closing_rank"]) != 1228:
        raise ValueError(
            f"Expected JNTUH CSE OC_BOYS closing_rank 1228; got {jnt.iloc[0]['closing_rank']}")

    # The line-wrap regression guard: this seat was split across two rows
    # (147,994 and 50,629) before the fix. One row, the higher rank.
    jnmb = out[(out["college_code"] == "JNMB")
               & (out["branch_code"] == "ECE")
               & (out["category_raw"] == "BC_C_GIRLS")]
    if len(jnmb) != 1 or int(jnmb.iloc[0]["closing_rank"]) != 147994:
        raise ValueError(
            "Line-wrap regression: JNMB/ECE/BC_C_GIRLS must be exactly 1 row "
            f"closing at 147994; got {len(jnmb)} row(s) "
            f"{jnmb['closing_rank'].tolist()}")

    # SF is a self-finance stream inside a state university — it fills at
    # private-level ranks, so it must NOT land in govt scope.
    sf = out[out["institute_type_raw"] == "SF"]
    if len(sf) and set(sf["college_type"]) != {"Private/SF"}:
        raise ValueError(
            f"SF colleges must not be govt-scope; got {sorted(set(sf['college_type']))}")

    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = ap.parse_args()

    df = build()
    print(f"\nValidated {len(df):,} rows")
    print("\n  rows per college_type:")
    print(df["college_type"].value_counts().to_string())
    print("\n  rows per canonical category:")
    print(df["category"].value_counts().to_string())
    print("\n  rows per gender:")
    print(df["gender"].value_counts().to_string())
    govt = df[df["college_type"].isin(GOVT_SCOPE)]
    print(f"\n  govt scope: {len(govt):,} rows / "
          f"{govt['college_code'].nunique()} colleges")

    if args.dry_run:
        print("\n[dry-run] No file written.")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    out = CLEAN / "tgeapcet_fact_cutoffs.parquet"
    df.to_parquet(out, index=False)
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
