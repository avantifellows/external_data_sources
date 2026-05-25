#!/usr/bin/env python3
"""
Clean JEE Mains + JEE Advanced raw Excel files into a single canonical table.

Mains processing is codemap-driven (codemaps/mains/).
Advanced processing uses a separate codemap family (codemaps/advanced/) and
is left-joined onto mains rows by (test_year, application_no).

Run:
    python3 scripts/clean_jee.py

Output:
    clean/jee_clean.csv
    schemas/jnv_fact_jee_results.yaml  (auto-generated; regenerated each run)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
JNV_DIR      = Path(__file__).resolve().parent.parent
RAW_MAINS    = JNV_DIR / "raw" / "jee_mains"
RAW_ADV      = JNV_DIR / "raw" / "jee_advanced"
CLEAN_DIR    = JNV_DIR / "clean"
CLEAN_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(JNV_DIR))
from codemaps.mains import ALL_CODEMAPS
from codemaps.mains.shared import (
    CANONICAL_COLS, COLUMN_TYPES, MAINS_RANK_SOURCE_COLS,
    normalize_gender, normalize_category,
    to_float, to_int, appeared, to_boolean, safe_pct, apply_dtypes,
)
from codemaps.advanced import ALL_ADV_CODEMAPS
from codemaps.advanced.shared import (
    ADV_CANONICAL_COLS, ADV_COLUMN_TYPES, ADV_RANK_SOURCE_COLS, to_adv_rank,
)

# ── BigQuery cutoff fetch ─────────────────────────────────────────────────────

def fetch_m2b_cutoffs():
    """
    Fetch JEE Mains M2b qualification cutoffs from dim_nta_cutoffs.
    Returns dict[(test_year_str, category)] -> min_value, or None on failure.
    """
    try:
        from google.cloud import bigquery
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from sources import BQ_PROJECT, BQ_LOCATION
        client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
        query = """
            SELECT CAST(test_year AS STRING) AS test_year, category, min_value
            FROM `avantifellows.production_dbt_final.dim_nta_cutoffs`
            WHERE test_name = 'JEE Mains'
              AND stream = 'engineering'
              AND academic_level = 'M2b'
        """
        return {(row.test_year, row.category): row.min_value
                for row in client.query(query).result()}
    except Exception as exc:
        print(f"  Warning: could not fetch M2b cutoffs from BigQuery ({exc}).\n"
              "  jee_mains_qualified_calculated will be null.")
        return None


# ── Column lookup helpers ─────────────────────────────────────────────────────

def _find_col(df, *candidates):
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        match = cols_lower.get(cand.lower().strip())
        if match is not None:
            return match
    return None


def _get(df, *candidates):
    col = _find_col(df, *candidates)
    return df[col] if col else pd.Series([np.nan] * len(df), index=df.index)


# ── Mains year processor ──────────────────────────────────────────────────────

def process_mains_year(df, codemap):
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
            out[col] = _get(df, *raw_cols).map(appeared) if raw_cols else True
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

    # Also process intermediate rank source columns (needed for category_rank derivation)
    for col, col_type in MAINS_RANK_SOURCE_COLS.items():
        raw_cols = col_map.get(col, [])
        series = _get(df, *raw_cols) if raw_cols else pd.Series([pd.NA] * len(df), index=df.index)
        out[col] = pd.array(series.apply(to_int), dtype="Int64")

    post_fn = codemap.get("post_transform")
    if post_fn:
        out = post_fn(df, out)

    return out


# ── Advanced year processor ───────────────────────────────────────────────────

def process_adv_year(df, codemap):
    """
    Map raw advanced DataFrame to ADV_CANONICAL_COLS.
    All rank columns use to_adv_rank (handles zero_is_null for 2025).
    """
    constants    = codemap.get("constants", {})
    col_map      = codemap.get("columns", {})
    zero_is_null = codemap.get("zero_is_null", False)
    out = pd.DataFrame(index=df.index)

    for col in ADV_CANONICAL_COLS:
        col_type = ADV_COLUMN_TYPES.get(col, "float")

        if col_type == "constant" or col in constants:
            out[col] = constants.get(col)
        elif col in col_map:
            series = _get(df, *col_map[col])
            if col_type == "int":
                parsed = series.apply(lambda v: to_adv_rank(v, zero_is_null))
                out[col] = pd.array(parsed.apply(lambda v: pd.NA if pd.isna(v) else int(v)), dtype="Int64")
            else:
                out[col] = series
        else:
            out[col] = np.nan

    # Also process intermediate rank source columns (for category_rank derivation post-merge)
    for col, col_type in ADV_RANK_SOURCE_COLS.items():
        raw_cols = col_map.get(col, [])
        series = _get(df, *raw_cols) if raw_cols else pd.Series([pd.NA] * len(df), index=df.index)
        out[col] = pd.array(series.apply(lambda v: to_adv_rank(v, zero_is_null)), dtype="Int64")

    post_fn = codemap.get("post_transform")
    if post_fn:
        out = post_fn(df, out)

    # Normalize application_no to string (drop trailing .0 from float reads)
    out["application_no"] = out["application_no"].apply(
        lambda v: str(int(float(v))) if pd.notna(v) else None
    )
    return out


# ── Post-processing ───────────────────────────────────────────────────────────

def _qualify_mains_calculated(row, cutoffs):
    """True/False vs M2b cutoff; None if score or cutoff unavailable."""
    year  = str(row.get("test_year") or "")
    cat   = str(row.get("category") or "")
    score = row.get("mains_total_score")
    if pd.isna(score) or not year or not cat:
        return None
    cutoff = cutoffs.get((year, cat)) or cutoffs.get((str(int(year) - 1), cat))
    if cutoff is None:
        return None
    return bool(float(score) >= float(cutoff))


def _derive_adv_category_rank(row, per_cat_col, general_col, cat_map):
    """Pick the right per-category rank column based on mains category."""
    cat = str(row.get("category") or "")
    col = cat_map.get(cat, general_col)
    val = row.get(col)
    return val if pd.notna(val) else np.nan


def post_process(df, cutoffs=None):
    # ── mains_category_rank derivation ───────────────────────────────────────
    cat_rank_map = {
        "OBC": "mains_obc_rank", "PWD-OBC": "mains_obc_rank",
        "SC":  "mains_sc_rank",  "PWD-SC":  "mains_sc_rank",
        "ST":  "mains_st_rank",  "PWD-ST":  "mains_st_rank",
        "Gen-EWS": "mains_ews_rank", "PWD-EWS": "mains_ews_rank",
    }
    mask = df["mains_category_rank"].isna()
    if mask.any():
        def _cat_rank(row):
            col = cat_rank_map.get(str(row.get("category") or ""))
            return row[col] if col and not pd.isna(row.get(col)) else np.nan
        df.loc[mask, "mains_category_rank"] = df[mask].apply(_cat_rank, axis=1)

    # ── board mark pct derivation ─────────────────────────────────────────────
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
            ["test_year", "application_no", "mains_total_score"],
            ascending=[True, True, False],
            na_position="last",
        )
        .drop_duplicates(subset=["test_year", "application_no"], keep="first")
        .reset_index(drop=True)
    )

    # ── JEE Mains qualification columns ──────────────────────────────────────
    df["jee_mains_qualified_from_data"] = df["jee_mains_qualified"]
    if cutoffs is not None:
        df["jee_mains_qualified_calculated"] = df.apply(
            lambda r: _qualify_mains_calculated(r, cutoffs), axis=1
        )
    else:
        df["jee_mains_qualified_calculated"] = None
    df["jee_mains_qualified"] = df["jee_mains_qualified_from_data"].combine_first(
        df["jee_mains_qualified_calculated"]
    )

    # ── Advanced category rank derivation ─────────────────────────────────────
    adv_cat_rank_map = {
        "OBC": "adv_obc_rank",     "PWD-OBC": "adv_obc_rank",
        "SC":  "adv_sc_rank",      "PWD-SC":  "adv_sc_rank",
        "ST":  "adv_st_rank",      "PWD-ST":  "adv_st_rank",
        "Gen-EWS": "adv_ews_rank", "PWD-EWS": "adv_ews_rank",
        "Gen": "adv_all_india_rank",
    }
    adv_pwd_rank_map = {
        "PWD-Gen": "adv_all_india_pwd_rank",
        "PWD-OBC": "adv_obc_pwd_rank",
        "PWD-SC":  "adv_sc_pwd_rank",
        "PWD-ST":  "adv_st_pwd_rank",
        "PWD-EWS": "adv_ews_pwd_rank",
    }
    adv_prep_rank_map = {
        "SC":      "adv_prep_sc_rank",
        "ST":      "adv_prep_st_rank",
        "PWD-SC":  "adv_prep_sc_pwd_rank",
        "PWD-ST":  "adv_prep_st_pwd_rank",
        "PWD-OBC": "adv_prep_obc_pwd_rank",
        "PWD-EWS": "adv_prep_ews_pwd_rank",
        "PWD-Gen": "adv_prep_crl_pwd_rank",
    }

    def _pick(row, rank_map, fallback=None):
        cat = str(row.get("category") or "")
        col = rank_map.get(cat, fallback)
        if col is None:
            return np.nan
        val = row.get(col)
        return val if pd.notna(val) else np.nan

    adv_cat_missing = df["adv_category_rank"].isna()
    if adv_cat_missing.any():
        df.loc[adv_cat_missing, "adv_category_rank"] = df[adv_cat_missing].apply(
            lambda r: _pick(r, adv_cat_rank_map), axis=1
        )

    adv_pwd_missing = df["adv_category_pwd_rank"].isna()
    if adv_pwd_missing.any():
        df.loc[adv_pwd_missing, "adv_category_pwd_rank"] = df[adv_pwd_missing].apply(
            lambda r: _pick(r, adv_pwd_rank_map), axis=1
        )

    # adv_prep_category_rank: fill from prep per-category columns where still null
    adv_prep_missing = df["adv_prep_category_rank"].isna()
    if adv_prep_missing.any():
        df.loc[adv_prep_missing, "adv_prep_category_rank"] = df[adv_prep_missing].apply(
            lambda r: _pick(r, adv_prep_rank_map), axis=1
        )

    # ── JEE Advanced qualification columns ───────────────────────────────────
    # adv_appeared marks students found in the advanced Excel (set True by codemap).
    # Priority: rank-derived (adv_appeared=True) > mains-file flag (2025 fallback).
    adv_in_file = df.get("adv_appeared", pd.Series(False, index=df.index)).fillna(False)

    # from_data: True if CRL rank present for students in adv file; else mains fallback
    adv_qual_from_rank = df["adv_all_india_rank"].notna()
    if "jee_advanced_qualified_from_data" not in df.columns:
        df["jee_advanced_qualified_from_data"] = None
    df["jee_advanced_qualified_from_data"] = np.where(
        adv_in_file,
        adv_qual_from_rank,
        df["jee_advanced_qualified_from_data"],
    )

    # jee_advanced_qualified_calculated: null — JEE Advanced scores not available
    # in these Excel files (rank lists only); cannot replicate the ETL's per-subject
    # cutoff check.
    df["jee_advanced_qualified_calculated"] = None

    df["jee_advanced_qualified"] = df["jee_advanced_qualified_from_data"].combine_first(
        df["jee_advanced_qualified_calculated"]
    )

    # ── Prep course qualification columns ─────────────────────────────────────
    any_prep = (
        df[["adv_prep_sc_rank", "adv_prep_st_rank",
            "adv_prep_sc_pwd_rank", "adv_prep_st_pwd_rank",
            "adv_prep_obc_pwd_rank", "adv_prep_ews_pwd_rank",
            "adv_prep_crl_pwd_rank"]]
        .notna().any(axis=1)
    )
    if "jee_prep_qualified_from_data" not in df.columns:
        df["jee_prep_qualified_from_data"] = None
    df["jee_prep_qualified_from_data"] = np.where(
        adv_in_file,
        any_prep,
        df["jee_prep_qualified_from_data"],
    )
    df["jee_prep_qualified_calculated"] = None
    df["jee_prep_qualified"] = df["jee_prep_qualified_from_data"].combine_first(
        df["jee_prep_qualified_calculated"]
    )

    # Drop intermediate rank source columns — used for derivation above, not in final output
    df = df.drop(columns=["adv_appeared"], errors="ignore")
    df = df.drop(columns=list(MAINS_RANK_SOURCE_COLS) + list(ADV_RANK_SOURCE_COLS), errors="ignore")

    return df


# ── File loader ───────────────────────────────────────────────────────────────

def load_file(raw_dir, source):
    path   = raw_dir / source["file"]
    header = source.get("header", 0)
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
    # ── Process mains ─────────────────────────────────────────────────────────
    mains_frames = []
    for codemap in ALL_CODEMAPS:
        year = codemap.get("constants", {}).get("test_year", "?")
        print(f"Processing mains {year} ({codemap['source']['file']}) ...")
        raw_df = load_file(RAW_MAINS, codemap["source"])
        mains_frames.append(process_mains_year(raw_df, codemap))

    print("\nConcatenating mains years ...")
    mains = pd.concat(mains_frames, ignore_index=True)

    # ── Process advanced ──────────────────────────────────────────────────────
    adv_frames = []
    for codemap in ALL_ADV_CODEMAPS:
        year = codemap.get("constants", {}).get("test_year", "?")
        print(f"Processing advanced {year} ({codemap['source']['file']}) ...")
        raw_df = load_file(RAW_ADV, codemap["source"])
        adv_frames.append(process_adv_year(raw_df, codemap))

    print("\nConcatenating advanced years ...")
    adv = pd.concat(adv_frames, ignore_index=True)

    # ── Merge advanced onto mains ─────────────────────────────────────────────
    # Normalize mains application_no to the same string format
    mains["application_no"] = mains["application_no"].apply(
        lambda v: str(int(float(v))) if pd.notna(v) and str(v).strip() not in ("", "nan") else None
    )

    # Drop the all-NaN adv_* placeholder columns the engine created from CANONICAL_COLS.
    # The actual values come from the advanced dataframe via the merge below.
    adv_placeholders = [c for c in mains.columns if c.startswith("adv_")]
    mains = mains.drop(columns=adv_placeholders)

    print("\nMerging advanced data onto mains ...")
    combined = mains.merge(
        adv,
        on=["test_year", "application_no"],
        how="left",
    )

    # Ensure all canonical columns exist (some adv_* derived cols aren't in ADV_CANONICAL_COLS)
    for col in CANONICAL_COLS:
        if col not in combined.columns:
            combined[col] = np.nan

    # ── Fetch cutoffs and post-process ────────────────────────────────────────
    print("Fetching M2b qualification cutoffs from BigQuery ...")
    cutoffs = fetch_m2b_cutoffs()

    print("Post-processing ...")
    combined = post_process(combined, cutoffs)

    # Ensure all canonical columns are present and in correct order
    for col in CANONICAL_COLS:
        if col not in combined.columns:
            combined[col] = np.nan
    combined = combined[CANONICAL_COLS]

    # Apply correct pandas dtypes (float, Int64, boolean, str) before saving
    combined = apply_dtypes(combined)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    out_path = CLEAN_DIR / "jee_clean.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nSaved {len(combined):,} rows → {out_path}")

    print("\nRow counts by test_year:")
    print(combined.groupby("test_year").size().rename("count").to_string())

    print("\nNull rates (key columns):")
    for col in [
        "mains_total_score", "mains_all_india_rank",
        "jee_mains_qualified_from_data", "jee_mains_qualified_calculated", "jee_mains_qualified",
        "adv_all_india_rank",
        "jee_advanced_qualified_from_data", "jee_advanced_qualified",
        "jee_prep_qualified_from_data", "jee_prep_qualified",
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
        for cm in ALL_CODEMAPS
    )
    adv_source_files_yaml = "\n".join(
        f"  {cm['constants']['test_year']}: {cm['source']['file']}"
        for cm in ALL_ADV_CODEMAPS
    )
    columns_yaml = "\n".join(
        f"  - name: {col}\n    type: {COLUMN_TYPES.get(col, 'str')}"
        for col in CANONICAL_COLS
    )
    yaml_text = (
        "# Auto-generated by clean_jee.py — do not edit by hand.\n\n"
        "description: Combined JEE Mains + Advanced results for JNV students —"
        " scores, ranks, and qualification flags across 2021–2026.\n"
        "grain: (test_year, application_no)\n"
        f"mains_source_files:\n{source_files_yaml}\n\n"
        f"advanced_source_files:\n{adv_source_files_yaml}\n\n"
        f"columns:\n{columns_yaml}\n"
    )
    schema_path = schemas_dir / "jnv_fact_jee_results.yaml"
    schema_path.write_text(yaml_text)
    print(f"Schema saved → {schema_path}")


if __name__ == "__main__":
    main()
