"""
Karnataka KCET (UGCET) — multi-stream closing-ranks pipeline.

Authority: Karnataka Examinations Authority (KEA)
           https://cetonline.karnataka.gov.in/kea/
Source:    KEA per-stream cutoff PDFs (Round 2 Final + Extended Round =
           the LAST round). Per-college, per-branch table with 24 cells
           (8 verticals × 3 horizontal sub-pools).

NOTE on year:
  KCET 2025 cutoff PDFs are NOT yet published as flat URLs (KEA serves the
  data only via the cutoffanalyser.aspx interactive tool). We use
  KCET 2024 EXT_RND (Extended Round, the last main round, 09-Oct-2024)
  as a PROXY for 2025 — same precedent as the medical-side Rajasthan
  scrape used 2024 NEET data as proxy for 2025. To re-run when 2025
  publishes, update YEAR and the URL pattern in download_KA.py.

Reservation taxonomy (KCET 2024):
  Vertical (caste): 1, 2A, 2B, 3A, 3B, GM, SC, ST
  Horizontal:       G (General), K (Kannada Medium 5%), R (Rural 15%)
  Domicile sub-pool: GEN (Rest of Karnataka, default) | HK (Hyderabad-
                     Karnataka 8% under Article 371J — for 7 NE Karnataka
                     districts only)

Note: EWS does NOT appear as a separate column in the 2024 KCET cutoff
PDFs. Karnataka subsumes EWS within the GM-EWS sub-pool which is
counselled separately and not in the consolidated cutoff PDF.

For canonical 5-cat mapping:
  GM     → GEN (General Merit)
  1, 2A, 2B, 3A, 3B → OBC-NCL (approximately — KA's BCs don't 1:1 map to
                      Central OBC-NCL list; documented as deviation)
  SC     → SC
  ST     → ST
  EWS    → not directly available

Govt-college filter: in KCET, college codes E001-E099 are typically state
govt or govt-aided. Most KCET colleges are private — we'll cross-check the
Status column in the per-college section AND use a fee-threshold as
secondary signal (govt fee ~₹64k vs private ~₹1L+). For 2024, the cutoff
PDF doesn't carry fee directly — we'll classify using the college-name
prefix patterns: "Govt." / "University of" / "State Govt" → govt; else
private/aided unless cross-listed in DTE govt list.

Output (to extracted_data/):
  - KA_<stream>_all_cutoffs_<year>.csv         — long, every (college,
                                                  branch, cell) row
  - KA_<stream>_closing_ranks_govt_<year>.csv  — govt scope
  - KA_<stream>_consolidated_5cat_govt_<year>.csv — schema-canonical
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

import pdfplumber
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ROOT / "source" / "KA"
OUT = ROOT / "extracted_data"
STATE_CODE = "KA"
DATA_YEAR = 2024
SOURCE_URL = "https://cetonline.karnataka.gov.in/kea/cutoff.aspx"

STREAM_CONFIG = {
    "engineering": dict(
        cet_name="KCET",
        files=[
            ("KA_engg_2024_GEN_EXT_RND.pdf", "GEN"),
            ("KA_engg_2024_HK_EXT_RND.pdf",  "HK"),
        ],
        out_prefix="engg",
        college_code_prefix="E",
        notes="EXT_RND = Extended Round (final). 2024 used as proxy for 2025.",
    ),
    "pharmacy": dict(
        cet_name="KCET",
        files=[
            ("KA_pharma_2024_GEN_EXT_RND.pdf", "GEN"),
            ("KA_pharma_2024_HK_EXT_RND.pdf",  "HK"),
        ],
        out_prefix="pharm",
        college_code_prefix="P",
        notes="2024 EXT_RND used as proxy for 2025.",
    ),
    "agriculture": dict(
        cet_name="KCET",
        files=[
            ("KA_agri_2024_GEN_EXT_RND.pdf", "GEN"),
            ("KA_agri_2024_HK_EXT_RND.pdf",  "HK"),
        ],
        out_prefix="agri",
        college_code_prefix="A",
        notes="2024 EXT_RND used as proxy for 2025.",
    ),
    "nursing": dict(
        cet_name="KCET",
        files=[
            ("KA_BSCNURS_2024_GEN_EXT_RND.pdf", "GEN"),
            ("KA_BSCNURS_2024_HK_EXT_RND.pdf",  "HK"),
        ],
        out_prefix="bscnurs",
        college_code_prefix="N",
        notes="2024 EXT_RND used as proxy for 2025.",
    ),
}


# Vertical caste codes in column header order
KA_VERTICALS = ["1", "2A", "2B", "3A", "3B", "GM", "SC", "ST"]
KA_HORIZONTALS = ["G", "K", "R"]   # General, Kannada-medium, Rural

# Verticals that exist in 2024 KCET PDF columns:
#   GEN PDF: <vertical><horizontal>      e.g., 1G, 1K, 1R, 2AG, ..., STR
#   HK  PDF: <vertical>[horizontal]H     e.g., 1H, 1KH, 1RH, 2AH, ..., STRH
#     (in HK, horizontal=G is omitted before H — `1H` means vert=1, horiz=G, domicile=HK)
EXPECTED_COLUMNS = (
    [v + h for v in KA_VERTICALS for h in KA_HORIZONTALS]
    + [v + "H" for v in KA_VERTICALS]
    + [v + h + "H" for v in KA_VERTICALS for h in ("K", "R")]
)


def parse_kcet_pdf(pdf_path: Path, variant: str) -> list[dict]:
    """Parse one KCET cutoff PDF (e.g., KA_engg_2024_GEN_EXT_RND.pdf).

    Returns one row per (college, branch, vertical, horizontal, variant)
    cell that has a closing rank.
    """
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        cur_college_code: str | None = None
        cur_college_name: str | None = None
        for page in pdf.pages:
            # Get text first to find college headers
            text = page.extract_text() or ""
            tables = page.extract_tables() or []

            # College headers are lines like:
            # "  1   E001   University of Visvesvaraya College of Engineering   Bangalore ( PUBLIC UNIV. )"
            # We track them by line order on each page
            college_headers = []
            for ln in text.splitlines():
                m = re.match(
                    r"^\s*(\d+)\s+([A-Z]\d{3})\s+(.+?)\s*$",
                    ln,
                )
                if m:
                    college_headers.append((m.group(2), m.group(3).strip()))

            # Each table is a set of branch rows for one college.
            # Match each table to the most recently seen college header.
            ci = 0
            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                header = tbl[0]
                # Verify this is a cutoff table (first column should be empty/None,
                # subsequent columns should be category codes)
                if not header or len(header) < 10:
                    continue
                cat_cols = [c.strip() if c else "" for c in header[1:]]
                if not any(c in EXPECTED_COLUMNS for c in cat_cols):
                    continue

                # Pick college: use the next unmatched college header
                if ci < len(college_headers):
                    cur_college_code, cur_college_name = college_headers[ci]
                    ci += 1
                if not cur_college_code:
                    continue

                # Branch rows
                for r in tbl[1:]:
                    if not r or not r[0]:
                        continue
                    branch_str = r[0].strip().replace("\n", " ")
                    bm = re.match(r"^([A-Z]{2})\s+(.+)$", branch_str)
                    if not bm:
                        continue
                    branch_code = bm.group(1)
                    branch_name = bm.group(2).strip()
                    # Extract values aligned to header
                    for cat_code, val in zip(cat_cols, r[1:]):
                        if not val:
                            continue
                        v = val.strip()
                        if v in ("--", "-", ""):
                            continue
                        try:
                            rank = int(v.replace(",", ""))
                        except ValueError:
                            continue
                        # Decode vertical + horizontal from cat_code
                        vert, horiz = _decode_cat(cat_code)
                        if vert is None:
                            continue
                        rows.append({
                            "college_code": cur_college_code,
                            "college_name": cur_college_name,
                            "branch_code": branch_code,
                            "branch_name": branch_name,
                            "category_raw": cat_code,
                            "vertical": vert,
                            "horizontal": horiz,
                            "domicile_sub_pool": variant,
                            "closing_rank": rank,
                        })
    return rows


def _decode_cat(cat: str) -> tuple[str | None, str | None]:
    """Split column code like '2AR' (GEN) or '2ARH' (HK) into
    (vertical, horizontal). Domicile sub-pool is encoded by the trailing H
    in HK PDFs, but is passed via the `variant` parameter to the parser
    (so we strip it here).

    Returns (vertical, horizontal) where horizontal ∈ {G, K, R}.
      e.g., '2AR'  → ('2A', 'R')
            '2ARH' → ('2A', 'R')
            'GM'   → ('GM', 'G')
            'GMH'  → ('GM', 'G')
            '1KH'  → ('1',  'K')
    """
    cat = cat.strip()
    # Try with trailing H (HK domicile) first
    if cat.endswith("H"):
        body = cat[:-1]
    else:
        body = cat
    for v in KA_VERTICALS:
        if body.startswith(v):
            rem = body[len(v):]
            if rem in ("G", "K", "R", ""):
                return (v, rem if rem else "G")
    return (None, None)


# ───────────────────────────────────────────────────────────────────────────
# Canonical 5-cat mapping
# ───────────────────────────────────────────────────────────────────────────
def normalise_vertical(v: str) -> str:
    return {
        "GM": "GEN",
        "1":  "OBC-NCL",   # KA Cat 1 (BC) — approximate
        "2A": "OBC-NCL",
        "2B": "OBC-NCL",
        "3A": "OBC-NCL",
        "3B": "OBC-NCL",
        "SC": "SC",
        "ST": "ST",
    }.get(v, "OTHER")


# ───────────────────────────────────────────────────────────────────────────
# Govt-college classifier — explicit whitelist of KA govt+aided engineering
# institutions. "University" alone in the name is NOT a govt signal in KA
# (many private deemed universities like PES, Reva, CMR, Christ qualify).
#
# Whitelist sources:
#  - Govt: 14 Government Engineering Colleges run by DTE Karnataka
#  - State govt universities: UVCE Bangalore, UBDT Davangere
#  - Govt-Aided (legacy): BMSCE, RVCE, MSRIT, NIE Mysore, BIT Bangalore,
#    SJCE/JSS Mysore, BVBCET/KLE Tech Univ Dharwad, MITE Mangalore, Dayananda
#    Sagar, KSIT, etc. — these have aided-status historically but most are
#    "deemed-private" or "fully aided private" — we mark them as Govt-Aided
#    only if they receive substantive state aid.
#  - We use an explicit whitelist and document deviations.
# ───────────────────────────────────────────────────────────────────────────
KA_GOVT_PATTERNS = [
    # Strong govt signals (state govt run / state public university)
    (r"\bGovt\.?\s+(Engineering|Polytechnic|Tool|SKSJT|Engg)", "Govt"),
    (r"\bGovernment\s+", "Govt"),
    (r"\bUniversity\s+of\s+Visvesvaraya\b", "Govt"),  # UVCE, public state
    (r"\bU\.?B\.?D\.?T\.?\s", "Govt"),                # UBDT Davangere, public state
    (r"\bS\.?K\.?S\.?J\.?T\.?\s", "Govt"),            # SKSJT Bangalore, govt
    (r"^Visvesvaraya Technological University", "Govt"),  # VTU
    # Govt-Aided well-known institutions (require explicit name match)
    (r"\bDr\.?\s+Ambedkar Institute Of Tech", "Govt-Aided"),
    (r"\bUVCE\b", "Govt"),
    # State-Univ-Dept (state public universities running their own engg)
    (r"^Karnatak University\b", "State-Univ-Dept"),
    (r"^Mangalore University\b", "State-Univ-Dept"),
    (r"^Bengaluru University\b", "State-Univ-Dept"),
    (r"\bKLE\s+Technological\s+University", "Govt-Aided"),
    (r"\bJSS\s+Science\s+and\s+Technology\s+University", "Govt-Aided"),
    (r"\bBangalore\s+Institute\s+of\s+Technology", "Govt-Aided"),  # BIT
    (r"\bNational\s+Institute\s+of\s+Engineering", "Govt-Aided"),  # NIE Mysore
    (r"\bSiddaganga\s+Institute\s+of\s+Technology", "Govt-Aided"),  # SIT Tumkur
]


def classify_ka_college(name: str) -> str:
    """Classify a KA college from name only.
    Returns 'Govt', 'Govt-Aided', 'State-Univ-Dept', or 'Private/Deemed'."""
    if not name:
        return "Unknown"
    for pat, cls in KA_GOVT_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            return cls
    return "Private/Deemed"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


# ───────────────────────────────────────────────────────────────────────────
# Per-stream pipeline
# ───────────────────────────────────────────────────────────────────────────
def run_stream(stream: str):
    cfg = STREAM_CONFIG[stream]
    source_dir = SOURCE_ROOT / stream
    prefix = cfg["out_prefix"]

    print("=" * 80)
    print(f"KA stream = {stream} ({cfg['notes']})")
    print("=" * 80)

    print(f"\nStage 1 — parsing {len(cfg['files'])} cutoff PDFs (GEN + HK variants)")
    all_rows = []
    for fname, variant in cfg["files"]:
        path = source_dir / fname
        if not path.exists():
            print(f"  ✗ {fname} missing")
            continue
        rows = parse_kcet_pdf(path, variant)
        print(f"  {fname:42s} {variant:3s}: {len(rows):,} cell rows")
        all_rows.extend(rows)
    if not all_rows:
        print(f"  ERROR: no rows parsed for {stream}")
        return

    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_{prefix}_all_cutoffs_{DATA_YEAR}.csv", index=False)
    print(f"  TOTAL rows: {len(df):,}")
    print(f"  Distinct colleges: {df['college_code'].nunique()}")
    print(f"  Distinct (college × branch): "
          f"{df.groupby(['college_code','branch_code']).ngroups}")

    # Govt classification (whitelist)
    df["college_type"] = df["college_name"].apply(classify_ka_college)
    govt = df[df["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  by college_type:")
    for t, n in df.college_type.value_counts().items():
        print(f"    {t:20s} {n:>5,}  cells")
    print(f"  unique govt-scope colleges:         {govt['college_code'].nunique()}")

    govt["state"] = "KARNATAKA"
    govt["cet_name"] = cfg["cet_name"]
    govt["stream"] = stream
    govt["year"] = DATA_YEAR
    govt["round"] = "EXT_RND (last main round, 09-Oct-2024)"
    govt["category"] = govt["vertical"].apply(normalise_vertical)
    govt["rank_basis"] = "KCET State Merit Rank"
    govt["source_url"] = SOURCE_URL
    # college_type already set by classify_ka_college

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "category_raw", "vertical", "category", "horizontal",
        "domicile_sub_pool",
        "closing_rank",
        "rank_basis", "source_url",
    ]].sort_values(["college_code", "branch_code", "domicile_sub_pool",
                    "vertical", "horizontal"])
    govt_out.to_csv(OUT / f"{STATE_CODE}_{prefix}_closing_ranks_govt_{DATA_YEAR}.csv",
                    index=False)
    print(f"  govt closing-rank rows:             {len(govt_out):,}")

    # Schema-canonical 5-cat — use horizontal=G (General, default — JNV
    # rural students could also use R/K but for the headline mapping use G)
    print("\nStage 2 — schema-canonical 5-cat consolidated (default horizontal G)")
    canon = govt_out[
        govt_out["category"].isin(["GEN", "OBC-NCL", "SC", "ST"])
        & (govt_out["horizontal"] == "G")
        & (govt_out["domicile_sub_pool"] == "GEN")
    ].copy()
    # KCET doesn't have boys/girls split; mark gender as "All"
    canon["gender"] = "All"
    canon["quota"] = "State (rest of Karnataka)"
    canon = canon.groupby(
        ["state", "cet_name", "stream", "year", "round",
         "college_code", "college_name", "college_type",
         "branch_code", "branch_name",
         "quota", "category", "gender"], dropna=False).agg(
        opening_rank=("closing_rank", "min"),  # one value per cell — opening = closing
        closing_rank=("closing_rank", "max"),
    ).reset_index()
    canon["rank_basis"] = "KCET State Merit Rank"
    canon["source_url"] = SOURCE_URL
    canon["last_round_with_max"] = "EXT_RND"
    canon.to_csv(
        OUT / f"{STATE_CODE}_{prefix}_consolidated_5cat_govt_{DATA_YEAR}.csv",
        index=False,
    )
    print(f"  consolidated 5-cat rows:            {len(canon):,}")

    # Sanity check — top 8 hardest GM/G General college × branch
    print(f"\n=== {stream} sanity (govt scope, GM+G default General) ===")
    sample = govt_out[
        (govt_out["vertical"] == "GM") & (govt_out["horizontal"] == "G")
        & (govt_out["domicile_sub_pool"] == "GEN")
    ].sort_values("closing_rank").head(10)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        print(f"\nAvailable streams: {sorted(STREAM_CONFIG)}")
        sys.exit(2)
    OUT.mkdir(parents=True, exist_ok=True)
    arg = sys.argv[1]
    if arg == "all":
        for s in STREAM_CONFIG:
            run_stream(s)
    elif arg in STREAM_CONFIG:
        run_stream(arg)
    else:
        print(f"ERROR: stream '{arg}' not in {sorted(STREAM_CONFIG)}")
        sys.exit(2)
    print(f"\n→ Outputs in {OUT}")


if __name__ == "__main__":
    main()
