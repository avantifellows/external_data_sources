"""
Maharashtra State CET Cell — multi-stream CAP closing-ranks pipeline.

Maharashtra runs ~10 separate Centralised Admission Processes (CAPs) under
one CET Cell, each on its own portal subdomain. Three of them share the
ASP.NET wrapper format that we extract via base64 (see _mh_streams.py):

  - engineering (fe2025.mahacet.org)
  - pharmacy    (ph2025.mahacet.org)
  - bdesign     (bdesigncap2025.mahacet.org)

These three publish CAP cutoff PDFs in the IDENTICAL layout — one parser
serves all three. This script processes one stream at a time:

    python3 state_MH.py engineering
    python3 state_MH.py pharmacy
    python3 state_MH.py bdesign
    python3 state_MH.py all     # all 3 wrapper-format streams in sequence

Streams using SPAs (agriculture, architecture, llb5, bhmct) need a separate
fetch path through Chrome MCP — they're handled by stream-specific scripts.

Methodology (applied to every stream):
  - Last main round used (CAP IV typically — final main round, R5/Stray excluded)
  - Closing rank = MAX(state merit rank) per
      (college, branch, quota_section, category)
    across the union of all main rounds × all stages within a round.
  - Govt scope = Govt + Govt-Aided + State-Univ-Dept (Status: field).
  - Canonical 5-cat mapping: GEN/EWS/OBC-NCL/SC/ST × Boys/Girls/All;
    everything else flagged as OTHER with sub_pool set.

Reservation taxonomy is shared across MHT-CET-based streams — see
docs/MH_CET_streams.md for the full reservation/quota reference.

Outputs (to ../extracted_data/, prefixed by stream code):
  - MH_<stream>_state_quota_all_stages_2025.csv       — raw long
  - MH_<stream>_state_quota_closing_ranks_2025.csv    — all colleges
  - MH_<stream>_state_quota_closing_ranks_govt_2025.csv  — govt scope
  - MH_<stream>_state_quota_closing_ranks_govt_pivot_StateLevel_2025.csv  — wide
  - MH_<stream>_consolidated_5cat_govt_2025.csv       — schema-canonical
  - MH_<stream>_all_india_allotments_2025.csv         — AI raw
  - MH_<stream>_all_india_closing_ranks_2025.csv      — AI closing
"""
from __future__ import annotations
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = ROOT / "source" / "MH"
OUT = ROOT / "extracted_data"
STATE_CODE = "MH"
YEAR = 2025

# ---- Stream-specific config ----
# (Stream → (cet_name, source_url, source_subdir, file pattern for state quota
#  files, file pattern for AI files, output prefix))
STREAM_CONFIG = {
    "engineering": dict(
        cet_name="MHT-CET",
        source_url="https://fe2025.mahacet.org/",
        subdir="engineering",
        state_files=[
            ("MH_CAP1_state_quota_2025.pdf", "R1"),
            ("MH_CAP2_state_quota_2025.pdf", "R2"),
            ("MH_CAP3_state_quota_2025.pdf", "R3"),
            ("MH_CAP4_state_quota_2025.pdf", "R4"),
        ],
        ai_files=[
            ("MH_CAP1_all_india_2025.pdf", "R1"),
            ("MH_CAP2_all_india_2025.pdf", "R2"),
            ("MH_CAP3_all_india_2025.pdf", "R3"),
            ("MH_CAP4_all_india_2025.pdf", "R4"),
        ],
        out_prefix="engg",
    ),
    "pharmacy": dict(
        cet_name="MHT-CET",                             # B.Pharm uses MHT-CET PCM/PCB
        source_url="https://ph2025.mahacet.org/",
        subdir="pharmacy",
        state_files=[
            ("MH_pharm_CAP1_mh_2025.pdf", "R1"),
            ("MH_pharm_CAP2_mh_2025.pdf", "R2"),
            ("MH_pharm_CAP3_mh_2025.pdf", "R3"),
            ("MH_pharm_CAP4_mh_2025.pdf", "R4"),
        ],
        ai_files=[
            ("MH_pharm_CAP1_ai_2025.pdf", "R1"),
            ("MH_pharm_CAP2_ai_2025.pdf", "R2"),
            ("MH_pharm_CAP3_ai_2025.pdf", "R3"),
            ("MH_pharm_CAP4_ai_2025.pdf", "R4"),
        ],
        out_prefix="pharm",
    ),
    "bdesign": dict(
        cet_name="MAH-AAC-CET",                         # B.Design uses MAH-AAC-CET
        source_url="https://bdesigncap2025.mahacet.org/",
        subdir="bdesign",
        state_files=[
            # Only CAP2-4 had MH cutoff links on the homepage we scraped.
            # CAP1 may need a separate probe.
            ("MH_bdesign_CAP2_mh_2025.pdf", "R2"),
            ("MH_bdesign_CAP3_mh_2025.pdf", "R3"),
            ("MH_bdesign_CAP4_mh_2025.pdf", "R4"),
        ],
        ai_files=[
            ("MH_bdesign_CAP2_ai_2025.pdf", "R2"),
        ],
        out_prefix="bdesign",
    ),
}

