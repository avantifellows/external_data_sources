"""
Andhra Pradesh AP-EAPCET (formerly AP EAMCET) — engineering closing-ranks pipeline.

Authority:  APSCHE (AP State Council of Higher Education)
            + Convener AP-EAPCET / JNTU Kakinada
Portal:     https://eapcet-sche.aptonline.in/  (rolled into 2026 cycle;
            2025 PDFs no longer at original URLs)
Source:     APSCHE 2022 LASTRANK PDF, the most recent freely downloadable
            consolidated cutoff PDF for AP. Used as proxy for 2025 — same
            precedent as KCET (2024 → 2025) and Rajasthan medical (2024 → 2025).

Notes:
  - AP-EAPCET 2024 last-rank PDF was published on the APSCHE portal but the
    URL `apsche.ap.gov.in/Pdf/APEAMCET2024LASTRANKDETAILS.pdf` returns 404 today.
    APSCHE typically re-publishes prior-year reference data when the new
    counselling starts (Apr-May). Re-attempt that URL when 2026 counselling
    opens to upgrade the proxy from 2022 → 2024.
  - 2022 data is older but structurally identical to subsequent years.

PDF format:
  31 columns per (college, branch) row:
    SNO | inst_code | inst_name | type (PVT/GOVT/UNIV) | INST_REG (AU/SVU/JNTUK) |
    DIST | PLACE | COED | AFFLIA.UNIV | ESTD | branch_code | Local_Area |
    OC_BOYS | OC_GIRLS | SC_BOYS | SC_GIRLS | ST_BOYS | ST_GIRLS |
    BCA_BOYS | BCA_GIRLS | BCB_BOYS | BCB_GIRLS | BCC_BOYS | BCC_GIRLS |
    BCD_BOYS | BCD_GIRLS | BCE_BOYS | BCE_GIRLS | OC_EWS_BOYS | OC_EWS_GIRLS |
    COLLFEE

Reservation taxonomy (Andhra Pradesh):
  Vertical (caste): OC / BC-A 7% / BC-B 10% / BC-C 1% / BC-D 7% / BC-E 4% /
                    SC 15% / ST 6% / EWS 10% within OC
  Horizontal: BOYS / GIRLS (33% women's reservation)
  Local-area sub-pools (NOT in the consolidated last-rank PDF):
    AU = Andhra University region
    SVU = Sri Venkateswara University region
    OU* = Osmania (mostly went to TG post-bifurcation)
    APUR = Universal/non-local (85%)
    APNL/APSL = AP North/South non-local fallback
  The consolidated PDF uses AU/SVU as the "INST_REG" column (institute's
  university affiliation region), not the candidate's local area pool.

For canonical 5-cat mapping (NCST schema):
  OC                                   → GEN
  BC-A, BC-B, BC-C, BC-D, BC-E         → OBC-NCL (AP's BC sub-list)
  SC                                   → SC
  ST                                   → ST
  OC_EWS                               → EWS

For Avanti JNV AP student:
  - JNV is Central govt school — no "govt school student" horizontal in AP.
  - Compete in regular OC/BC*/SC/ST/EWS per caste category.

Output (to extracted_data/):
  - AP_engg_all_cutoffs_2022.csv          — long format, every cell
  - AP_engg_closing_ranks_govt_2022.csv   — govt scope
  - AP_engg_consolidated_5cat_govt_2022.csv  — schema-canonical
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "AP" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "AP"
DATA_YEAR = 2022  # most recent freely-downloadable AP last-rank PDF
CET_NAME = "AP-EAMCET"   # rebranded AP-EAPCET 2024+; 2022 data uses old name
SOURCE_URL = "https://apsche.ap.gov.in/Pdf/APEAMCET2022LASTRANKDETAILS.pdf"

PHASE_FILE = "AP_EAMCET_2022_LastRankDetails.pdf"

# Cell columns (col_idx, raw_label, canonical_cat, gender)
CELL_COLUMNS = [
    (12, "OC_BOYS",       "GEN",      "Boys"),
    (13, "OC_GIRLS",      "GEN",      "Girls"),
    (14, "SC_BOYS",       "SC",       "Boys"),
    (15, "SC_GIRLS",      "SC",       "Girls"),
    (16, "ST_BOYS",       "ST",       "Boys"),
    (17, "ST_GIRLS",      "ST",       "Girls"),
    (18, "BCA_BOYS",      "OBC-NCL",  "Boys"),
    (19, "BCA_GIRLS",     "OBC-NCL",  "Girls"),
    (20, "BCB_BOYS",      "OBC-NCL",  "Boys"),
    (21, "BCB_GIRLS",     "OBC-NCL",  "Girls"),
    (22, "BCC_BOYS",      "OBC-NCL",  "Boys"),
    (23, "BCC_GIRLS",     "OBC-NCL",  "Girls"),
    (24, "BCD_BOYS",      "OBC-NCL",  "Boys"),
    (25, "BCD_GIRLS",     "OBC-NCL",  "Girls"),
    (26, "BCE_BOYS",      "OBC-NCL",  "Boys"),
    (27, "BCE_GIRLS",     "OBC-NCL",  "Girls"),
    (28, "OC_EWS_BOYS",   "EWS",      "Boys"),
    (29, "OC_EWS_GIRLS",  "EWS",      "Girls"),
]


def parse_ap_pdf(pdf_path: Path) -> list[dict]:
    rows: list[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables() or []
            for tbl in tables:
                for r in tbl:
                    if not r or len(r) < 30:
                        continue
                    sno = (r[0] or "").strip()
                    if not sno or not sno.replace(",", "").isdigit():
                        continue
                    inst_code = (r[1] or "").strip()
                    if not inst_code:
                        continue
                    inst_name = (r[2] or "").strip()
                    coll_type_raw = (r[3] or "").strip().upper()  # PVT/GOVT/UNIV
                    inst_reg = (r[4] or "").strip()
                    dist = (r[5] or "").strip()
                    place = (r[6] or "").strip()
                    coed = (r[7] or "").strip()
                    affil_univ = (r[8] or "").strip()
                    estd = (r[9] or "").strip()
                    branch_code = (r[10] or "").strip()
                    local_area = (r[11] or "").strip()
                    coll_fee = (r[30] or "").strip() if len(r) > 30 else ""

                    if not branch_code:
                        continue

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
                            "college_code": inst_code,
                            "college_name": inst_name,
                            "college_type_raw": coll_type_raw,
                            "inst_region": inst_reg,
                            "dist": dist,
                            "place": place,
                            "coed": coed,
                            "affil_univ": affil_univ,
                            "estd": estd,
                            "branch_code": branch_code,
                            "local_area": local_area,
                            "category_raw": raw_lbl,
                            "category": cat,
                            "gender": gender,
                            "closing_rank": rank,
                            "college_fee": coll_fee,
                        })
    return rows


# State public universities in AP — only these count as State-Univ-Dept
AP_STATE_UNIVS = [
    "JNTUK",        # JNTU Kakinada
    "JNTUA",        # JNTU Anantapur
    "JNTUGV",       # JNTU GV (Gurajada Vizianagaram)
    "JNTUP",        # JNTU Pulivendula
    "JNTU PULI",    # JNTU Pulivendula
    "A U COLLEGE",  # Andhra University
    "ANDHRA UNIVERSITY",
    "S V U COLLEGE",  # Sri Venkateswara University
    "SVU COLLEGE",
    "S V UNIVERSITY",
    "YOGI VEMANA",
    "RGUKT",        # Rajiv Gandhi University of Knowledge Technologies (govt)
    "ADIKAVI NANNAYA",
    "DRAVIDIAN UNIVERSITY",
    "PADMAVATHI",   # Sri Padmavathi Mahila Vishwavidyalayam (women's, govt)
    "ACHARYA NAGARJUNA",
    "KRISHNA UNIVERSITY",
    "VIKRAMA SIMHAPURI",
]

# Private deemed-universities masquerading as UNIV in AP type col
AP_PRIVATE_DEEMED = [
    "VIT-AP", "VIT AP",
    "SRM UNIVERSITY AP", "SRM AP",
    "MOHAN BABU UNIVERSITY",
    "K L UNIVERSITY", "KLU", "KL UNIVERSITY",
    "VIGNAN", "VIGNANS",
    "GITAM",
    "AMITY UNIVERSITY",
    "CENTURION",
]


def classify_ap_college(coll_type_raw: str, college_name: str) -> str:
    name_upper = college_name.upper()
    t = coll_type_raw.strip().upper()

    # Private deemed first (overrides UNIV type)
    if any(p in name_upper for p in AP_PRIVATE_DEEMED):
        return "Private/Deemed"

    if t == "GOVT":
        return "Govt"
    if t == "UNIV":
        # State public university → keep; otherwise private deemed
        if any(p in name_upper for p in AP_STATE_UNIVS):
            return "State-Univ-Dept"
        return "Private/Deemed"
    if t == "PVT":
        return "Private/SF"
    # Heuristic fallback by name
    if "GOVERNMENT" in name_upper or "GOVT" in name_upper:
        return "Govt"
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse AP last-rank PDF")
    path = SOURCE / PHASE_FILE
    if not path.exists():
        print(f"  ✗ {PHASE_FILE} missing in {SOURCE}")
        return
    rows = parse_ap_pdf(path)
    print(f"  Total cell rows: {len(rows):,}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_cutoffs_{DATA_YEAR}.csv", index=False)
    print(f"  Distinct colleges: {df['college_code'].nunique()}")
    print(f"  Distinct (college × branch): "
          f"{df.groupby(['college_code','branch_code']).ngroups}")

    print("\nStage 2 — classify govt scope")
    df["college_type"] = df.apply(
        lambda r: classify_ap_college(r["college_type_raw"], r["college_name"]),
        axis=1,
    )
    print("  by college_type:")
    for t, n in (df.groupby(["college_code","college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = df[df["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_code'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    govt["state"] = "ANDHRA PRADESH"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "Final last-rank (post-counselling 2022)"
    govt["quota"] = "State (AP domicile)"
    govt["rank_basis"] = "AP-EAMCET State Rank"
    govt["source_url"] = SOURCE_URL

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code",
        "quota", "category_raw", "category", "gender",
        "closing_rank",
        "rank_basis", "source_url",
    ]].sort_values(["college_code", "branch_code", "category_raw", "gender"])
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    # 5-cat consolidated
    print("\nStage 3 — schema-canonical 5-cat consolidated")
    govt["branch_name"] = govt["branch_code"]  # branch_code in AP IS the short name
    canon = govt.groupby(
        ["state", "cet_name", "stream", "year", "round",
         "college_code", "college_name", "college_type",
         "branch_code", "branch_name",
         "quota", "category", "gender"],
        dropna=False,
    ).agg(
        opening_rank=("closing_rank", "min"),
        closing_rank=("closing_rank", "max"),
    ).reset_index()
    canon["last_round_with_max"] = "Final"
    canon["rank_basis"] = "AP-EAMCET State Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    # Sanity check
    print("\n=== AP sanity (govt scope, OC/Boys, hardest 10) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "OC_BOYS")
    ].sort_values("closing_rank").head(10)
    if not sample.empty:
        print(sample[["college_name", "branch_code", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
