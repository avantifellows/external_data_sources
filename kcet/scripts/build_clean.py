"""Build and validate the clean KCET 2025 cutoff fact.

The authoritative raw cutoff CSV is produced from the two official KEA Round
3 PDFs by ``parse_KA_2025.py`` in ``avantifellows/futures-v2``. This step adds
warehouse metadata and provenance, optionally enriches known 2024 government
scope, validates source anchors and declared grain, and writes deterministic
Parquet bytes for GCS/BigQuery.

Raw files in ``kcet/raw/``:
  KA_engg_2025_all_cutoffs_R3.csv       required parsed fact
  KA_engg_2025_GEN_R3.pdf               required official GEN PDF
  KA_engg_2025_HK_R3.pdf                required official HK PDF
  KA_engg_closing_ranks_govt_2024.csv   optional historical classification

An unmatched 2024 classification is ``Unknown``—absence from a government-only
file is not evidence that a 2025 college is private.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, RAW

CUTOFFS_GLOB = "KA_engg_*_all_cutoffs_R*.csv"
GOVT_GLOB = "KA_engg_closing_ranks_govt_*.csv"

SOURCE_URLS = {
    "GEN": "https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_E_R_11092025english.pdf",
    "HK": "https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/PROF_CODE_E_H_11092025english.pdf",
}
SOURCE_FILES = {
    "GEN": "KA_engg_2025_GEN_R3.pdf",
    "HK": "KA_engg_2025_HK_R3.pdf",
}

RAW_REQUIRED = [
    "college_code", "college_name", "course_name_raw", "course_name",
    "domicile_pool", "category_code", "closing_rank", "year", "round",
]
OUTPUT_COLS = [
    "state", "cet_name", "stream", "year", "round",
    "college_code", "college_name", "college_type", "college_type_source",
    "course_name_raw", "course_name", "domicile_pool", "category_code",
    "closing_rank", "source_file", "source_url",
]
GRAIN = [
    "college_code", "course_name", "domicile_pool", "category_code", "year", "round",
]


def _find_one(pattern: str, *, required: bool = True) -> Path | None:
    matches = sorted(RAW.glob(pattern))
    if not matches:
        if required:
            raise SystemExit(f"No file matching {pattern!r} in {RAW}")
        return None
    if len(matches) > 1:
        raise SystemExit(f"Multiple files match {pattern!r}: {[m.name for m in matches]}")
    return matches[0]


def _college_type_map(path: Path | None) -> pd.Series:
    if path is None:
        print("No 2024 government-scope file found; college_type will be 'Unknown'.")
        return pd.Series(dtype="string")

    govt = pd.read_csv(path, dtype={"college_code": "string"})
    required = {"college_code", "college_type"}
    if not required.issubset(govt.columns):
        raise ValueError(f"{path.name} is missing columns {sorted(required - set(govt.columns))}")

    conflicts = govt.groupby("college_code")["college_type"].nunique().loc[lambda s: s > 1]
    if not conflicts.empty:
        raise ValueError(f"Conflicting college_type values for: {conflicts.index.tolist()}")

    print(f"Reading optional classification: {path.name}")
    return (
        govt[["college_code", "college_type"]]
        .dropna()
        .drop_duplicates("college_code")
        .set_index("college_code")["college_type"]
    )


def build() -> pd.DataFrame:
    cutoffs_path = _find_one(CUTOFFS_GLOB)
    govt_path = _find_one(GOVT_GLOB, required=False)

    print(f"Reading: {cutoffs_path.name}")
    df = pd.read_csv(cutoffs_path, dtype={"college_code": "string"})
    missing_cols = sorted(set(RAW_REQUIRED) - set(df.columns))
    if missing_cols:
        raise ValueError(f"Parsed cutoff CSV is missing columns: {missing_cols}")

    df["closing_rank"] = pd.to_numeric(df["closing_rank"], errors="coerce")
    df["year"] = pd.to_numeric(df["year"], errors="raise").astype("Int64")
    df["round"] = pd.to_numeric(df["round"], errors="raise").astype("Int64")
    if df["closing_rank"].isna().any():
        raise ValueError("closing_rank contains null or non-numeric values")

    college_types = _college_type_map(govt_path)
    mapped_type = df["college_code"].map(college_types)
    explicit_government_name = df["college_name"].str.contains(
        r"(?i)(?:^|\b)GOVT\.?|\bGOVERNMENT ENGINEERING COLLEGE\b",
        regex=True,
        na=False,
    )
    df["college_type"] = mapped_type
    df["college_type_source"] = "KEA 2024 government-scope file"
    inferred = mapped_type.isna() & explicit_government_name
    df.loc[inferred, "college_type"] = "Govt"
    df.loc[inferred, "college_type_source"] = "explicit KEA 2025 college name"
    unknown = df["college_type"].isna()
    df.loc[unknown, "college_type"] = "Unknown"
    df.loc[unknown, "college_type_source"] = "unclassified"
    df["state"] = "KARNATAKA"
    df["cet_name"] = "KCET"
    df["stream"] = "engineering"
    df["source_file"] = df["domicile_pool"].map(SOURCE_FILES)
    df["source_url"] = df["domicile_pool"].map(SOURCE_URLS)
    df = df[OUTPUT_COLS]

    nulls = df[OUTPUT_COLS].isna().any()
    if nulls.any():
        raise ValueError(f"Required columns contain nulls: {nulls[nulls].index.tolist()}")
    if set(df["domicile_pool"]) != {"GEN", "HK"}:
        raise ValueError(f"Unexpected domicile pools: {sorted(df['domicile_pool'].unique())}")
    if set(df["year"]) != {2025} or set(df["round"]) != {3}:
        raise ValueError("Expected only KCET 2025 Round 3")

    duplicates = df.duplicated(GRAIN, keep=False)
    if duplicates.any():
        sample = df.loc[duplicates, GRAIN + ["closing_rank"]].head(10)
        raise ValueError(f"Duplicate declared grain:\n{sample.to_string(index=False)}")

    expected = {
        "rows": 13_604,
        "colleges": 229,
        "courses": 140,
        "categories": 47,
        "gen_rows": 10_949,
        "hk_rows": 2_655,
        "e237_rows": 276,
    }
    actual = {
        "rows": len(df),
        "colleges": df["college_code"].nunique(),
        "courses": df["course_name"].nunique(),
        "categories": df["category_code"].nunique(),
        "gen_rows": int((df["domicile_pool"] == "GEN").sum()),
        "hk_rows": int((df["domicile_pool"] == "HK").sum()),
        "e237_rows": int((df["college_code"] == "E237").sum()),
    }
    if actual != expected:
        raise ValueError(f"KCET source anchors changed: expected {expected}, got {actual}")

    uvce = df[
        (df["college_code"] == "E001")
        & (df["course_name"] == "COMPUTER SCIENCE AND ENGINEERING")
        & (df["domicile_pool"] == "GEN")
        & (df["category_code"] == "GM")
    ]
    if len(uvce) != 1 or uvce.iloc[0]["closing_rank"] != 5020:
        raise ValueError("Expected UVCE E001 CSE GEN/GM closing rank 5,020")
    if set(df.loc[df["college_code"] == "E237", "domicile_pool"]) != {"GEN", "HK"}:
        raise ValueError("E237 must be correctly attributed in both PDFs")

    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing")
    args = parser.parse_args()

    df = build()
    print(
        f"\nValidated {len(df):,} rows; {df['college_code'].nunique()} colleges; "
        f"{df['course_name'].nunique()} courses; {df['category_code'].nunique()} categories"
    )
    print(df.drop_duplicates("college_code")["college_type"].value_counts().to_string())

    if args.dry_run:
        print("[dry-run] No file written.")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    output = CLEAN / "kcet_fact_cutoffs.parquet"
    df.to_parquet(output, index=False)
    print(f"Written: {output}")


if __name__ == "__main__":
    main()