# Section / row patterns shared across streams (the PDF layout is identical)
QUOTA_SECTIONS = {
    "State Level": "State Level",
    "Home University Seats Allotted to Home University Candidates": "Home → Home",
    "Home University Seats Allotted to Other Than Home University Candidates": "Home → Other",
    "Other Than Home University Seats Allotted to Other Than Home University Candidates": "Other → Other",
    "Other Than Home University Seats Allotted to Home University Candidates": "Other → Home",
}

SKIP_PREFIXES = (
    "Government of Maharashtra",
    "State Common Entrance",
    "Cut Off List for",
    "Cut Off Merit for",
    "and Technology",
    "Master of Engineering",
    "B .Pharmacy", "B .Pharmacy ", "B.Pharmacy", "Pharm.D",
    "Year 2025-26",
    "Legends:",
    "Page ",
    "PWDR :", "DEFR :", "Starting character",
)
SKIP_SUBSTR = (
    "Maharashtra State Seats - Cut Off",
    "Maharashtra State Seats",
    "Figures in bracket",
)

CATEGORY_TOKEN_RE = re.compile(
    r"^(?:"
    r"[GL](?:OPEN|OBC|SC|ST|VJ|NT[1-3]|SEBC|SBC|MI|MIN)[HOS]"
    r"|EWS|TFWS|ORPHAN|MI|MINO"
    r"|DEF(?:R)?(?:OPEN|OBC|SC|ST|VJ|NT[1-3]|SEBC|SBC)[HOS]"
    r"|PWD(?:R)?(?:OPEN|OBC|SC|ST|VJ|NT[1-3]|SEBC|SBC)[HOS]"
    r"|EMOBC[HOS]?|EMSEBC[HOS]?"
    r"|MIO?|MIH?"
    r")$"
)


# ───────────────────────────────────────────────────────────────────────────
# State quota PDF parser (same logic for engg / pharm / bdesign)
# ───────────────────────────────────────────────────────────────────────────
def _pdftotext(pdf: Path) -> str:
    res = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    )
    return res.stdout


def _scan_categories(line: str, start: int = 0) -> list[tuple[str, int, int]]:
    """Find category-header tokens in `line` starting at column `start`."""
    out = []
    for cm in re.finditer(r"\S+", line[start:]):
        tok = cm.group(0)
        if CATEGORY_TOKEN_RE.match(tok):
            out.append((tok, start + cm.start(), start + cm.end()))
    return out


