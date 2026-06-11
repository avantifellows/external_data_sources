"""
Telangana TG-EAPCET (formerly TS EAMCET) — engineering closing-ranks pipeline.

Authority:  TGCHE (Telangana State Council of Higher Education)
            + Convener TG-EAPCET / JNTU Hyderabad
Portal:     https://tgeapcet.nic.in/  (rolled into 2026 mode; 2025 PDFs no
            longer at original URLs)
Source:     TG-EAPCET 2024 Last Rank Statements (P1, P2, FinalPhase) sourced
            from Drive mirrors via forum.universityupdates.in. Used as
            proxy for 2025 — same precedent as KA / RJ.

PDF format (clean tabular, pdfplumber extracts cleanly):
  29 columns per (college, branch) row:
    Inst Code | Institute Name | Place | Dist Code | Co Education |
    College Type (PVT/GOVT/UNIV) | Year of Estab | Branch Code | Branch Name |
    OC_BOYS | OC_GIRLS | BC_A BOYS | BC_A GIRLS | BC_B BOYS | BC_B GIRLS |
    BC_C BOYS | BC_C GIRLS | BC_D BOYS | BC_D GIRLS | BC_E BOYS | BC_E GIRLS |
    SC_BOYS | SC_GIRLS | ST_BOYS | ST_GIRLS | EWS_GEN_OU | EWS_GIRLS_OU |
    Tuition Fee | Affiliated To

Reservation taxonomy (Telangana):
  Vertical (caste): OC / BC_A / BC_B / BC_C / BC_D / BC_E / SC / ST + EWS
  Horizontal: BOYS / GIRLS (33% women's reservation embedded)
  Local-area sub-pools: OU (Osmania — covers most of TG) / KU (Kakatiya —
                        Warangal area) / TGUR (TG Universal/non-local 15%)
                        — the published PDF appears to show OU sub-pool ranks
                        primarily; EWS is OU-specific in this PDF.

For canonical 5-cat mapping (NCST schema):
  OC                                → GEN
  BC_A, BC_B, BC_C, BC_D, BC_E      → OBC-NCL (TG's BC sub-list — approximate)
  SC                                → SC
  ST                                → ST
  EWS                               → EWS

For Avanti JNV TG student:
  - JNV is Central govt school — no horizontal "govt school student"
    reservation in TG. Compete in regular OC/BC*/SC/ST per caste category.
  - Local area: most JNV districts in TG would be OU (Osmania); Warangal/
    Karimnagar/Khammam districts → KU. The PDF doesn't expose local area
    explicitly per row except for EWS, so we use the headline closing rank.

Methodology: TG publishes Phase 1, Phase 2, and Final Phase last-rank PDFs.
Final Phase = cumulative through Phase 3 (the last main allotment round).
Stray vacancy rounds excluded. We use Final Phase as the authoritative
closing rank.

Output (to extracted_data/):
  - TG_engg_all_cutoffs_2024.csv         — long, every (college, branch, cat) cell
  - TG_engg_closing_ranks_govt_2024.csv  — govt scope
  - TG_engg_consolidated_5cat_govt_2024.csv  — schema-canonical
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "TG" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "TG"
DATA_YEAR = 2024  # TG-EAPCET 2024 used as proxy for 2025
CET_NAME = "TG-EAPCET"
SOURCE_URL = "https://tgeapcet.nic.in/"

PHASE_FILES = [
    ("TG_EAPCET_2024_FirstPhase_LastRanks.pdf", "P1"),
    ("TG_EAPCET_2024_SecondPhase_LastRanks.pdf", "P2"),
    ("TG_EAPCET_2024_FinalPhase_LastRanks.pdf",  "PFinal"),  # ← used for closing
]

# Cell column → (canonical_category, gender)
CELL_COLUMNS = [
    # (col_idx, raw_label, canonical_cat, gender)
    (9,  "OC_BOYS",      "GEN",      "Boys"),
    (10, "OC_GIRLS",     "GEN",      "Girls"),
    (11, "BC_A_BOYS",    "OBC-NCL",  "Boys"),
    (12, "BC_A_GIRLS",   "OBC-NCL",  "Girls"),
    (13, "BC_B_BOYS",    "OBC-NCL",  "Boys"),
    (14, "BC_B_GIRLS",   "OBC-NCL",  "Girls"),
    (15, "BC_C_BOYS",    "OBC-NCL",  "Boys"),
    (16, "BC_C_GIRLS",   "OBC-NCL",  "Girls"),
    (17, "BC_D_BOYS",    "OBC-NCL",  "Boys"),
    (18, "BC_D_GIRLS",   "OBC-NCL",  "Girls"),
    (19, "BC_E_BOYS",    "OBC-NCL",  "Boys"),
    (20, "BC_E_GIRLS",   "OBC-NCL",  "Girls"),
    (21, "SC_BOYS",      "SC",       "Boys"),
    (22, "SC_GIRLS",     "SC",       "Girls"),
    (23, "ST_BOYS",      "ST",       "Boys"),
    (24, "ST_GIRLS",     "ST",       "Girls"),
    (25, "EWS_GEN_OU",   "EWS",      "Boys"),
    (26, "EWS_GIRLS_OU", "EWS",      "Girls"),
]


def parse_tg_phase_pdf(pdf_path: Path, phase_label: str) -> list[dict]:
    """Parse one TG-EAPCET phase Last Rank PDF; return cell-level rows."""
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for tbl in tables:
                for r in tbl:
                    if not r or len(r) < 27:
                        continue
                    code = (r[0] or "").strip()
                    # Header rows have no 4-letter code
                    if not (len(code) >= 3 and code.isalpha() and code.isupper()):
                        continue
                    branch_code = (r[7] or "").strip()
                    if not branch_code:
                        continue
                    college = (r[1] or "").strip()
                    place = (r[2] or "").strip()
                    dist = (r[3] or "").strip()
                    coed = (r[4] or "").strip()
                    coll_type = (r[5] or "").strip().upper()
                    estd = (r[6] or "").strip()
                    branch_name = (r[8] or "").strip()
                    affiliated = (r[28] or "").strip() if len(r) > 28 else ""
                    fee = (r[27] or "").strip() if len(r) > 27 else ""

                    for col_idx, raw_lbl, cat, gender in CELL_COLUMNS:
                        if col_idx >= len(r):
                            continue
                        v = (r[col_idx] or "").strip()
                        if not v or v in ("--", "-"):
                            continue
                        try:
                            rank = int(v.replace(",", ""))
                        except ValueError:
                            continue
                        rows.append({
                            "phase": phase_label,
                            "college_code": code,
                            "college_name": college,
                            "place": place,
                            "dist": dist,
                            "coed": coed,
                            "college_type_raw": coll_type,
                            "estd": estd,
                            "branch_code": branch_code,
                            "branch_name": branch_name,
                            "category_raw": raw_lbl,
                            "category": cat,
                            "gender": gender,
                            "closing_rank": rank,
                            "tuition_fee": fee,
                            "affiliated_to": affiliated,
                        })
    return rows


def classify_tg_college(coll_type_raw: str, college_name: str, affiliated: str) -> str:
    """Govt scope classifier.
    PDF has 'PVT' / 'GOVT' / 'UNIV' in college_type column. Use that as primary.
    """
    t = coll_type_raw.strip().upper()
    if t == "GOVT":
        return "Govt"
    if t == "UNIV":
        return "State-Univ-Dept"
    if t == "PVT":
        # Check if it's a govt-aided autonomous (mostly we'll skip these)
        return "Private/SF"
    # Heuristic fallback by name pattern
    if "GOVERNMENT" in college_name.upper() or "GOVT" in college_name.upper():
        return "Govt"
    if "UNIVERSITY" in college_name.upper():
        return "State-Univ-Dept"
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse TG phase PDFs (P1, P2, FinalPhase)")
    all_rows = []
    for fname, phase in PHASE_FILES:
        path = SOURCE / fname
        if not path.exists():
            print(f"  ✗ {fname} missing")
            continue
        rows = parse_tg_phase_pdf(path, phase)
        print(f"  {fname:55s} {phase:8s}: {len(rows):,} cell rows")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    print(f"\n  TOTAL all-phases: {len(df):,} cell rows")
    print(f"  Distinct colleges: {df['college_code'].nunique()}")
    print(f"  Distinct (college × branch): "
          f"{df.groupby(['college_code','branch_code']).ngroups}")
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_phases_{DATA_YEAR}.csv", index=False)

    print("\nStage 2 — closing ranks: take MAX(rank) across all 3 phases")
    closing = (df.groupby(
        ["college_code", "college_name", "place", "dist", "coed",
         "college_type_raw", "estd", "branch_code", "branch_name",
         "category_raw", "category", "gender", "tuition_fee", "affiliated_to"],
        dropna=False,
    ).agg(
        opening_rank=("closing_rank", "min"),
        closing_rank=("closing_rank", "max"),
        last_phase_with_max=("phase",
                              lambda s: s.value_counts().index[0]),
    ).reset_index())
    print(f"  closing-rank rows (all colleges): {len(closing):,}")

    print("\nStage 3 — classify govt scope")
    closing["college_type"] = closing.apply(
        lambda r: classify_tg_college(r["college_type_raw"], r["college_name"], r["affiliated_to"]),
        axis=1,
    )
    print("  by college_type:")
    for t, n in (closing.groupby(["college_code","college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = closing[closing["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_code'].nunique()}")
    print(f"  govt closing-rank rows: {len(govt):,}")

    govt["state"] = "TELANGANA"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "P1+P2+PFinal cumulative (last-rank PDFs)"
    govt["quota"] = "State (TG domicile)"
    govt["rank_basis"] = "TG-EAPCET State Rank"
    govt["source_url"] = SOURCE_URL

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category_raw", "category", "gender",
        "opening_rank", "closing_rank", "last_phase_with_max",
        "rank_basis", "source_url",
    ]].sort_values(["college_code", "branch_code", "category_raw", "gender"])
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    # 5-cat consolidated (BC_A...BC_E aggregated to OBC-NCL)
    print("\nStage 4 — schema-canonical 5-cat consolidated")
    canon = govt.groupby(
        ["state", "cet_name", "stream", "year", "round",
         "college_code", "college_name", "college_type",
         "branch_code", "branch_name",
         "quota", "category", "gender"],
        dropna=False,
    ).agg(
        opening_rank=("opening_rank", "min"),
        closing_rank=("closing_rank", "max"),
        last_round_with_max=("last_phase_with_max",
                              lambda s: s.value_counts().index[0]),
    ).reset_index()
    canon["rank_basis"] = "TG-EAPCET State Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== TG sanity (govt scope, GEN/Boys, hardest 10) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "OC_BOYS")
    ].sort_values("closing_rank").head(10)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
