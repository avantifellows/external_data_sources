"""
Gujarat ACPC — engineering closing-ranks pipeline.

Authority:  Admission Committee for Professional Courses (ACPC), Gujarat
Portal:     https://gujacpc.admissions.nic.in/eservices-be_b-tech/
Source:     "First Year Degree Engineering 2025-26 — Institute Wise :
            Program Wise : Last Admitted Rank after Round-3" PDF at
            cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/
              uploads/2025/08/2025080255.pdf

Round 3 = LAST main round (Aug 2025); no later round in eservices listing.

PDF format (single tabular structure across 51 pages):
  6 columns:
    Inst_Name | Course_name | Cat_Name | Board | Type_of_Institute | closing

  Two parallel ranks per (institute, course, category):
    - GUJCET Based (state engineering exam rank)
    - JEE Based   (JEE Main rank)
  Each appears as a separate row.

Reservation taxonomy (Gujarat):
  Vertical: GEN / EWS / SC / ST / SEBC (27%, Gujarat OBC label)
  Special: TFWS (Tuition Fee Waiver Scheme — economic, separate column
            with own closing rank since TFWS is a separate sub-pool)
  Horizontal: PH / EX (small categories, present in some sub-pools)

Type_of_Institute classification:
  GIA   = Grant-in-Aid (state-aided autonomous) → Govt-Aided
  GOV   = Government → Govt
  Univ Dept. = State public university tech dept → State-Univ-Dept
  SFI   = Self-Financed → Private/SF

For canonical 5-cat mapping (NCST schema):
  GEN   → GEN
  EWS   → EWS
  SEBC  → OBC-NCL  (Gujarat's OBC label)
  SC    → SC
  ST    → ST
  TFWS  → flagged via sub_pool

For Avanti JNV GJ student:
  - JNV is Central govt school. Gujarat has no horizontal "govt school
    student" reservation. Compete in regular state quota under their
    GJ vertical category.
  - GJ uses the state's own composite formula: GUJCET 1/3 + JEE Main 1/3
    + Class 12 1/3. The published cutoff is the MERIT POSITION among
    Gujarat applicants, computed from this composite (not GUJCET alone).

Output (to extracted_data/):
  - GJ_engg_all_cutoffs_2025.csv         — long format
  - GJ_engg_closing_ranks_govt_2025.csv  — govt scope
  - GJ_engg_consolidated_5cat_govt_2025.csv  — schema-canonical
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "GJ" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "GJ"
DATA_YEAR = 2025
CET_NAME = "ACPC-GUJCET"
SOURCE_URL = ("https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/"
              "uploads/2025/08/2025080255.pdf")
PHASE_FILE = "GJ_ACPC_2025_R3_LastAdmittedRank.pdf"


def parse_gj_pdf(path: Path) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) < 6:
                        continue
                    inst = (r[0] or "").replace("\n", " ").strip()
                    course = (r[1] or "").strip()
                    cat = (r[2] or "").strip()
                    board = (r[3] or "").strip()
                    inst_type = (r[4] or "").replace("\n", " ").strip()
                    closing = (r[5] or "").strip()
                    # Skip header rows
                    if inst in ("", "Inst_Name") or "Admission Committee" in inst:
                        continue
                    if cat in ("", "Cat_Name"):
                        continue
                    try:
                        rank = int(float(closing.replace(",", "")))
                    except (ValueError, AttributeError):
                        continue
                    rows.append({
                        "college_name": inst,
                        "branch_name": course,
                        "category_raw": cat,
                        "board": board,
                        "institute_type_raw": inst_type,
                        "closing_rank": rank,
                    })
    return rows


def classify_gj_college(inst_type_raw: str, name: str) -> str:
    t = inst_type_raw.strip().upper()
    if t == "GOV" or "GOVERNMENT" in name.upper() or "GOVT" in name.upper():
        return "Govt"
    if t == "GIA":
        return "Govt-Aided"
    if t in ("UNIV DEPT.", "UNIV", "UNIV DEPT", "UNIVERSITY DEPT"):
        return "State-Univ-Dept"
    if t == "SFI":
        return "Private/SF"
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def normalise_category(c: str) -> tuple[str, str]:
    c = c.strip().upper()
    if c == "GEN":  return ("GEN", "")
    if c == "EWS":  return ("EWS", "")
    if c == "SEBC": return ("OBC-NCL", "")
    if c == "SC":   return ("SC", "")
    if c == "ST":   return ("ST", "")
    if c == "TFWS": return ("OTHER", "TFWS")
    if c == "PH":   return ("OTHER", "PH")
    if c == "EX":   return ("OTHER", "EX")
    return ("OTHER", c)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse Gujarat ACPC R3 last-rank PDF")
    rows = parse_gj_pdf(SOURCE / PHASE_FILE)
    df = pd.DataFrame(rows)
    print(f"  Total rows: {len(df):,}")
    print(f"  Distinct institutes: {df['college_name'].nunique()}")
    print(f"  Boards: {df['board'].value_counts().to_dict()}")
    print(f"  Institute types: {df['institute_type_raw'].value_counts().to_dict()}")
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_cutoffs_{DATA_YEAR}.csv", index=False)

    print("\nStage 2 — classify govt scope")
    df["college_type"] = df.apply(
        lambda r: classify_gj_college(r["institute_type_raw"], r["college_name"]),
        axis=1,
    )
    print("  by college_type (distinct colleges):")
    for t, n in (df.groupby(["college_name", "college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = df[df["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_name'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    cat_norm = govt["category_raw"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "sub_pool"]
    govt = pd.concat([govt, cat_norm], axis=1)

    govt["state"] = "GUJARAT"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "Round 3 (last main round)"
    govt["quota"] = "State (Gujarat domicile)"
    govt["gender"] = "All"  # GJ doesn't split by gender in this PDF
    govt["college_code"] = govt["college_name"]  # ACPC doesn't expose stable codes here
    govt["rank_basis_per_row"] = govt["board"].apply(
        lambda b: "GUJCET-Based composite (GUJCET 1/3 + JEE Main 1/3 + Class 12 1/3)"
        if "GUJCET" in str(b).upper() else "JEE Main rank"
    )

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type", "institute_type_raw",
        "branch_name", "board",
        "quota", "category_raw", "category", "sub_pool", "gender",
        "closing_rank", "rank_basis_per_row",
    ]].sort_values(["college_name", "branch_name", "board", "category_raw"])
    govt_out["source_url"] = SOURCE_URL
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    # 5-cat consolidated — use GUJCET-based ranks (state merit) as the headline
    print("\nStage 3 — schema-canonical 5-cat consolidated (GUJCET-based ranks)")
    canon = govt_out[
        (govt_out["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"]))
        & (govt_out["board"] == "GUJCET Based")
    ].copy()
    canon["branch_code"] = canon["branch_name"]
    canon = canon.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(
        opening_rank=("closing_rank", "min"),
        closing_rank=("closing_rank", "max"),
    ).reset_index()
    canon["last_round_with_max"] = "R3"
    canon["rank_basis"] = "Gujarat State Merit Rank (GUJCET 1/3 + JEE 1/3 + Cl12 1/3)"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== GJ sanity (govt scope, GEN + GUJCET-based, hardest 12) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "GEN")
        & (govt_out["board"] == "GUJCET Based")
    ].sort_values("closing_rank").head(12)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