def parse_state_quota_pdf(pdf_path: Path, round_label: str) -> list[dict]:
    """Parse one CAP-round state-quota cutoff PDF.

    Two layout variants are supported:
      A. Engineering (fe2025): `Stage   CAT1   CAT2   CAT3` on one line
      B. Pharmacy / B.Design (ph2025, bdesigncap2025): categories on the line
         BEFORE the word `Stage`, which sits alone on the next line.

    We track `prev_cat_line` (the most recent line containing category tokens)
    so when we see a bare `Stage` line we can look back.
    """
    text = _pdftotext(pdf_path)
    rows: list[dict] = []

    college_code = college_name = None
    branch_code = branch_name = None
    status = None
    quota_section = None
    cat_columns: list[tuple[str, int, int]] = []
    prev_cat_line: list[tuple[str, int, int]] = []  # categories on prior non-empty line

    for raw in text.splitlines():
        ln = raw.rstrip()
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.startswith(SKIP_PREFIXES):
            continue
        if any(s in stripped for s in SKIP_SUBSTR):
            continue
        if re.match(r"^\d+$", stripped):
            continue

        m = re.match(r"^(\d{5})\s*-\s*(.+)$", stripped)
        if m:
            college_code = m.group(1)
            college_name = m.group(2).strip()
            cat_columns = []
            prev_cat_line = []
            continue

        m = re.match(r"^(\d{10})\s*-\s*(.+)$", stripped)
        if m:
            branch_code = m.group(1)
            branch_name = m.group(2).strip()
            cat_columns = []
            prev_cat_line = []
            continue

        m = re.match(r"^Status:\s*(.+)$", stripped)
        if m:
            status = m.group(1).strip()
            cat_columns = []
            prev_cat_line = []
            continue

        if stripped in QUOTA_SECTIONS:
            quota_section = QUOTA_SECTIONS[stripped]
            cat_columns = []
            prev_cat_line = []
            continue

        m = re.search(r"\bStage\b", ln)
        if m:
            # Variant A: categories on same line, after "Stage"
            same_line_cats = _scan_categories(ln, m.end())
            if same_line_cats:
                cat_columns = same_line_cats
            # Variant B: categories on previous non-empty line
            elif prev_cat_line:
                cat_columns = prev_cat_line
            else:
                cat_columns = []
            prev_cat_line = []
            continue

        # Pre-scan: maybe THIS line is a category-header line for a future Stage
        line_cats = _scan_categories(ln)
        if line_cats and len(line_cats) >= 1 and not re.search(r"\d{2,}", ln):
            # All tokens on this line are categories (no rank numbers) →
            # it's a probable category header line waiting for "Stage"
            prev_cat_line = line_cats
            continue
        else:
            # data row — clear pending category-line buffer
            prev_cat_line = []

        if not (cat_columns and college_code and branch_code and quota_section):
            continue

        # Skip percentile lines (parenthesised)
        if "(" in ln and ")" in ln:
            continue

        # Parse stage label at left of line (informational only)
        stage_match = re.match(
            r"^\s*(I{1,3}|IV|V|VI{0,3}|IX|X|"
            r"I-Non|II-Non|III-Non|"
            r"PWD|Defence|"
            r"\d+(?:-Non)?)\s",
            ln,
        )

        int_tokens = [
            (int(cm.group(0)), cm.start(), cm.end())
            for cm in re.finditer(r"\b(\d{2,7})\b", ln)
        ]
        if not int_tokens:
            continue

        first_cat_col = min(cs for _, cs, _ in cat_columns)
        for val, s, e in int_tokens:
            if s + 2 < first_cat_col - 5:
                continue
            cat = _match_column(s, e, cat_columns)
            if cat is None:
                continue
            stage_label = stage_match.group(1) if stage_match else "?"
            rows.append({
                "round": round_label,
                "stage": stage_label,
                "college_code": college_code,
                "college_name": college_name,
                "branch_code": branch_code,
                "branch_name": branch_name,
                "status": status,
                "quota_section": quota_section,
                "category_raw": cat,
                "rank": val,
            })

    return rows


def _match_column(s: int, e: int, cat_cols, tolerance: int = 6) -> str | None:
    center = (s + e) / 2
    best, best_dist = None, 1e9
    for cat, cs, ce in cat_cols:
        col_center = (cs + ce) / 2
        if cs - tolerance <= center <= ce + tolerance:
            dist = abs(center - col_center)
            if dist < best_dist:
                best, best_dist = cat, dist
    return best


