"""
Kerala KEAM — engineering closing-ranks pipeline.

Authority:  Commissioner for Entrance Examinations (CEE), Kerala
Portal:     https://cee.kerala.gov.in/keam2025/
Source:     KEAM 2025 Engineering Last Rank Tables (P1, P2-final) at
            cee.kerala.gov.in/keam2025/list/lastrank/
              - p1_last_rank_final.pdf  (Phase 1)
              - last_rank_engg_p2_final.pdf  (Phase 2 = LAST main round)
            (Engineering had 2 main phases in 2025; medical had 3.)

PDF format (clean tabular):
  17 columns per (course-section, college) row:
    College Code | Name | Type (G=Govt / S=Self-financing) |
    SM | EZ | MU | LA | DV | VK | BH | BX | KN | KU | SC | ST | EW |
    Other Categories (free-text: FW:xxxx, YN:xxxx, PD:xxxx, PT:xxxx)
  Each course (CSE, ECE, etc.) has its own table on its page section.

Reservation taxonomy (Kerala — 13 vertical categories):
  Vertical: SM 50% / SEBC 30% (sub-split: EZ 9% Ezhava, MU 8% Muslim,
            BH 3% Backward Hindu, LA 3% Latin Catholic & Anglo Indian,
            DV 2% Dheevara, VK 2% Vishwakarma, KN 1% Kusavan,
            BX 1% Backward Christian) / SC 8% / ST 2% / EW 10% (EWS)
  KU column: Kudumbi (BC, very small)
  Horizontal: PwD 5%, Ex-Servicemen 2% (in "Other Categories" col)
  Special: FW (Fee Waiver, ≤₹2.5L family income), YN (Yatheem/Nirashayar)

  ⚠ Central OBC certificate is NOT valid in Kerala.
    Candidates need state-specific community certificate (e.g.,
    EZ requires Ezhava community proof).

For canonical 5-cat mapping:
  SM                            → GEN
  EZ, MU, BH, LA, DV, VK, BX, KN, KU  → OBC-NCL (Kerala state OBC sub-pools)
  SC                            → SC
  ST                            → ST
  EW                            → EWS
  Other Categories (FW/YN/PD/PT) → flagged via sub_pool

For Avanti JNV KL student:
  - JNV is Central govt school. Kerala has no horizontal "govt school
    student" reservation. Compete in regular state quota under KL-
    specific community certificate (most JNV-KL students may default
    to SM if non-reserved or community is not in the SEBC list).

Methodology:
  - Phase 2 (LAST main phase) used as authoritative closing rank.
    Phase 1 also captured for provenance / round-by-round comparison.
    Stray/reallocation rounds excluded per project pattern.

Output (to extracted_data/):
  - KL_engg_p2_all_cutoffs_2025.csv         — long, every cell from P2
  - KL_engg_p1_all_cutoffs_2025.csv         — long, P1 (reference)
  - KL_engg_closing_ranks_govt_2025.csv     — govt scope (P2 final)
  - KL_engg_consolidated_5cat_govt_2025.csv — schema-canonical
"""
from __future__ import annotations
import re
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "KL" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "KL"
DATA_YEAR = 2025
CET_NAME = "KEAM"
SOURCE_URL = "https://cee.kerala.gov.in/keam2025/last_rank"

PHASE_FILES = [
    ("KL_engg_2025_P1_lrank.pdf", "P1"),
    ("KL_engg_2025_P2_lrank.pdf", "P2"),  # ← LAST main round
]
LAST_PHASE = "P2"

CATEGORY_COLS = ["SM", "EZ", "MU", "LA", "DV", "VK", "BH", "BX", "KN", "KU",
                 "SC", "ST", "EW"]


def parse_kl_pdf(path: Path, phase: str) -> list[dict]:
    """Parse one KEAM Last Rank PDF.

    Each table has a course header row, a column-header row, then
    college rows. We track the current course (set when we see a
    single-cell row at the top of a table) and emit (course, college,
    category, rank) tuples.
    """
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            current_course = None
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r:
                        continue
                    # Course header: first cell has text, rest are None
                    if r[0] and not r[2] and not (len(r) > 3 and r[3]):
                        current_course = (r[0] or "").strip()
                        continue
                    # Column header row: cell[0] is "Name of College" or None, cell[2] is "Type" or "SM"
                    if r[0] in ("Name of College", None) and any(c == "SM" for c in r[2:5]):
                        continue
                    # Data row: r[0] = code (3-letter), r[1] = full college name
                    code = (r[0] or "").strip()
                    if not (code and len(code) >= 2 and len(code) <= 6 and code.replace("/", "").isalnum()):
                        continue
                    name = (r[1] or "").replace("\n", " ").strip()
                    coll_type = (r[2] or "").strip().upper()  # G or S
                    if not coll_type:
                        continue
                    # Categories at columns 3..15 (13 categories)
                    for i, cat in enumerate(CATEGORY_COLS):
                        col_idx = 3 + i
                        if col_idx >= len(r):
                            continue
                        v = (r[col_idx] or "").strip()
                        if not v or v in ("-", "--"):
                            continue
                        try:
                            rank = int(v.replace(",", ""))
                        except ValueError:
                            continue
                        rows.append({
                            "phase": phase,
                            "course": current_course,
                            "college_code": code,
                            "college_name": name,
                            "college_type_raw": coll_type,
                            "category_raw": cat,
                            "closing_rank": rank,
                        })
                    # Other Categories column (col 16): free-text like "FW:11944, PD:42925"
                    if len(r) > 16 and r[16]:
                        other_text = r[16].strip()
                        for m in re.finditer(r"([A-Z]{1,3}):(\d+)", other_text):
                            sub_code, val = m.group(1), m.group(2)
                            try:
                                rank = int(val)
                            except ValueError:
                                continue
                            rows.append({
                                "phase": phase,
                                "course": current_course,
                                "college_code": code,
                                "college_name": name,
                                "college_type_raw": coll_type,
                                "category_raw": sub_code,  # FW / PD / YN / PT etc.
                                "closing_rank": rank,
                            })
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Govt classifier — KEAM uses Type column directly: G = Govt (incl. Govt-Aided), S = Self-financing/Private
# ───────────────────────────────────────────────────────────────────────────
def classify_kl_college(coll_type_raw: str) -> str:
    t = coll_type_raw.strip().upper()
    if t == "G":
        return "Govt"   # Kerala collapses Govt + Govt-Aided into single 'G' category
    if t == "S":
        return "Private/SF"
    return "Unknown"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


