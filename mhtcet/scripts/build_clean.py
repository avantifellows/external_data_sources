"""Build and validate the clean MHT-CET 2025 cutoff fact.

The authoritative raw per-stream CSVs are produced from the official CET Cell
CAP PDFs by ``state_MH.py`` / ``state_MH_arch.py`` in
``avantifellows/futures-v2`` (``state_cet/scrape/scripts/``). This step unions
the streams, types columns, adds provenance, validates source anchors and the
declared grain, and writes deterministic Parquet bytes for GCS/BigQuery.

Raw files in ``mhtcet/raw/`` (one per stream, "all colleges" view):
  MH_engg_state_quota_closing_ranks_2025.csv      required
  MH_pharm_state_quota_closing_ranks_2025.csv     required
  MH_arch_state_quota_closing_ranks_2025.csv      required
  MH_bdesign_state_quota_closing_ranks_2025.csv   optional (3 private institutes)

Scope note: every college type ships, with ``college_type`` as a column.
Government scope is a query (``college_type IN ('Govt','Govt-Aided',
'State-Univ-Dept')``), not a pipeline decision — the same choice kcet/ makes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, OPTIONAL_RAW_FILES, RAW, RAW_FILES

# Architecture is admitted on a DIFFERENT exam and therefore a different rank
# space (MAH-AAC-CET / NATA merit, not the MHT-CET PCM state merit rank). It
# ships in the same table because the counselling process and reservation
# taxonomy are shared, but rank_basis must be filtered on before any
# cross-stream rank comparison.
STREAM_OF_FILE = {
    "MH_engg_state_quota_closing_ranks_2025.csv": "engineering",
    "MH_pharm_state_quota_closing_ranks_2025.csv": "pharmacy",
    "MH_arch_state_quota_closing_ranks_2025.csv": "architecture",
    "MH_bdesign_state_quota_closing_ranks_2025.csv": "bdesign",
}
PORTAL_OF_STREAM = {
    "engineering": "https://fe2025.mahacet.org/",
    "pharmacy": "https://ph2025.mahacet.org/",
    "architecture": "https://arch2025.mahacet.org.in/",
    "bdesign": "https://bdesigncap2025.mahacet.org/",
}

# The architecture parser names two columns differently (its raw reservation
# code is the PDF's "SeatType" column, and it counts allotments rather than
# rank observations). Harmonise on the engineering names — same meaning, and
# renaming here keeps one warehouse schema instead of two.
RENAME_PER_STREAM = {
    "architecture": {
        "seat_type": "category_raw",
        "allotted_count": "num_rank_observations",
    },
}

RAW_REQUIRED = [
    "state", "cet_name", "stream", "year", "round",
    "college_code", "college_name", "college_type", "status",
    "branch_code", "branch_name",
    "quota", "category_raw", "category", "gender", "sub_pool",
    "opening_rank", "closing_rank", "num_rank_observations",
    "last_round_with_max", "rank_basis",
]
OUTPUT_COLS = [
    "state", "cet_name", "stream", "year", "round",
    "college_code", "college_name", "college_type", "status",
    "branch_code", "branch_name",
    "quota", "category_raw", "category", "gender", "sub_pool",
    "opening_rank", "closing_rank", "num_rank_observations",
    # Architecture only: the CET Cell publishes a NATA/AAC-CET merit SCORE
    # alongside the merit number. NULL for the MHT-CET streams, which publish
    # no per-seat score.
    "opening_score", "closing_score",
    "last_round_with_max", "rank_basis", "source_file", "source_url",
]
SCORE_COLS = ["opening_score", "closing_score"]
# category_raw (not category) is part of the grain: the canonical `category`
# collapses many raw CET codes into 5 buckets + OTHER, so it is deliberately
# non-unique. `college_type` is in the grain because a handful of institutes
# genuinely run two funding pools under one college_code (03016 Bombay College
# of Pharmacy runs both Government-Aided and Un-Aided seats).
GRAIN = [
    "stream", "college_code", "branch_code", "quota", "category_raw",
    "college_type", "year",
]

CANONICAL_CATEGORIES = {"GEN", "EWS", "OBC-NCL", "SC", "ST", "OTHER"}
CANONICAL_GENDERS = {"All", "Girls"}
COLLEGE_TYPES = {
    "Govt", "Govt-Aided", "State-Univ-Dept",
    "Private-Unaided", "Private-Minority", "Deemed",
}


def _read(name: str, *, required: bool) -> pd.DataFrame | None:
    path = RAW / name
    if not path.exists():
        if required:
            raise SystemExit(f"Missing required raw source: {path}")
        print(f"Optional source absent, skipping: {name}")
        return None
    print(f"Reading: {name}")
    df = pd.read_csv(path, dtype={"college_code": "string", "branch_code": "string"})
    stream = STREAM_OF_FILE[name]
    if stream in RENAME_PER_STREAM:
        df = df.rename(columns=RENAME_PER_STREAM[stream])
    missing = sorted(set(RAW_REQUIRED) - set(df.columns))
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")
    df["source_file"] = name
    return df


def build() -> pd.DataFrame:
    frames = [_read(n, required=True) for n in RAW_FILES]
    frames += [_read(n, required=False) for n in OPTIONAL_RAW_FILES]
    df = pd.concat([f for f in frames if f is not None], ignore_index=True)

    # ── types ────────────────────────────────────────────────────────────────
    for col in ("opening_rank", "closing_rank", "num_rank_observations", "year"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    if df["closing_rank"].isna().any():
        raise ValueError("closing_rank contains null or non-numeric values")
    if df["opening_rank"].isna().any():
        raise ValueError("opening_rank contains null or non-numeric values")

    # college_name arrives with embedded newlines from pdftotext wrapping.
    for col in ("college_name", "branch_name", "status"):
        df[col] = (df[col].astype("string")
                   .str.replace(r"\s*\n\s*", " ", regex=True)
                   .str.replace(r"\s{2,}", " ", regex=True)
                   .str.strip())

    for col in SCORE_COLS:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Float64")

    df["sub_pool"] = df["sub_pool"].fillna("").astype("string")
    df["source_url"] = df["stream"].map(PORTAL_OF_STREAM)
    df = df[OUTPUT_COLS]

    # ── invariants ───────────────────────────────────────────────────────────
    never_null = [c for c in OUTPUT_COLS if c not in {"sub_pool", *SCORE_COLS}]
    nulls = df[never_null].isna().any()
    if nulls.any():
        raise ValueError(f"Required columns contain nulls: {nulls[nulls].index.tolist()}")

    if set(df["state"]) != {"MAHARASHTRA"}:
        raise ValueError(f"Unexpected states: {sorted(set(df['state']))}")
    if set(df["year"]) != {2025}:
        raise ValueError(f"Expected only 2025; got {sorted(set(df['year']))}")

    bad_cat = set(df["category"]) - CANONICAL_CATEGORIES
    if bad_cat:
        raise ValueError(f"Non-canonical category values: {sorted(bad_cat)}")
    bad_gender = set(df["gender"]) - CANONICAL_GENDERS
    if bad_gender:
        raise ValueError(
            f"Non-canonical gender values: {sorted(bad_gender)}. "
            "MHT-CET codes are G=General (gender-neutral) and L=Ladies, so the "
            "only valid values are 'All' and 'Girls' — 'Boys' means the "
            "upstream parser has regressed to reading G as male-only."
        )
    bad_type = set(df["college_type"]) - COLLEGE_TYPES
    if bad_type:
        raise ValueError(f"Unexpected college_type values: {sorted(bad_type)}")

    inverted = df["opening_rank"] > df["closing_rank"]
    if inverted.any():
        raise ValueError(f"{int(inverted.sum())} rows have opening_rank > closing_rank")

    # Horizontal flags (PWD / DEF / TFWS / ORPHAN / minority) must never be
    # folded into a base category — they carry sub_pool instead.
    flagged_in_base = df[(df["sub_pool"] != "") & (df["category"] == "EWS")]
    if len(flagged_in_base):
        raise ValueError("EWS rows must not carry a horizontal sub_pool flag")

    duplicates = df.duplicated(GRAIN, keep=False)
    if duplicates.any():
        sample = df.loc[duplicates, GRAIN + ["closing_rank"]].head(10)
        raise ValueError(f"Duplicate declared grain:\n{sample.to_string(index=False)}")

    # ── source anchors ───────────────────────────────────────────────────────
    # These pin the upstream parser. They are expected to change ONLY when the
    # CET Cell republishes or a parser bug is fixed — in which case update them
    # in the same commit as the parser change, never silently.
    expected = {
        "rows": 59_380,
        "engineering_rows": 46_662,
        "pharmacy_rows": 11_716,
        "architecture_rows": 983,
        "bdesign_rows": 19,
        "engineering_colleges": 372,
    }
    actual = {
        "rows": len(df),
        "engineering_rows": int((df["stream"] == "engineering").sum()),
        "pharmacy_rows": int((df["stream"] == "pharmacy").sum()),
        "architecture_rows": int((df["stream"] == "architecture").sum()),
        "bdesign_rows": int((df["stream"] == "bdesign").sum()),
        "engineering_colleges": int(
            df.loc[df["stream"] == "engineering", "college_code"].nunique()
        ),
    }
    if actual != expected:
        raise ValueError(f"MHT-CET source anchors changed: expected {expected}, got {actual}")

    # VJTI Computer Engineering, State Level, GOPENS — independently verified
    # against published 2025 cutoffs: CAP1 closed at 103, CAP2 at 119.
    vjti = df[
        (df["college_code"] == "03012")
        & (df["branch_code"] == "0301224510")
        & (df["quota"] == "State Level")
        & (df["category_raw"] == "GOPENS")
    ]
    if len(vjti) != 1:
        raise ValueError(f"Expected exactly 1 VJTI CSE GOPENS State Level row, got {len(vjti)}")
    row = vjti.iloc[0]
    if (row["opening_rank"], row["closing_rank"]) != (103, 119):
        raise ValueError(
            "Expected VJTI Computer Engineering GOPENS State Level "
            f"opening 103 / closing 119; got {row['opening_rank']} / {row['closing_rank']}"
        )

    # Bombay College of Pharmacy genuinely runs two funding pools under one
    # code. If this collapses to one type, the group key has regressed.
    bcp_types = set(df.loc[df["college_code"] == "03016", "college_type"])
    if bcp_types != {"Govt-Aided", "Private-Unaided"}:
        raise ValueError(
            f"College 03016 must retain both funding pools; got {sorted(bcp_types)}"
        )

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args()

    df = build()
    print(f"\nValidated {len(df):,} rows")
    print(f"  colleges (all streams): {df['college_code'].nunique()}")
    print("\n  rows per stream:")
    print(df["stream"].value_counts().to_string())
    print("\n  rows per college_type:")
    print(df["college_type"].value_counts().to_string())
    print("\n  rows per canonical category:")
    print(df["category"].value_counts().to_string())
    print("\n  gender split:")
    print(df["gender"].value_counts().to_string())

    if args.dry_run:
        print("\n[dry-run] No file written.")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    output = CLEAN / "mhtcet_fact_cutoffs.parquet"
    df.to_parquet(output, index=False)
    print(f"\nWritten: {output}")


if __name__ == "__main__":
    main()