# ───────────────────────────────────────────────────────────────────────────
# All India quota PDF parser
# ───────────────────────────────────────────────────────────────────────────
# Engineering-format AI rows have everything on one line:
#   1   83256 (30.5397513)   0100552410   01005 - Sant ...   Paper and Pulp...   JEE   MH to AI   LSTH
ALLOT_PATTERN_FLAT = re.compile(
    r"^\s*(\d{1,5})\s+"
    r"(\d{1,7})\s*\(([\d.]+)\)\s+"
    r"(\d{10}[A-Z]?)\s+"
    r"(\d{5})\s*-\s*(.+?)\s{2,}"
    r"(.+?)\s{2,}"
    r"(MH to AI|AI to AI|MI to AI)\s+"
    r"([A-Z]{1,12})\s*$"
)

# Pharmacy/B.Design-format AI rows split across 2+ lines:
#   <indented> 03016 - Bombay College of Pharmacy, Santacruz(E), Mumbai     Pharmacy
#       1   857 (84.2494309)    0301682370U                              NEET   AI to AI   AI
ALLOT_PATTERN_RANKROW = re.compile(
    r"^\s*(\d{1,5})\s+"
    r"(\d{1,7})\s*\(([\d.]+)\)\s+"
    r"(\d{10}[A-Z]?)\s+.*?"
    r"(JEE|NEET|MHT-?CET|CET)\s+"
    r"(MH to AI|AI to AI|MI to AI)\s+"
    r"([A-Z]{1,12})\s*$"
)
ALLOT_PATTERN_INSTROW = re.compile(
    r"^\s*(\d{5})\s*-\s*(.+?)\s{2,}([A-Z][\w \-./()&,]+?)\s*$"
)


def parse_all_india_pdf(pdf_path: Path, round_label: str) -> list[dict]:
    """Parse an All India quota PDF. Handles two layouts:
      A. Engineering — everything on one line per record
      B. Pharmacy / B.Design — institute+course on the line ABOVE the rank row
    """
    text = _pdftotext(pdf_path)
    rows: list[dict] = []
    pending_inst: tuple[str, str, str] | None = None  # (code, name, course)
    for ln in text.splitlines():
        # Try the flat (one-line) format first
        m = ALLOT_PATTERN_FLAT.match(ln)
        if m:
            sr, air, pct, choice, coll_code, coll_name, course, atype, seat_type = m.groups()
            rows.append({
                "round": round_label,
                "sr_no": int(sr),
                "all_india_rank": int(air),
                "merit_score": float(pct),
                "choice_code": choice,
                "college_code": coll_code,
                "college_name": coll_name.strip(),
                "branch_code": choice,
                "branch_name": course.strip(),
                "allotment_type": atype,
                "seat_type": seat_type,
            })
            pending_inst = None
            continue

        # Check if this is an institute+course "header" line (variant B)
        m2 = ALLOT_PATTERN_INSTROW.match(ln.strip())
        if m2 and not re.search(r"\(\d", ln):  # no rank+pct → it's an institute row
            pending_inst = (m2.group(1), m2.group(2).strip(), m2.group(3).strip())
            continue

        # Variant B rank-row: needs preceding institute row
        m3 = ALLOT_PATTERN_RANKROW.match(ln)
        if m3 and pending_inst:
            sr, air, pct, choice, exam, atype, seat_type = m3.groups()
            coll_code, coll_name, course = pending_inst
            rows.append({
                "round": round_label,
                "sr_no": int(sr),
                "all_india_rank": int(air),
                "merit_score": float(pct),
                "choice_code": choice,
                "college_code": coll_code,
                "college_name": coll_name,
                "branch_code": choice[:10],
                "branch_name": course,
                "exam": exam,
                "allotment_type": atype,
                "seat_type": seat_type,
            })
            pending_inst = None
            continue
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Canonical category mapping (5-cat NCST space)
# ───────────────────────────────────────────────────────────────────────────
def normalise_category(mh_cat: str) -> tuple[str, str, str]:
    c = mh_cat.upper()
    if c == "TFWS":
        return ("OTHER", "All", "TFWS")
    if c == "ORPHAN":
        return ("OTHER", "All", "ORPHAN")
    if c.startswith("DEFR"):
        return ("OTHER", "All", "DEFR")
    if c.startswith("DEF"):
        return ("OTHER", "All", "DEF")
    if c.startswith("PWD"):
        body = c[3:]
        if body.startswith("R"):
            body = body[1:]
        cat, _, _ = _decode_body(body)
        return (cat, "All", "PWD")
    if c == "EWS":
        return ("EWS", "All", "")
    if c in ("MI", "MINO", "MIH", "MIO", "MIS"):
        return ("OTHER", "All", "MIN")
    if c.startswith("EMOBC"):
        return ("OBC-NCL", "All", "EMOBC")
    if c.startswith("EMSEBC"):
        return ("OTHER", "All", "EMSEBC")
    if c[0] in ("G", "L"):
        gender = "Boys" if c[0] == "G" else "Girls"
        body = c[1:]
        cat, _, _ = _decode_body(body)
        return (cat, gender, "")
    return ("OTHER", "All", "UNKNOWN")


