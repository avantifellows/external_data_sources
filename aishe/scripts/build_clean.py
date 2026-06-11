"""
Build clean parquet files from the raw AISHE HE Directory Excel exports.

Reads each Excel file from aishe/raw/, skips the title/date header rows,
normalises column names to canonical snake_case, strips whitespace,
classifies each institution into one or more types, and writes a clean
parquet to aishe/clean/.

The clean parquets are the inputs to upload_to_gcs.py and load_bq.py.
Raw Excel files are gitignored — they must be downloaded manually from
https://dashboard.aishe.gov.in/hedirectory/#/hedirectory and placed in
aishe/raw/ before running this script.

Institution-type classification
--------------------------------
Each row gets an `institution_types` column: a comma-separated list of
matched types from the controlled vocabulary below, or NULL if no keyword
matches. Matching runs against the institution name (lowercased) using:
  1. Exact substring match for multi-word keywords (e.g. "hotel management")
  2. Fuzzy token match (rapidfuzz ratio >= 95%) for single-word keywords —
     handles spelling variants like "ayurved/ayurveda", regional
     transliterations, etc.

Controlled vocabulary (17 types):
  Engineering, Medical, Architecture, Law, Arts/Commerce/Science, Teaching,
  Journalism, Hotel Management, Pharmacy, Nursing, Agriculture, Ayurveda,
  Paramedical, Veterinary, Research, Design, Polytechnic

Requires: pandas, openpyxl, pyarrow, rapidfuzz

Usage:
  python3 scripts/build_clean.py                              # all five tables
  python3 scripts/build_clean.py --table aishe_fact_colleges  # one only
  python3 scripts/build_clean.py --dry-run                    # print stats, no write
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
from rapidfuzz import fuzz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, TABLE_BY_NAME, TABLES, Table


# ─── Institution-type keyword map ────────────────────────────────────────────
# Each entry: (institution_type_label, [keywords])
#
# Keywords are matched against the lowercased institution name.
# Multi-word keywords → exact substring match.
# Single-word keywords → fuzzy token match at >= FUZZY_THRESHOLD.
#
# ALL matching types are collected (multi-label output).
#
# Ordering note: Polytechnic is checked before Engineering so that a pure
# polytechnic/ITI name doesn't also get tagged Engineering.

FUZZY_THRESHOLD = 95  # rapidfuzz ratio score 0–100; 95 ≈ 1–2 char edit distance

TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Polytechnic", [
        # English
        "polytechnic", "iti", "industrial training", "vocational",
        "diploma engineering", "diploma technology",
        "technical institute", "technical school",
        # Hindi / Sanskrit
        "takniki sansthan",            # technical institute
        "vyavsayik",                   # vocational
        "audyogik",                    # industrial
        "prashikshan",                 # training (ITI context)
    ]),
    ("Engineering", [
        # English — degree-level programmes only
        "engineering", "technology",
        "electronics", "electrical", "mechanical",
        "civil engineering", "computer science", "information technology",
        # Hindi / Sanskrit
        "abhiyantriki",                # engineering
        "praudyogiki",                 # technology
        "tantra",                      # technology/system (e.g. "tantra vidyalaya")
    ]),
    ("Medical", [
        # English
        "medical", "medicine", "hospital", "surgery", "clinical",
        "mbbs", "healthcare", "health sciences",
        # Hindi / Sanskrit
        "chikitsa",                    # medicine/treatment
        "swasthya",                    # health
    ]),
    ("Architecture", [
        "architecture", "architectural", "planning",
        "vastu",                       # Sanskrit: architecture/built environment
    ]),
    ("Law", [
        "law", "legal", "juridical", "llb", "llm",
        "vidhi",                       # Hindi: law
        "nyaya",                       # Sanskrit: justice/law
    ]),
    ("Arts/Commerce/Science", [
        "arts", "commerce", "science", "humanities", "liberal arts",
        "social science", "economics", "statistics", "mathematics",
        "mahavidyalaya",               # Hindi: general college (arts/commerce/science)
        "vidyapith",                   # Sanskrit: seat of learning (general)
        "degree college",
    ]),
    ("Teaching", [
        "education", "teacher", "teaching", "b.ed", "bed",
        "d.ed", "ded", "d.el.ed", "deled", "pedagogy",
        "shiksha",                     # Hindi: education
        "adhyapak",                    # Hindi: teacher/instructor
        "shikshak",                    # Hindi: teacher
    ]),
    ("Journalism", [
        "journalism", "mass communication", "media studies",
        "communication studies", "broadcasting",
        "patrakarita",                 # Hindi: journalism
    ]),
    ("Hotel Management", [
        "hotel management", "hospitality management",
        "hotel and catering", "catering technology",
        "hotel administration", "culinary", "tourism management",
    ]),
    ("Pharmacy", [
        "pharmacy", "pharmaceutical", "pharmacology",
        "d.pharm", "b.pharm", "m.pharm",
        "pharmac",                     # catches "pharma", "pharmacist" etc.
    ]),
    ("Nursing", [
        "nursing", "gnm", "b.sc nursing", "midwifery",
        "prasuti",                     # Hindi: obstetrics — common in nursing names
        "stree rog",                   # Hindi: gynaecology (co-occurs in nursing colleges)
    ]),
    ("Agriculture", [
        "agriculture", "agricultural", "agronomy", "horticulture",
        "fishery", "fisheries", "forestry",
        "krishi",                      # Hindi: agriculture/farming
        "udyan",                       # Hindi: horticulture/garden
        "vanijya",                     # Hindi: commerce — but often "krishi vanijya" context
    ]),
    ("Ayurveda", [
        "ayurveda", "ayurved", "ayurvedic",
        "homeopathy", "homoeopathy", "unani", "siddha",
        "naturopathy", "yoga", "panchakarma",
        "vaidya",                      # Sanskrit: Ayurvedic practitioner
    ]),
    ("Paramedical", [
        "paramedical", "physiotherapy", "occupational therapy",
        "radiology", "medical laboratory", "optometry", "audiology",
        "speech therapy", "rehabilitation sciences",
    ]),
    ("Veterinary", [
        "veterinary", "animal husbandry", "animal science",
        "pashu",                       # Hindi: animal
        "pashuchikitsa",               # Hindi: veterinary medicine
    ]),
    ("Research", [
        "research", "institute of advanced", "advanced studies",
        "shodh",                       # Hindi: research/investigation
        "anusandhan",                  # Hindi/Sanskrit: research
    ]),
    ("Design", [
        "design", "fine arts", "applied arts", "visual arts",
        "fashion", "textile", "craft",
        "kala",                        # Hindi/Sanskrit: art
        "lalitakala",                  # Sanskrit: fine arts
        "chitrakala",                  # Sanskrit: painting/visual arts
    ]),
]

# Pre-split into multi-word (exact substring) vs single-word (fuzzy token)
_EXACT_KEYWORDS: list[tuple[str, str]] = []   # (label, phrase)
_FUZZY_TOKENS:   list[tuple[str, str]] = []   # (label, token)

for _label, _kws in TYPE_KEYWORDS:
    for _kw in _kws:
        if " " in _kw:
            _EXACT_KEYWORDS.append((_label, _kw))
        else:
            _FUZZY_TOKENS.append((_label, _kw))

# Canonical label order for consistent output
_LABEL_ORDER: list[str] = [label for label, _ in TYPE_KEYWORDS]


# ─── Classifier ──────────────────────────────────────────────────────────────

def _classify(name: Optional[str]) -> Optional[str]:
    """
    Return a comma-separated string of matched institution types, or None.

    Strategy:
      1. Exact substring search for multi-word keywords on the full lowercased name.
      2. For each single-word keyword, check every name-token with rapidfuzz
         ratio >= FUZZY_THRESHOLD (handles ayurved/ayurveda, engeneering/engineering, etc.)
    """
    if not name or not isinstance(name, str):
        return None

    name_lower = name.lower()

    # Tokenize: split on whitespace + punctuation, keep tokens >= 3 chars
    name_tokens = [t for t in re.split(r"[\s\W]+", name_lower) if len(t) >= 3]

    matched: set[str] = set()

    # Pass 1 — exact multi-word substring
    for label, phrase in _EXACT_KEYWORDS:
        if phrase in name_lower:
            matched.add(label)

    # Pass 2 — fuzzy single-word token
    for label, keyword in _FUZZY_TOKENS:
        for token in name_tokens:
            if fuzz.ratio(token, keyword) >= FUZZY_THRESHOLD:
                matched.add(label)
                break  # keyword matched; no need to check more tokens

    if not matched:
        return None

    return ", ".join(t for t in _LABEL_ORDER if t in matched)


# ─── Core pipeline ───────────────────────────────────────────────────────────

def _read_and_clean(table: Table) -> pd.DataFrame:
    """Read raw Excel → clean DataFrame with canonical column names."""
    if not table.raw_path.exists():
        raise SystemExit(
            f"Missing raw file: {table.raw_path}\n"
            f"Download from https://dashboard.aishe.gov.in/hedirectory/#/hedirectory "
            f"and place in aishe/raw/ as '{table.raw_file}'."
        )

    df = pd.read_excel(
        table.raw_path,
        header=table.header_row,  # skip title + date rows; actual headers at row 2
        dtype=str,                 # keep everything as string; avoids float coercion on codes
    )

    # Drop fully-empty rows/columns (Excel exports often have trailing empties)
    df = df.dropna(how="all").reset_index(drop=True)
    df = df.loc[:, df.columns.notna()]
    df = df.loc[:, df.columns.str.strip() != ""]

    # Strip whitespace from all headers and string values
    df.columns = df.columns.str.strip()
    for col in df.select_dtypes("object").columns:
        df[col] = df[col].str.strip()

    # Validate expected source columns before renaming
    missing = set(table.column_renames) - set(df.columns)
    if missing:
        raise SystemExit(
            f"{table.raw_file}: expected columns not found: {sorted(missing)}\n"
            f"Actual columns: {list(df.columns)}"
        )

    df = df.rename(columns=table.column_renames)

    # Cast serial-number columns from float string to nullable Int64
    if "sno" in df.columns:
        df["sno"] = pd.to_numeric(df["sno"], errors="coerce").astype("Int64")

    # Normalise unknown year values ('-') to None
    if "year_of_establishment" in df.columns:
        df["year_of_establishment"] = df["year_of_establishment"].replace("-", None)

    # ── Institution-type classification ──────────────────────────────────────
    name_col = next((c for c in ("name", "institute_name") if c in df.columns), None)
    if name_col:
        df["institution_types"] = df[name_col].apply(_classify)

    return df


def _build(table: Table, dry_run: bool) -> None:
    df = _read_and_clean(table)
    n_rows, n_cols = df.shape
    n_classified = int(df["institution_types"].notna().sum()) if "institution_types" in df.columns else 0

    if dry_run:
        print(f"  [dry-run] {table.bq_name}: {n_rows:,} rows × {n_cols} cols  "
              f"({n_classified:,} classified, {n_rows - n_classified:,} NULL)")
        print(f"    columns: {list(df.columns)}")
        if "institution_types" in df.columns:
            top = (
                df["institution_types"]
                .fillna("NULL")
                .str.split(", ")
                .explode()
                .value_counts()
                .head(12)
            )
            print(f"    top institution_types:\n{top.to_string()}")
        return

    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(table.clean_path, index=False)
    print(
        f"  {table.bq_name}: {n_rows:,} rows × {n_cols} cols  "
        f"({n_classified:,} classified) → {table.clean_path}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--table",
        default=None,
        help="Build only this BQ table (e.g. aishe_fact_colleges).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Read + validate locally; print stats but don't write parquet.",
    )
    args = ap.parse_args()

    if args.table:
        if args.table not in TABLE_BY_NAME:
            raise SystemExit(
                f"Unknown table {args.table!r}. Known: {list(TABLE_BY_NAME)}"
            )
        chosen = [TABLE_BY_NAME[args.table]]
    else:
        chosen = TABLES

    print(
        f"AISHE HE Directory → aishe/clean/   "
        f"({'dry-run' if args.dry_run else 'writing parquet'})"
    )
    for t in chosen:
        _build(t, args.dry_run)
    print("✓ done.")


if __name__ == "__main__":
    main()
