#!/usr/bin/env python3
"""
Clean JEE Mains raw Excel files into a canonical schema.

All year-specific logic lives in codemaps/mains/. To add a new year:
  1. Create codemaps/mains/yYYYY.py
  2. Register it in codemaps/mains/__init__.py

Run:
    python3 scripts/clean_jee_mains.py

Output:
    clean/jee_mains_clean.csv
    schemas/jnv_fact_jee_mains_results.yaml  (auto-generated; regenerated each run)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
JNV_DIR   = Path(__file__).resolve().parent.parent
RAW_DIR   = JNV_DIR / "raw" / "jee_mains"
CLEAN_DIR = JNV_DIR / "clean"
CLEAN_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(JNV_DIR))
from codemaps.mains import ALL_CODEMAPS
from codemaps.mains.shared import (
    CANONICAL_COLS, COLUMN_TYPES,
    normalize_gender, normalize_category,
    to_float, appeared, to_bool_qualified, safe_pct,
)

# ── Column lookup helpers ─────────────────────────────────────────────────────

def _find_col(df, *candidates):
    """Return the first matching column name (case-insensitive), or None."""
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for cand in candidates:
        match = cols_lower.get(cand.lower().strip())
        if match is not None:
            return match
    return None


def _get(df, *candidates):
    """Return the first matching column as a Series, or an all-NaN Series."""
    col = _find_col(df, *candidates)
    return df[col] if col else pd.Series([np.nan] * len(df), index=df.index)


# ── Generic year processor ────────────────────────────────────────────────────

def process_year(df, codemap):
    """
    Map raw DataFrame columns to canonical schema using the codemap.
    No year-specific logic here — everything is driven by the codemap dict.
    """
    constants = codemap.get("constants", {})
    col_map   = codemap.get("columns", {})
    out = pd.DataFrame(index=df.index)

    for col in CANONICAL_COLS:
        col_type = COLUMN_TYPES.get(col, "str")

        # 1. Constant columns — value comes from the codemap constants dict.
        if col_type == "constant" or col in constants:
            out[col] = constants.get(col)

        # 2. Category — needs both the category col and optional PWD col.
        elif col_type == "category":
            cat_raw = _get(df, *col_map.get("category", []))
            pwd_raw = _get(df, *col_map.get("_pwd_raw", []))
            out[col] = [normalize_category(c, p) for c, p in zip(cat_raw, pwd_raw)]

        # 3. Appeared — True/False based on ABS detection in the score col.
        elif col_type == "appeared":
            raw_cols = col_map.get(col, [])
            out[col] = _get(df, *raw_cols).map(appeared) if raw_cols else True

        # 4. All other mapped columns.
        elif col in col_map:
            series = _get(df, *col_map[col])
            if col_type == "float":
                out[col] = series.apply(to_float)
            elif col_type == "gender":
                out[col] = series.map(normalize_gender)
            elif col_type == "bool_qualified":
                out[col] = series.map(to_bool_qualified)
            else:
                out[col] = series

        # 5. Not in codemap — leave as NaN.
        else:
            out[col] = np.nan

    # Year-specific post-transform hook (e.g. deriving category_pwd_rank for 2025).
    post_fn = codemap.get("post_transform")
    if post_fn:
        out = post_fn(df, out)

    return out


# ── Post-processing (applied once across all years) ───────────────────────────

def post_process(df):
    # Derive category_rank from per-category rank cols where still null.
    cat_rank_map = {
        "OBC": "obc_rank", "PWD-OBC": "obc_rank",
        "SC":  "sc_rank",  "PWD-SC":  "sc_rank",
        "ST":  "st_rank",  "PWD-ST":  "st_rank",
        "Gen-EWS": "ews_rank", "PWD-EWS": "ews_rank",
    }
    mask = df["category_rank"].isna()
    if mask.any():
        def _cat_rank(row):
            col = cat_rank_map.get(str(row.get("category") or ""))
            return row[col] if col and not pd.isna(row.get(col)) else np.nan
        df.loc[mask, "category_rank"] = df[mask].apply(_cat_rank, axis=1)

    # Fill marks_12_pct and marks_10_pct where computable from obtained/total.
    for grade in ("12", "10"):
        pct = f"marks_{grade}_pct"
        obt = f"marks_{grade}_obtained"
        tot = f"marks_{grade}_total"
        missing = df[pct].isna() & df[obt].notna() & df[tot].notna()
        if missing.any():
            df.loc[missing, pct] = df.loc[missing].apply(
                lambda r: safe_pct(r[obt], r[tot]), axis=1
            )

    # Deduplicate on (test_year, application_no); prefer rows with a score.
    df = (
        df.sort_values(
            ["test_year", "application_no", "total_score"],
            ascending=[True, True, False],
            na_position="last",
        )
        .drop_duplicates(subset=["test_year", "application_no"], keep="first")
        .reset_index(drop=True)
    )
    return df


# ── File loader ───────────────────────────────────────────────────────────────

def load_file(source):
    path = RAW_DIR / source["file"]
    header = source.get("header", 0)
    fallback = source.get("header_fallback")

    print(f"  Loading {source['file']} (sheet: {source['sheet']}) ...")
    df = pd.read_excel(path, sheet_name=source["sheet"], header=header)

    # Retry with fallback header row if most columns came back Unnamed.
    if fallback is not None:
        unnamed = sum(1 for c in df.columns if "Unnamed" in str(c))
        if unnamed > len(df.columns) // 2:
            df = pd.read_excel(path, sheet_name=source["sheet"], header=fallback)

    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    frames = []

    for codemap in ALL_CODEMAPS:
        year = codemap.get("constants", {}).get("test_year", "?")
        print(f"Processing {year} ({codemap['source']['file']}) ...")
        raw_df = load_file(codemap["source"])
        frames.append(process_year(raw_df, codemap))

    print("\nConcatenating all years ...")
    combined = pd.concat(frames, ignore_index=True)

    print("Post-processing (category_rank derivation, pct fill, dedup) ...")
    combined = post_process(combined)

    # Ensure all canonical columns are present and in order.
    for col in CANONICAL_COLS:
        if col not in combined.columns:
            combined[col] = np.nan
    combined = combined[CANONICAL_COLS]

    # ── Save CSV ──────────────────────────────────────────────────────────────
    out_path = CLEAN_DIR / "jee_mains_clean.csv"
    combined.to_csv(out_path, index=False)
    print(f"\nSaved {len(combined):,} rows → {out_path}")

    print("\nRow counts by test_year:")
    print(combined.groupby("test_year").size().rename("count").to_string())

    print("\nNull rates (key columns):")
    for col in ["total_score", "all_india_rank", "student_state", "jee_mains_qualified"]:
        pct = combined[col].isna().mean() * 100
        print(f"  {col}: {pct:.1f}% null")

    print("\nCategory distribution:")
    print(combined["category"].value_counts().to_string())

    print("\nGender distribution:")
    print(combined["student_gender"].value_counts().to_string())

    # ── Save schema (YAML to schemas/) ───────────────────────────────────────
    schemas_dir = JNV_DIR / "schemas"
    schemas_dir.mkdir(exist_ok=True)
    source_files_yaml = "\n".join(
        f"  {cm['constants']['test_year']}: {cm['source']['file']}"
        for cm in ALL_CODEMAPS
    )
    columns_yaml = "\n".join(
        f"  - name: {col}\n    type: {COLUMN_TYPES.get(col, 'str')}"
        for col in CANONICAL_COLS
    )
    yaml_text = (
        "# Auto-generated by clean_jee_mains.py — do not edit by hand.\n\n"
        "description: JEE Mains results for JNV students — scores, ranks, board marks,"
        " and qualification flags across 2021–2026.\n"
        "grain: (test_year, application_no)\n"
        f"source_files:\n{source_files_yaml}\n\n"
        f"columns:\n{columns_yaml}\n"
    )
    schema_path = schemas_dir / "jnv_fact_jee_mains_results.yaml"
    schema_path.write_text(yaml_text)
    print(f"Schema saved → {schema_path}")


if __name__ == "__main__":
    main()