def _decode_body(body: str) -> tuple[str, str, str]:
    if body and body[-1] in ("H", "O", "S"):
        sub = body[-1]
        mid = body[:-1]
    else:
        sub = ""
        mid = body
    mapping = {
        "OPEN": "GEN", "OBC": "OBC-NCL", "SC": "SC", "ST": "ST", "EWS": "EWS",
        "VJ": "OTHER", "NT1": "OTHER", "NT2": "OTHER", "NT3": "OTHER",
        "NTD": "OTHER", "SEBC": "OTHER", "SBC": "OTHER", "MI": "OTHER",
        "MIN": "OTHER",
    }
    return (mapping.get(mid, "OTHER"), mid, sub)


# ───────────────────────────────────────────────────────────────────────────
# College-type classifier (Status → bucket)
# ───────────────────────────────────────────────────────────────────────────
def classify_college_type(status: str | None) -> str:
    if not status:
        return "Unknown"
    s = status.strip()
    if s.startswith("Un-Aided"):
        if "Minority" in s:
            return "Private-Minority"
        return "Private-Unaided"
    if s.startswith("University Managed (Un-Aided)"):
        return "Private-Unaided"
    if s.startswith("Government-Aided"):
        return "Govt-Aided"
    if s.startswith("Government"):
        return "Govt"
    if s.startswith("University Department"):
        return "State-Univ-Dept"
    if s.startswith("University Managed Autonomous") or s.startswith("University Autonomous"):
        return "State-Univ-Dept"
    if s.startswith("University"):
        return "State-Univ-Dept"
    if s.startswith("Deemed"):
        return "Deemed"
    return "Other"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


