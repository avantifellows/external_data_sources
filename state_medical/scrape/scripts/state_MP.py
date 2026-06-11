"""
Madhya Pradesh NEET UG 2025 — state govt closing ranks pipeline.

Authority: Directorate of Medical Education (DME), MP. https://dme.mponline.gov.in
Source: MP DME publishes a clean per-(institute, category) opening/closing
        AIR PDF directly after each round. Round 2 (22-Sep-2025) used
        as the latest available with allotment data; Mop-up file from
        16-Oct-2025 contains only schedule, no allotment data.

Last round used: Round 2 (22-Sep-2025). Mop-up round happened later but
                 only the time schedule PDF is published; college-wise
                 allotment opening/closing PDF for Mop-up not on the
                 portal as of pull date.

Source PDF: MP_R2_OpenClose_2025.pdf
URL: https://dme.mponline.gov.in/ql_dme/DMECounselling_Public/DMEUG/2025/Display%20Second%20Round%20Allotment%20Opening%20Closing%202025_DME_UG_SR_REPORT_65.pdf

Schema:
  INST_CODE | INST_TYPE (GOVT/Private) | INST_NAME | COURSE
            | OPENING AI RANK | CLOSING AI RANK
            | OPENING NEET AI SCORE | CLOSING NEET AI SCORE
            | ALLOTTED CATEGORY/CLASS (e.g., 'UR/X/OP', 'OBC/PH/OP')
            | TOTAL ALLOTTED | MP DOMICILE STATUS

Allotted Category format: <vert>/<horiz>/<sub>
  Vertical: UR / OBC / SC / ST / EWS
  Horizontal:
    X  = no horizontal modifier (the headline)
    PH = PwD (5%)
    GS = Govt Servant child (10%) — MP-specific
    SN = ?
    FF = Freedom Fighter dependents (3%)
  Sub: OP = Open (vs other internal sub-quotas)

For Avanti JNV MP student: most likely UR/X/OP, OBC/X/OP, SC/X/OP, ST/X/OP
                           or EWS/X/OP. JNV is Central govt school —
                           wouldn't qualify for "GS" (Govt Servant child)
                           which is specific to MP state govt employees.

Govt-college filter: INST_TYPE = "GOVT"
Result: 19 govt MBBS + 1 govt BDS (NMC list says ~15 MBBS + 1 BDS — extras
        include new GMCs added in 2024-25)

Reservation taxonomy (see state_reservation_taxonomy.csv):
  Vertical: UR / OBC 14% / SC 16% / ST 20% / EWS 10%
  Horizontal: PwD 5%, Govt-Servant child 10% (MP-specific), Freedom Fighter,
              Sports

Outputs (to ../extracted_data/):
  - MP_all_allotments_2025.csv                  — all 392 rows incl private
  - MP_closing_ranks_state_govt_2025.csv        — 99 plain (X/OP) govt rows
  - MP_closing_ranks_state_govt_2025_pivot.csv  — wide pivot
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "MP"
OUT = ROOT / "extracted_data"
STATE_CODE = "MP"
PDF_FILE = SOURCE / "MP_R2_OpenClose_2025.pdf"

VERTICAL_ORDER = ["UR", "OBC", "EWS", "SC", "ST"]


def parse_mp_pdf(path: Path) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 11:
                        continue
                    code = str(r[0] or "").strip()
                    if not code.isdigit():
                        continue
                    rows.append({
                        "inst_code": code,
                        "inst_type": str(r[1] or "").strip(),
                        "inst_name": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                        "course": str(r[3] or "").strip(),
                        "opening_air": str(r[4] or "").strip().replace(",", ""),
                        "closing_air": str(r[5] or "").strip().replace(",", ""),
                        "opening_neet": str(r[6] or "").strip(),
                        "closing_neet": str(r[7] or "").strip(),
                        "allotted_category": re.sub(r"\s+", " ", str(r[8] or "")).strip(),
                        "total_allotted": str(r[9] or "").strip(),
                        "mp_domicile": (
                            str(r[10] or "").strip() if len(r) > 10 else ""
                        ),
                    })
    df = pd.DataFrame(rows)
    for c in ["opening_air", "closing_air", "opening_neet", "closing_neet"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def decompose(c: str):
    parts = str(c).split("/")
    if len(parts) >= 3:
        return parts[0], parts[1], parts[2]
    return c, "", ""


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Stage 1 — parsing {PDF_FILE.name}...")
    df = parse_mp_pdf(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  {len(df)} rows, {df['inst_code'].nunique()} institutes")

    print("\nStage 2 — filtering to GOVT + plain (X/OP)...")
    gov = df[df["inst_type"] == "GOVT"].copy()
    deco = gov["allotted_category"].apply(lambda c: pd.Series(decompose(c)))
    deco.columns = ["vert", "horiz", "sub"]
    gov = pd.concat([gov.reset_index(drop=True), deco], axis=1)
    plain = gov[(gov["horiz"] == "X") & (gov["sub"] == "OP")].copy()
    print(f"  Govt rows: {len(gov)}, plain (X/OP): {len(plain)}")

    plain.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 3 — wide pivot...")
    piv = plain.pivot_table(
        index=["inst_code", "inst_name", "course"], columns="vert",
        values="closing_air", aggfunc="first",
    ).reset_index()
    present = [c for c in VERTICAL_ORDER if c in piv.columns]
    piv = piv[["inst_code", "inst_name", "course"] + present]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows ("
          f"{(piv['course']=='MBBS').sum()} MBBS + {(piv['course']=='BDS').sum()} BDS)")

    print(f"\n=== Top 5 MP govt MBBS by UR closing AIR ===")
    print(piv[piv["course"] == "MBBS"]
          .sort_values("UR", na_position="last").head(5)
          [["inst_code", "inst_name", "UR", "OBC", "EWS", "SC", "ST"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
