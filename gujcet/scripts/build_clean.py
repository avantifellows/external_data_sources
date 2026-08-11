"""Build and validate the clean GUJCET / ACPC Gujarat cutoff fact.

The authoritative raw CSVs are produced from the official ACPC closure PDFs by
``state_GJ.py`` in ``avantifellows/futures-v2`` (``state_cet/scrape/scripts/``).
This step unions the streams, widens the govt-scope canonical columns to ALL
institute types, validates source anchors and the declared grain, and writes
deterministic Parquet bytes for GCS/BigQuery.

Raw files in ``gujcet/raw/``:
  GJ_engg_all_cutoffs_2025.csv           required  every institute type
  GJ_engg_closing_ranks_govt_2025.csv    required  govt subset, canonical cols
  GJ_pharm_all_cutoffs_2024.csv          required
  GJ_pharm_closing_ranks_govt_2024.csv   required

WHY TWO FILES PER STREAM. The upstream parser emits the full canonical column
set (state / cet_name / category / sub_pool / quota / ...) only for the
govt-scope subset, and a leaner 6-column view for all institute types. BQ wants
ALL colleges WITH the canonical columns — the same choice kcet/ and mhtcet/
make, where govt scope is a *query* (college_type IN (...)) rather than a
pipeline decision. So this script takes the all-types rows as the row set and
re-derives the canonical columns for every row, reusing the parser's own
``classify_gj_college`` / ``normalise_category`` rather than duplicating their
logic here.

TWO DIFFERENT ADMISSION YEARS. Engineering is 2025-26; pharmacy is 2024-25 (the
latest ACPC has published in this format). ``year`` keeps them apart — never
aggregate across streams without filtering on it.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, RAW, RAW_FILES

# Per stream: (all-types file, govt file, stream label, year, cet_name,
#              open-category code as written in that PDF)
STREAMS = [
    ("GJ_engg_all_cutoffs_2025.csv", "GJ_engg_closing_ranks_govt_2025.csv",
     "engineering", 2025, "ACPC-GUJCET", "OP"),
    ("GJ_pharm_all_cutoffs_2024.csv", "GJ_pharm_closing_ranks_govt_2024.csv",
     "pharmacy", 2024, "ACPC", "OPEN"),
]

OUTPUT_COLS = [
    "state", "cet_name", "stream", "year", "round",
    "college_name", "college_type", "institute_type_raw",
    "branch_name",
    "quota", "category_raw", "category", "sub_pool", "gender",
    "closing_rank", "closing_percentile",
    "rank_basis", "source_url",
]
# One row per (stream, college, branch, raw category, year). category_raw
# rather than category, because the canonical rollup folds TFWS/ESM into OTHER
# and is deliberately non-unique.
GRAIN = ["stream", "college_name", "branch_name", "category_raw", "year"]

CANONICAL_CATEGORIES = {"GEN", "EWS", "OBC-NCL", "SC", "ST", "OTHER"}
COLLEGE_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept", "Private/SF"}


def _load_parser():
    """Import state_GJ from futures-v2 so classification stays single-sourced.

    Set GJ_PARSER_DIR to point at futures-v2/state_cet/scrape/scripts. Falls
    back to a sibling checkout, which is the usual local layout.
    """
    candidates = []
    if os.environ.get("GJ_PARSER_DIR"):
        candidates.append(Path(os.environ["GJ_PARSER_DIR"]) / "state_GJ.py")
    candidates.append(
        Path.home() / "jan2023" / "futures-v2" / "state_cet" / "scrape"
        / "scripts" / "state_GJ.py"
    )
    for p in candidates:
        if p.exists():
            spec = importlib.util.spec_from_file_location("state_GJ", p)
            mod = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(p.parent))
            spec.loader.exec_module(mod)
            print(f"Using upstream classifier: {p}")
            return mod
    raise SystemExit(
        "Could not import state_GJ.py — set GJ_PARSER_DIR to "
        "futures-v2/state_cet/scrape/scripts so college_type and category "
        "mapping stay identical to the parser."
    )


def build() -> pd.DataFrame:
    gj = _load_parser()
    frames = []

    for all_file, govt_file, stream, year, cet_name, open_code in STREAMS:
        for f in (all_file, govt_file):
            if not (RAW / f).exists():
                raise SystemExit(f"Missing required raw source: {RAW / f}")

        print(f"Reading: {all_file}")
        df = pd.read_csv(RAW / all_file)
        govt = pd.read_csv(RAW / govt_file)

        # Provenance/basis strings come from the govt file so they stay
        # byte-identical to what the parser declared — not retyped here.
        row0 = govt.iloc[0]
        df["state"] = row0["state"]
        df["cet_name"] = cet_name
        df["stream"] = stream
        df["year"] = year
        df["round"] = row0["round"]
        df["quota"] = row0["quota"]
        df["source_url"] = row0["source_url"]
        df["rank_basis"] = row0["rank_basis_per_row"]

        # Re-derive the canonical columns for EVERY institute type using the
        # parser's own functions.
        df["college_type"] = [
            gj.classify_gj_college(t, n)
            for t, n in zip(df["institute_type_raw"], df["college_name"])
        ]
        cat = df["category_raw"].apply(lambda c: pd.Series(gj.normalise_category(c)))
        df["category"], df["sub_pool"] = cat[0], cat[1]
        # ACPC publishes one Home-State merit list per category; no separate
        # male/female pools, unlike Maharashtra's L*/G* split.
        df["gender"] = "All"

        frames.append(df)

    df = pd.concat(frames, ignore_index=True)

    # ── types ────────────────────────────────────────────────────────────────
    df["year"] = df["year"].astype("Int64")
    # FLOAT, not INT: ACPC publishes tied ranks with a .5 suffix (1 such row
    # in the 2025-26 engineering file, e.g. 36906.5) exactly as KEA does for
    # KCET. Casting to INT would silently round a real published value.
    df["closing_rank"] = pd.to_numeric(df["closing_rank"], errors="coerce").astype("Float64")
    df["closing_percentile"] = pd.to_numeric(
        df["closing_percentile"], errors="coerce").astype("Float64")
    for c in ("college_name", "branch_name", "institute_type_raw"):
        df[c] = (df[c].astype("string")
                 .str.replace(r"\s+", " ", regex=True).str.strip())
    df["sub_pool"] = df["sub_pool"].fillna("").astype("string")

    df = df[OUTPUT_COLS]

    # ── invariants ───────────────────────────────────────────────────────────
    # closing_percentile is legitimately NULL for pharmacy ESM rows: the PDF's
    # ESM_MERIT column is a column-boundary artifact (it always exactly equals
    # the rank), so the parser nulls it rather than shipping a fake percentile.
    never_null = [c for c in OUTPUT_COLS
                  if c not in {"sub_pool", "closing_percentile"}]
    nulls = df[never_null].isna().any()
    if nulls.any():
        raise ValueError(f"Required columns contain nulls: {nulls[nulls].index.tolist()}")

    if set(df["state"]) != {"GUJARAT"}:
        raise ValueError(f"Unexpected states: {sorted(set(df['state']))}")
    bad_cat = set(df["category"]) - CANONICAL_CATEGORIES
    if bad_cat:
        raise ValueError(f"Non-canonical category values: {sorted(bad_cat)}")
    bad_type = set(df["college_type"]) - COLLEGE_TYPES
    if bad_type:
        raise ValueError(f"Unexpected college_type values: {sorted(bad_type)}")

    dup = df.duplicated(GRAIN, keep=False)
    if dup.any():
        sample = df.loc[dup, GRAIN + ["closing_rank"]].head(10)
        raise ValueError(f"Duplicate declared grain:\n{sample.to_string(index=False)}")

    # ── source anchors ───────────────────────────────────────────────────────
    # Expected to fail on a refresh. When they do, confirm the change is real
    # (ACPC republished, or an upstream parser fix) and update in the SAME
    # commit as the cause — never relax an assertion to make a build pass.
    expected = {
        "rows": 2_487,
        "engineering_rows": 1_954,
        "pharmacy_rows": 533,
        "engineering_colleges": 133,
        "pharmacy_colleges": 118,
    }
    actual = {
        "rows": len(df),
        "engineering_rows": int((df["stream"] == "engineering").sum()),
        "pharmacy_rows": int((df["stream"] == "pharmacy").sum()),
        "engineering_colleges": int(
            df.loc[df["stream"] == "engineering", "college_name"].nunique()),
        "pharmacy_colleges": int(
            df.loc[df["stream"] == "pharmacy", "college_name"].nunique()),
    }
    if actual != expected:
        raise ValueError(f"GUJCET source anchors changed: expected {expected}, got {actual}")

    # L.D. College Computer Engineering — read digit-for-digit off page 3 of the
    # 2025-26 engineering closure PDF.
    ld = df[(df["college_name"].str.contains("L.D.College", regex=False, na=False))
            & (df["branch_name"] == "COMPUTER ENGINEERING")
            & (df["category_raw"] == "OP")]
    if len(ld) != 1:
        raise ValueError(f"Expected exactly 1 LDCE Computer Engineering OP row, got {len(ld)}")
    if int(ld.iloc[0]["closing_rank"]) != 646:
        raise ValueError(
            f"Expected LDCE CSE OP closing_rank 646; got {ld.iloc[0]['closing_rank']}")

    # PPP is a public-private-partnership college that fills like a private one.
    # The UP NEET parser's equivalent bug was classifying [PPP] as govt.
    ppp = df[df["institute_type_raw"] == "PPP"]
    if len(ppp) and set(ppp["college_type"]) != {"Private/SF"}:
        raise ValueError(
            f"PPP colleges must not be govt-scope; got {sorted(set(ppp['college_type']))}")

    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = ap.parse_args()

    df = build()
    print(f"\nValidated {len(df):,} rows")
    print("\n  rows per stream / year:")
    print(df.groupby(["stream", "year"]).size().to_string())
    print("\n  rows per college_type:")
    print(df["college_type"].value_counts().to_string())
    print("\n  rows per canonical category:")
    print(df["category"].value_counts().to_string())
    govt = df[df["college_type"].isin(["Govt", "Govt-Aided", "State-Univ-Dept"])]
    print(f"\n  govt scope: {len(govt):,} rows / "
          f"{govt['college_name'].nunique()} colleges")

    if args.dry_run:
        print("\n[dry-run] No file written.")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    out = CLEAN / "gujcet_fact_cutoffs.parquet"
    df.to_parquet(out, index=False)
    print(f"\nWritten: {out}")


if __name__ == "__main__":
    main()