# ───────────────────────────────────────────────────────────────────────────
# Per-stream pipeline
# ───────────────────────────────────────────────────────────────────────────
def run_stream(stream: str):
    cfg = STREAM_CONFIG[stream]
    source_dir = SOURCE_ROOT / cfg["subdir"]
    prefix = cfg["out_prefix"]

    print("=" * 80)
    print(f"MH stream = {stream}  (source = {cfg['source_url']})")
    print("=" * 80)

    print(f"\nStage 1 — parsing {len(cfg['state_files'])} State Quota cutoff PDFs")
    all_rows = []
    for fname, rlabel in cfg["state_files"]:
        path = source_dir / fname
        if not path.exists():
            print(f"  ✗ {fname} missing — skipping")
            continue
        rows = parse_state_quota_pdf(path, rlabel)
        print(f"  {fname:42s} {rlabel}: {len(rows):,} rank records")
        all_rows.extend(rows)

    if not all_rows:
        print(f"  WARNING: no state-quota rows for stream={stream}")
        return None, None

    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_{prefix}_state_quota_all_stages_{YEAR}.csv", index=False)
    print(f"  TOTAL all-stages: {len(df):,}")

    print("\nStage 2 — aggregating MAX-rank closing ranks across rounds × stages")
    agg = (df.groupby(
        ["college_code", "college_name", "branch_code", "branch_name",
         "status", "quota_section", "category_raw"], dropna=False)
        .agg(closing_rank=("rank", "max"),
             opening_rank=("rank", "min"),
             num_rank_observations=("rank", "count"))
        .reset_index())
    last = (df.sort_values("rank", ascending=False)
              .drop_duplicates(["college_code", "branch_code", "quota_section", "category_raw"])
              [["college_code", "branch_code", "quota_section", "category_raw",
                "round", "stage"]]
              .rename(columns={"round": "last_round_with_max",
                               "stage": "last_stage_with_max"}))
    agg = agg.merge(last, on=["college_code", "branch_code", "quota_section", "category_raw"])

    cat_norm = agg["category_raw"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "gender", "sub_pool"]
    agg = pd.concat([agg, cat_norm], axis=1)

    agg["state"] = "MAHARASHTRA"
    agg["cet_name"] = cfg["cet_name"]
    agg["stream"] = stream
    agg["year"] = YEAR
    rounds_used = "+".join(r for _, r in cfg["state_files"]) + " (cumulative)"
    agg["round"] = rounds_used
    agg["quota"] = agg["quota_section"]
    agg["rank_basis"] = f"{cfg['cet_name']} State Merit Rank"
    agg["source_url"] = cfg["source_url"]
    agg["college_type"] = agg["status"].apply(classify_college_type)

    cols_out = [
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type", "status",
        "branch_code", "branch_name",
        "quota", "category_raw", "category", "gender", "sub_pool",
        "opening_rank", "closing_rank", "num_rank_observations",
        "last_round_with_max", "last_stage_with_max",
        "rank_basis", "source_url",
    ]
    agg_out = agg[cols_out].sort_values(
        ["college_code", "branch_code", "quota", "category_raw"]
    )
    agg_out.to_csv(OUT / f"{STATE_CODE}_{prefix}_state_quota_closing_ranks_{YEAR}.csv", index=False)
    print(f"  closing-rank rows (all colleges):    {len(agg_out):,}")

    govt = agg_out[agg_out["college_type"].isin(GOVT_TYPES)].copy()
    govt.to_csv(OUT / f"{STATE_CODE}_{prefix}_state_quota_closing_ranks_govt_{YEAR}.csv", index=False)
    print(f"  closing-rank rows (govt scope):      {len(govt):,}")
    print(f"  by college_type:")
    for t, n in agg_out.college_type.value_counts().items():
        print(f"    {t:20s} {n:>6,}")
    print(f"  unique govt-scope colleges:          {govt['college_code'].nunique()}")
    print(f"  unique govt-scope college × branch:  {govt.groupby(['college_code','branch_code']).ngroups}")

    # Wide pivot — State Level only
    print("\nStage 2b — wide pivot for govt scope, State Level quota")
    headline_cats = [
        "GOPENS", "LOPENS", "EWS",
        "GOBCS", "LOBCS", "GSCS", "LSCS", "GSTS", "LSTS",
        "GVJS", "LVJS", "GNT1S", "LNT1S", "GNT2S", "LNT2S",
        "GNT3S", "LNT3S", "GSEBCS", "LSEBCS",
        "TFWS", "ORPHAN",
    ]
    sl = govt[govt["quota"] == "State Level"].copy()
    if not sl.empty:
        sl_pivot = sl.pivot_table(
            index=["college_code", "college_name", "college_type",
                   "branch_code", "branch_name"],
            columns="category_raw",
            values="closing_rank",
            aggfunc="first",
        ).reset_index()
        cat_cols_present = [c for c in headline_cats if c in sl_pivot.columns]
        sl_pivot = sl_pivot[
            ["college_code", "college_name", "college_type",
             "branch_code", "branch_name"] + cat_cols_present
        ]
        sl_pivot.to_csv(
            OUT / f"{STATE_CODE}_{prefix}_state_quota_closing_ranks_govt_pivot_StateLevel_{YEAR}.csv",
            index=False,
        )
        print(f"  pivot rows (govt × State Level):     {len(sl_pivot)}")
    else:
        print("  (no State Level rows for this stream)")

    # Schema-canonical 5-cat consolidated long view
    print("\nStage 2c — schema-consistent consolidated MH long view (5-cat)")
    canon = govt[
        (govt["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"]))
        & (govt["sub_pool"].isna() | (govt["sub_pool"] == ""))
    ].copy()
    canon = (canon.groupby(
        ["state", "cet_name", "stream", "year", "round",
         "college_code", "college_name", "college_type",
         "branch_code", "branch_name",
         "quota", "category", "gender"], dropna=False)
        .agg(opening_rank=("opening_rank", "min"),
             closing_rank=("closing_rank", "max"),
             last_round_with_max=("last_round_with_max",
                                   lambda s: s.value_counts().index[0]))
        .reset_index())
    canon["rank_basis"] = f"{cfg['cet_name']} State Merit Rank"
    canon["source_url"] = cfg["source_url"]
    canon.to_csv(
        OUT / f"{STATE_CODE}_{prefix}_consolidated_5cat_govt_{YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows:             {len(canon):,}")

    # All India quota
    print(f"\nStage 3 — parsing {len(cfg['ai_files'])} All India Quota allotment PDFs")
    ai_rows = []
    for fname, rlabel in cfg["ai_files"]:
        path = source_dir / fname
        if not path.exists():
            print(f"  ✗ {fname} missing — skipping")
            continue
        rows = parse_all_india_pdf(path, rlabel)
        print(f"  {fname:42s} {rlabel}: {len(rows):,} allotments")
        ai_rows.extend(rows)
    if ai_rows:
        ai_df = pd.DataFrame(ai_rows)
        ai_df.to_csv(OUT / f"{STATE_CODE}_{prefix}_all_india_allotments_{YEAR}.csv", index=False)
        cr = (ai_df.groupby(
            ["college_code", "college_name", "branch_code", "branch_name", "seat_type"],
            dropna=False)
            .agg(closing_rank=("all_india_rank", "max"),
                 opening_rank=("all_india_rank", "min"),
                 allotted_count=("all_india_rank", "count"))
            .reset_index())
        last = (ai_df.sort_values("all_india_rank", ascending=False)
                  .drop_duplicates(["college_code", "branch_code", "seat_type"])
                  [["college_code", "branch_code", "seat_type", "round"]]
                  .rename(columns={"round": "last_round_with_max"}))
        cr = cr.merge(last, on=["college_code", "branch_code", "seat_type"])
        cr["state"] = "MAHARASHTRA"
        cr["cet_name"] = cfg["cet_name"]
        cr["stream"] = stream
        cr["year"] = YEAR
        cr["round"] = rounds_used
        cr["quota"] = "All India"
        cr["rank_basis"] = "JEE Main / All India Merit"
        cr["source_url"] = cfg["source_url"]
        cr.to_csv(OUT / f"{STATE_CODE}_{prefix}_all_india_closing_ranks_{YEAR}.csv", index=False)
        print(f"  AI closing-rank rows:                {len(cr):,}")

    # Sanity check
    print(f"\n=== {stream} sanity (govt, State Level, GOPENS) ===")
    sample = govt[
        (govt["quota"] == "State Level") & (govt["category_raw"] == "GOPENS")
    ].sort_values("closing_rank").head(8)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank", "last_round_with_max"]]
              .to_string(index=False, max_colwidth=55))

    return agg_out, govt


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)

    arg = sys.argv[1]
    OUT.mkdir(parents=True, exist_ok=True)

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
