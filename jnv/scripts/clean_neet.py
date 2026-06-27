#!/usr/bin/env python3
"""
Clean NEET raw Excel files into a single canonical table.

Processing is codemap-driven (codemaps/neet/).  The engine contains no
year-specific logic — all year knowledge lives in the codemap files.

Run:
    python3 scripts/clean_neet.py

Output:
    clean/neet_clean.csv
    schemas/jnv_fact_neet_results.yaml  (auto-generated; regenerated each run)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
JNV_DIR   = Path(__file__).resolve().parent.parent
RAW_NEET  = JNV_DIR / "raw" / "neet"
CLEAN_DIR = JNV_DIR / "clean"
CLEAN_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(JNV_DIR))
from codemaps.neet import ALL_NEET_CODEMAPS
from codemaps.neet.shared import (
    CANONICAL_COLS, COLUMN_TYPES,
    normalize_gender, normalize_category,
    to_float, to_int, appeared, to_boolean, safe_pct, apply_dtypes,
)

# ── BigQuery cutoff fetch ─────────────────────────────────────────────────────

def fetch_neet_cutoffs():
    """
    Fetch NEET qualifying cutoffs from dim_nta_cutoffs.
    Returns dict[(test_year_str, category)] -> min_value, or None on failure.
    Cutoff values are raw marks (not percentile).
    """
    try:
        from google.cloud import bigquery
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sources import BQ_PROJECT, BQ_LOCATION
        client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
        query = """
            SELECT CAST(test_year AS STRING) AS test_year, category, min_value
            FROM `avantifellows.production_dbt_final.dim_nta_cutoffs`
            WHERE test_name = 'NEET'
              AND academic_level = 'NEET Qual.'
        """
        return {(row.test_year, row.category): row.min_value
                for row in client.query(query).result()}
    except Exception as exc:
        print(f"  Warning: could not fetch NEET cutoffs from BigQuery ({exc}).\n"
              "  neet_qualified_calculated will be null.")
        return None


# ── Column lookup helpers ─────────────────────────────────────────────────────

def _find_col(df, *candidates):
    # Guard against non-string column names (e.g. integer "400" in NEET 2022)
    cols_lower = {str(c).lower().strip(): c for c in df.columns}
    for cand in candidates:
        match = cols_lower.get(cand.lower().strip())
        if match is not None:
            return match
    return None


def _get(df, *candidates):
    col = _find_col(df, *candidates)
    return df[col] if col else pd.Series([np.nan] * len(df), index=df.index)


# ── Year processor ────────────────────────────────────────────────────────────

def process_neet_year(df, codemap):
    constants = codemap.get("constants", {})
    col_map   = codemap.get("columns", {})
    out = pd.DataFrame(index=df.index)

    for col in CANONICAL_COLS:
        col_type = COLUMN_TYPES.get(col, "str")

        if col_type == "constant" or col in constants:
            out[col] = constants.get(col)
        elif col_type == "category":
            cat_raw = _get(df, *col_map.get("category", []))
            pwd_raw = _get(df, *col_map.get("_pwd_raw", []))
            out[col] = [normalize_category(c, p) for c, p in zip(cat_raw, pwd_raw)]
        elif col_type == "appeared":
            raw_cols = col_map.get(col, [])
            if raw_cols:
                out[col] = _get(df, *raw_cols).map(appeared)
            else:
                out[col] = True  # default: all rows are appeared candidates
        elif col in col_map:
            series = _get(df, *col_map[col])
            if col_type == "float":
                out[col] = series.apply(to_float)
            elif col_type == "int":
                out[col] = pd.array(series.apply(to_int), dtype="Int64")
            elif col_type == "gender":
                out[col] = series.map(normalize_gender)
            elif col_type == "boolean":
                out[col] = series.map(to_boolean)
            else:
                out[col] = series
        else:
            out[col] = np.nan

    post_fn = codemap.get("post_transform")
    if post_fn:
        out = post_fn(df, out)

    return out


# ── Post-processing ───────────────────────────────────────────────────────────

def _qualify_neet_calculated(row, cutoffs):
    """True/False vs NEET qualifying cutoff; None if score or cutoff unavailable."""
    year  = str(row.get("test_year") or "")
    cat   = str(row.get("category") or "")
    score = row.get("neet_total_score")
    if pd.isna(score) or not year or not cat:
        return None
    cutoff = cutoffs.get((year, cat)) or cutoffs.get((str(int(year) - 1), cat))
    if cutoff is None:
        return None
    return bool(float(score) >= float(cutoff))


def post_process(df, cutoffs=None):
    # ── Board mark pct derivation ─────────────────────────────────────────────
    for grade in ("12", "10"):
        pct = f"marks_{grade}_pct"
        obt = f"marks_{grade}_obtained"
        tot = f"marks_{grade}_total"
        missing = df[pct].isna() & df[obt].notna() & df[tot].notna()
        if missing.any():
            df.loc[missing, pct] = df.loc[missing].apply(
                lambda r: safe_pct(r[obt], r[tot]), axis=1
            )

    # ── Dedup on (test_year, application_no); prefer rows with a score ────────
    df = (
        df.sort_values(
            ["test_year", "application_no", "neet_total_score"],
            ascending=[True, True, False],
            na_position="last",
        )
        .drop_duplicates(subset=["test_year", "application_no"], keep="first")
        .reset_index(drop=True)
    )

    # ── NEET qualification columns ────────────────────────────────────────────
    # neet_qualified_from_data: already populated where the file carries a flag (2022).
    # neet_qualified_calculated: derived from cutoffs fetched from dim_nta_cutoffs.
    # neet_qualified: from_data takes precedence; falls back to calculated.
    if cutoffs is not None:
        df["neet_qualified_calculated"] = df.apply(
            lambda r: _qualify_neet_calculated(r, cutoffs), axis=1
        )
    else:
        df["neet_qualified_calculated"] = None

    df["neet_qualified"] = df["neet_qualified_from_data"].combine_first(
        df["neet_qualified_calculated"]
    )

    return df


# ── File loader ───────────────────────────────────────────────────────────────

def load_file(raw_dir, source):
    path     = raw_dir / source["file"]
    header   = source.get("header", 0)
    fallback = source.get("header_fallback")

    print(f"  Loading {source['file']} (sheet: {source['sheet']}) ...")
    df = pd.read_excel(path, sheet_name=source["sheet"], header=header)

    if fallback is not None:
        unnamed = sum(1 for c in df.columns if "Unnamed" in str(c))
        if unnamed > len(df.columns) // 2:
            df = pd.read_excel(path, sheet_name=source["sheet"], header=fallback)

    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    frames = []
    for codemap in ALL_NEET_CODEMAPS:
        year = codemap.get("constants", {}).get("test_year", "?")
        print(f"Processing NEET {year} ({codemap['source']['file']}) ...")
        raw_df = load_file(RAW_NEET, codemap["source"])
        frames.append(process_neet_year(raw_df, codemap))

    print("\nConcatenating years ...")
    combined = pd.concat(frames, ignore_index=True)

    # Normalize application_no to string
    combined["application_no"] = combined["application_no"].apply(
        lambda v: str(int(float(v))) if pd.notna(v) and str(v).strip() not in ("", "nan") else None
    )

    print("Fetching NEET qualifying cutoffs from BigQuery ...")
    cutoffs = fetch_neet_cutoffs()

    print("Post-processing ...")
    combined = post_process(combined, cutoffs)

    # Ensure canonical column order
    for col in CANONICAL_COLS:
        if col not in combined.columns:
            combined[col] = np.nan
    combined = combined[CANONICAL_COLS]

    # Apply correct pandas dtypes (float, Int64, boolean, str) before saving
    combined = apply_dtypes(combined)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    out_path = CLEAN_DIR / "neet_clean.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nSaved {len(combined):,} rows → {out_path}")

    print("\nRow counts by test_year:")
    print(combined.groupby("test_year").size().rename("count").to_string())

    print("\nNull rates (key columns):")
    for col in [
        "neet_total_score", "neet_all_india_rank",
        "neet_qualified_from_data", "neet_qualified_calculated", "neet_qualified",
    ]:
        pct = combined[col].isna().mean() * 100
        print(f"  {col}: {pct:.1f}% null")

    print("\nCategory distribution:")
    print(combined["category"].value_counts().to_string())

    print("\nGender distribution:")
    print(combined["student_gender"].value_counts().to_string())

    # ── Save schema ───────────────────────────────────────────────────────────
    schemas_dir = JNV_DIR / "schemas"
    schemas_dir.mkdir(exist_ok=True)
    source_files_yaml = "\n".join(
        f"  {cm['constants']['test_year']}: {cm['source']['file']}"
        for cm in ALL_NEET_CODEMAPS
    )
    columns_yaml = "\n".join(
        f"  - name: {col}\n    type: {COLUMN_TYPES.get(col, 'str')}"
        for col in CANONICAL_COLS
    )
    yaml_text = (
        "# Auto-generated by clean_neet.py — do not edit by hand.\n\n"
        "description: NEET results for JNV students —"
        " scores, ranks, and qualification flags across 2021–2025.\n"
        "grain: (test_year, application_no)\n"
        f"source_files:\n{source_files_yaml}\n\n"
        f"columns:\n{columns_yaml}\n"
    )
    schema_path = schemas_dir / "jnv_fact_neet_results.yaml"
    schema_path.write_text(yaml_text)
    print(f"Schema saved → {schema_path}")


if __name__ == "__main__":
    main()
