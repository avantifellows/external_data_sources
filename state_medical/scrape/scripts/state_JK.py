"""
Jammu & Kashmir NEET UG 2025 — state govt closing ranks pipeline.

Authority: J&K Board of Professional Entrance Examinations (BOPEE).
           https://www.jkbopee.gov.in
Source PDF: JK_R3_2025.pdf — Provisional Selection List 3rd Round (25-Oct-2025)
URL: https://www.jkbopee.gov.in/Pdf/Downloader.ashx?nid=17239&type=n

Last round used: R3 (last main round before Mop-up; Mop-up excluded).

Schema: SNO | ROLL NO | NAME | GENDER | CAT | S-CAT | UT RANK | DISCIPLINE
        | INSTITUTION | CAT-SLI | U/A DISCIPLINE | U/A INSTITUTION | CAT SLI

Closing-rank metric: UT RANK (J&K state-specific NEET-based rank).

Reservation taxonomy (J&K):
  Vertical: OM (Open Merit) / OBC / EWS / SC / ST (sub-categories ST-i,
            ST1, ST2, STii) / RBA (Resident Backward Areas) / P&B (Poor &
            Backward — only at ASCOMS/private)
  Sub-categories (S-CAT): JKPM (J&K Permanent Migrants), CDP, SP, PWD

Govt-college filter: institution starts with GMC (Govt Medical College),
                     SKIMSMC, or GDC (Govt Dental College). ASCOMS is private.

Result: 9 govt MBBS + 2 govt BDS (matches NMC list 9+2 exactly).

Outputs (to ../extracted_data/):
  - JK_R3_allotments_2025.csv               — raw 585 rows
  - JK_closing_ranks_state_govt_2025.csv    — long format
  - JK_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "JK"
OUT = ROOT / "extracted_data"
STATE_CODE = "JK"
PDF_FILE = SOURCE / "JK_R3_2025.pdf"

VERTICAL_ORDER = ["OM", "OBC", "EWS", "SC", "ST", "RBA"]


def parse_jk_pdf(path: Path) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 9:
                        continue
                    sno = str(r[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    rec = {
                        "sno": int(sno),
                        "roll": str(r[1] or "").strip(),
                        "name": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                        "gender": str(r[3] or "").strip(),
                        "cat": str(r[4] or "").strip(),
                        "s_cat": str(r[5] or "").strip(),
                        "ut_rank": str(r[6] or "").strip().replace(",", ""),
                        "discipline": str(r[7] or "").strip(),
                        "institution": re.sub(r"\s+", " ", str(r[8] or "")).strip(),
                        "cat_sli": str(r[9] or "").strip() if len(r) > 9 else "",
                    }
                    try:
                        rec["ut_rank"] = int(rec["ut_rank"])
                    except ValueError:
                        continue
                    rows.append(rec)
    return pd.DataFrame(rows)


def is_govt(name: str) -> bool:
    n = str(name).upper().strip()
    return n.startswith("GMC") or n.startswith("SKIMSMC") or n.startswith("GDC")


def collapse_st(c: str) -> str:
    c = str(c).strip()
    if c.startswith("ST"):
        return "ST"
    return c


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Stage 1 — parsing {PDF_FILE.name}...")
    df = parse_jk_pdf(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_R3_allotments_2025.csv", index=False)
    print(f"  Total: {len(df)}, institutions: {df['institution'].nunique()}")

    print("\nStage 2 — filtering to govt + MBBS/BDS + plain (no sub-pool)...")
    gov = df[df["institution"].apply(is_govt)].copy()
    gov = gov[gov["discipline"].isin(["MBBS", "BDS"])].copy()
    gov["vert"] = gov["cat"].apply(collapse_st)
    plain = gov[gov["s_cat"].fillna("").astype(str).isin(["", "nan"])].copy()
    print(f"  Govt: {len(gov)}, plain: {len(plain)}")

    print("\nStage 3 — closing ranks per (institution, discipline, vert)...")
    cr = (
        plain.groupby(["institution", "discipline", "vert"])["ut_rank"]
        .agg(closing_UT_rank="max", opening_UT_rank="min", allotted_count="count")
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 4 — wide pivot...")
    piv = cr.pivot_table(
        index=["institution", "discipline"], columns="vert",
        values="closing_UT_rank", aggfunc="first",
    ).reset_index()
    present = [c for c in VERTICAL_ORDER if c in piv.columns]
    piv = piv[["institution", "discipline"] + present]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print(f"\n=== Top 5 J&K govt MBBS by OM closing UT rank ===")
    print(piv[piv["discipline"] == "MBBS"]
          .sort_values("OM", na_position="last").head(5).to_string(index=False))


if __name__ == "__main__":
    main()