# ───────────────────────────────────────────────────────────────────────────
# Canonical 5-cat mapping
# ───────────────────────────────────────────────────────────────────────────
def normalise_category(c: str) -> tuple[str, str]:
    """Return (canonical_category, sub_pool)."""
    c = c.strip().upper()
    if c == "SM": return ("GEN", "")
    if c in ("EZ", "MU", "LA", "DV", "VK", "BH", "BX", "KN", "KU"):
        return ("OBC-NCL", c)
    if c == "SC": return ("SC", "")
    if c == "ST": return ("ST", "")
    if c == "EW": return ("EWS", "")
    if c == "FW": return ("OTHER", "FW")  # Fee Waiver
    if c == "YN": return ("OTHER", "YN")  # Yatheem/Nirashayar (orphan/destitute)
    if c == "PD": return ("OTHER", "PD")  # PwD
    if c == "PT": return ("OTHER", "PT")  # Sports/PT
    return ("OTHER", c)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse Phase 1 + Phase 2 KEAM engineering PDFs")
    all_rows = []
    for fname, phase in PHASE_FILES:
        path = SOURCE / fname
        if not path.exists():
            print(f"  ✗ {fname} missing")
            continue
        rows = parse_kl_pdf(path, phase)
        print(f"  {fname:42s} {phase:3s}: {len(rows):,} cell rows")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    print(f"\n  TOTAL all-phases: {len(df):,}")
    print(f"  Distinct (college, course): "
          f"{df.groupby(['college_code','course']).ngroups}")
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_phases_{DATA_YEAR}.csv", index=False)

    # Phase 2 = LAST main phase, authoritative for closing
    print(f"\nStage 2 — closing ranks: take MAX(rank) across phases (P2 dominates as final)")
    closing = (df.groupby(
        ["college_code", "college_name", "college_type_raw",
         "course", "category_raw"], dropna=False)
        .agg(opening_rank=("closing_rank", "min"),
             closing_rank=("closing_rank", "max"),
             last_phase_with_max=("phase",
                                   lambda s: s.value_counts().index[0]))
        .reset_index())
    print(f"  closing-rank rows (all colleges): {len(closing):,}")

    print("\nStage 3 — classify govt scope")
    closing["college_type"] = closing["college_type_raw"].apply(classify_kl_college)
    print("  by college_type:")
    for t, n in (closing.groupby(["college_code","college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = closing[closing["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_code'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    cat_norm = govt["category_raw"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "sub_pool"]
    govt = pd.concat([govt, cat_norm], axis=1)

    govt["state"] = "KERALA"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "P1+P2 cumulative (P2 = last main phase)"
    govt["quota"] = "State (Kerala domicile)"
    govt["gender"] = "All"  # KEAM doesn't split by gender in Last Rank Table
    govt["rank_basis"] = "KEAM State Rank"
    govt["source_url"] = SOURCE_URL

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "course",
        "quota", "category_raw", "category", "sub_pool", "gender",
        "opening_rank", "closing_rank", "last_phase_with_max",
        "rank_basis", "source_url",
    ]].rename(columns={"course": "branch_name"}).sort_values(
        ["college_code", "branch_name", "category_raw"]
    )
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    # 5-cat consolidated
    print("\nStage 4 — schema-canonical 5-cat consolidated")
    canon = govt_out[
        (govt_out["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"]))
    ].copy()
    canon["branch_code"] = canon["branch_name"]  # KEAM uses course as identifier
    canon = canon.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(
        opening_rank=("opening_rank", "min"),
        closing_rank=("closing_rank", "max"),
        last_round_with_max=("last_phase_with_max",
                              lambda s: s.value_counts().index[0]),
    ).reset_index()
    canon["rank_basis"] = "KEAM State Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== KL sanity (govt scope, SM/Open, hardest 12) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "SM")
    ].sort_values("closing_rank").head(12)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=50))


if __name__ == "__main__":
    main()
