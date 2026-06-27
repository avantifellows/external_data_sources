#!/usr/bin/env python3
"""
Transform NVS NCST Excel files into a single clean CSV.

Reads:
    raw/NCST 2026.xlsx  (sheet: NCST Data)

Writes:
    clean/ncst_clean.csv

Transformations applied (driven by codemaps/ncst/):
  - Column rename to canonical schema (86 columns)
  - Gender normalised → Male / Female
  - Category normalised → Gen / Gen-EWS / OBC / SC / ST
  - Stream normalised → Engineering / Medical
  - Coaching preferences normalised →
        Dakshana Foundation / Ex-Navodaya Foundation / Avanti Foundation
  - physically_disabled / is_father_late / is_mother_alive / willing_for_coaching
    / is_bpl / has_ration_card coerced to bool
  - is_father_late inverted from "Is Father alive(Yes/No)"
  - DOB and exam_date converted to YYYY-MM-DD strings
  - Normalized scores pre-computed in source Excel; pipeline reads them directly

Contact columns (mobile, email) and parent names are excluded.

Usage:
    python3 scripts/clean_ncst.py
"""

import sys
from pathlib import Path

import pandas as pd

NVS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(NVS_DIR))
sys.path.insert(0, str(NVS_DIR.parent))

from codemaps.ncst import ALL_NCST_CODEMAPS
from codemaps.ncst.shared import (
    CANONICAL_COLS,
    normalize_bool,
    normalize_category,
    normalize_coaching,
    normalize_gender,
    normalize_stream,
)
from scripts.sources import NCST_CLEAN, RAW_NCST_FILES


def _match_column(raw_cols_lower: dict[str, str], candidates: list[str]) -> str | None:
    """Return the first raw column name that matches any candidate (case-insensitive)."""
    for cand in candidates:
        if cand.lower() in raw_cols_lower:
            return raw_cols_lower[cand.lower()]
    return None


def _process_codemap(codemap: dict) -> pd.DataFrame:
    source   = codemap["source"]
    raw_file = NVS_DIR / "raw" / source["file"]

    if not raw_file.exists():
        print(f"  WARNING: {raw_file} not found — skipping.")
        return pd.DataFrame(columns=CANONICAL_COLS)

    year = codemap["constants"]["test_year"]
    print(f"  Reading NCST {year}: {source['file']!r} sheet {source['sheet']!r} ...")

    df_raw = pd.read_excel(
        raw_file,
        sheet_name=source["sheet"],
        header=source.get("header", 0),
        dtype=str,
    )

    n = len(df_raw)
    out = pd.DataFrame({col: [None] * n for col in CANONICAL_COLS})

    # Set constants
    for k, v in codemap.get("constants", {}).items():
        out[k] = v

    # Map columns (case-insensitive, first candidate found wins)
    raw_cols_lower = {str(c).strip().lower(): c for c in df_raw.columns}
    for canonical, candidates in codemap.get("columns", {}).items():
        matched = _match_column(raw_cols_lower, candidates)
        if matched:
            out[canonical] = df_raw[matched].values

    # Post-transform (DOB coercion, date formatting, stream-based score, etc.)
    if "post_transform" in codemap:
        out = codemap["post_transform"](df_raw, out)

    # Apply normalisations
    out["student_gender"]        = out["student_gender"].apply(normalize_gender)
    out["category"]              = out["category"].apply(normalize_category)
    out["stream"]                = out["stream"].apply(normalize_stream)
    out["physically_disabled"]   = out["physically_disabled"].apply(normalize_bool)
    out["is_father_late"]        = out["is_father_late"].apply(normalize_bool)
    out["is_mother_alive"]       = out["is_mother_alive"].apply(normalize_bool)
    out["willing_for_coaching"]  = out["willing_for_coaching"].apply(normalize_bool)
    out["is_bpl"]                = out["is_bpl"].apply(normalize_bool)
    out["has_ration_card"]       = out["has_ration_card"].apply(normalize_bool)
    out["coaching_preference_1"] = out["coaching_preference_1"].apply(normalize_coaching)
    out["coaching_preference_2"] = out["coaching_preference_2"].apply(normalize_coaching)
    out["coaching_preference_3"] = out["coaching_preference_3"].apply(normalize_coaching)

    # Drop rows where roll_no is missing
    before = len(out)
    out = out[out["roll_no"].notna() & (out["roll_no"] != "None")]
    dropped = before - len(out)
    if dropped:
        print(f"    Dropped {dropped:,} rows with null roll_no")

    print(f"    {len(out):,} rows × {len(out.columns)} columns")
    return out


def main() -> None:
    frames = []
    for codemap in ALL_NCST_CODEMAPS:
        df = _process_codemap(codemap)
        if not df.empty:
            frames.append(df)

    if not frames:
        print("ERROR: no data produced — check that raw files exist under raw/")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    print(f"\nTotal: {len(combined):,} rows across {combined['test_year'].nunique()} years")

    out_path = NCST_CLEAN.local_path
    out_path.parent.mkdir(exist_ok=True)
    combined.to_csv(out_path, index=False)
    print(f"Written to {out_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
