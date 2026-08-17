"""
Parse the MCC NEET UG 2025 Round 1 Provisional Allotment Result PDF
into per-(institute, course, quota, category) closing ranks.

Source: ../source/r1_provisional.pdf
        Downloaded from
        https://cdnbbsr.s3waas.gov.in/s3e0f7a4d0ef9b84b83b693bbf3feb8e6e/uploads/2025/08/202508121942915214.pdf
        (Aug 12, 2025 — Round 1 Provisional Result)

Why R1 alone (not R3 final)?
  - R1 Provisional has explicit Allotted Category column.
  - The R3 cumulative file (admitted_upto_r3.pdf) only carries quota,
    not category — it would need the per-round PDFs (R1, R2, R3) joined
    on roll number to recover category for R2/R3 movers.
  - R1 closing ranks are conservative ("rank you need to confidently
    secure this seat in R1"); final-round closing tends to be 5-15%
    worse for popular colleges, more for less popular ones.
  - Stray / Special-Stray rounds are excluded (fill ~1,100 leftover
    seats at much lower ranks; not a meaningful target).

Outputs (to ../extracted_data/):
  - r1_allotments.csv                              — raw 26,607 R1 allotments
  - closing_ranks_aiq_r1_2025.csv                  — long format, all quotas
  - govt_medical_closing_ranks_r1_2025.csv         — long format, govt only
  - govt_medical_closing_ranks_r1_2025_pivot.csv   — wide format with
                                                      Open/EWS/OBC/SC/ST cols
"""
import pdfplumber
import pandas as pd
import re
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
PDF = ROOT / "source" / "r1_provisional.pdf"
OUT_DIR = ROOT / "extracted_data"

# Govt-flavoured quotas (drop Deemed/NRI/Minority/Foreign)
GOVT_QUOTAS = {
    "All India",                          # 15% AIQ at state govt colleges
    "Open Seat Quota",                    # central institutes (AIIMS / JIPMER)
    "Employees State Insurance Scheme(ESI)",
    "Delhi University Quota",
    "IP University Quota",
    "Aligarh Muslim University (AMU) Quota",
    "Internal - Puducherry UT Domicile",
    "Jamia Internal Quota",
    "Delhi NCR Children/Widows of Personnel of the Armed Forces (CW) DU Quota",
    "Delhi NCR Children/Widows of Personnel of the Armed Forces (CW) IP Quota",
}


def parse_r1_pdf(pdf_path: Path) -> pd.DataFrame:
    """Extract all R1 allotment rows.

    Schema (per row):
      SNo, Rank, Allotted Quota, Allotted Institute, Course,
      Allotted Category, Candidate Category, Remarks
    """
    out = []
    t0 = time.time()
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
        print(f"  Parsing {n} pages...", flush=True)
        for i, page in enumerate(pdf.pages):
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 8:
                        continue
                    sno = str(r[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    rank = str(r[1] or "").strip()
                    if not rank.isdigit():
                        continue
                    out.append({
                        "sno": int(sno),
                        "rank": int(rank),
                        "quota": re.sub(r"\s+", " ", str(r[2] or "")).strip(),
                        "institute_full": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "course": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "alloted_category": re.sub(r"\s+", " ", str(r[5] or "")).strip(),
                        "candidate_category": re.sub(r"\s+", " ", str(r[6] or "")).strip(),
                        "remarks": re.sub(r"\s+", " ", str(r[7] or "")).strip(),
                    })
            if (i + 1) % 200 == 0:
                print(f"    {i+1}/{n} pages, {len(out):,} rows, {time.time()-t0:.0f}s",
                      flush=True)
    return pd.DataFrame(out)


def clean_institute_name(s: str) -> str:
    """Strip address tail from MCC's institute_full string.

    Format: "Name, City, address blob, State, PIN" — the address blob
    can contain multiple commas. Strategy: drop trailing PIN (6 digits)
    and trailing state name (alphabetic, ≤30 chars), then take first
    2 comma-separated parts.
    """
    parts = [p.strip() for p in str(s).split(",")]
    while parts and re.match(r"^\d{6}$", parts[-1]):
        parts.pop()
    if parts and re.match(r"^[A-Za-z][A-Za-z &().-]{0,30}$", parts[-1]):
        parts.pop()
    return ", ".join(parts[:2]) if len(parts) >= 2 else (parts[0] if parts else "")


def tag_institute_type(name: str) -> str:
    """Classify institute into central / central-univ / state-govt buckets."""
    n = name.lower()
    if "aiims" in n: return "Central-AIIMS"
    if "jipmer" in n: return "Central-JIPMER"
    if "esic" in n or "employee" in n or "state insurance" in n:
        return "Central-ESIC"
    if "armed forces" in n or "afmc" in n: return "Central-AFMC"
    if "aligarh muslim" in n: return "Central-Univ-AMU"
    if "jamia" in n: return "Central-Univ-Jamia"
    if "banaras hindu" in n or "bhu" in n: return "Central-Univ-BHU"
    if any(k in n for k in ["lady hardinge", "maulana azad",
                             "university college of medical", "ucms",
                             "vmmc", "safdarjung", "rml", "abvims", "ndmc"]):
        return "Central-Univ-DU/Delhi"
    if "ipu" in n or "ip university" in n or "school of medical sciences" in n:
        return "Central-Univ-IP"
    return "State-Govt"


def main():
    print(f"Parsing {PDF.name}...")
    r1 = parse_r1_pdf(PDF)
    print(f"  Done: {len(r1):,} R1 allotments")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    r1.to_csv(OUT_DIR / "r1_allotments.csv", index=False)

    # Clean institute names
    r1["institute"] = r1["institute_full"].apply(clean_institute_name)

    # Closing rank table (long format, ALL quotas)
    cr = (
        r1.groupby(["institute", "course", "quota", "alloted_category"])
        .agg(
            closing_rank=("rank", "max"),
            opening_rank=("rank", "min"),
            allotted_count=("rank", "count"),
        )
        .reset_index()
        .sort_values(["institute", "course", "quota", "alloted_category"])
    )
    cr.to_csv(OUT_DIR / "closing_ranks_aiq_r1_2025.csv", index=False)
    print(f"  Wrote closing_ranks_aiq_r1_2025.csv: {len(cr):,} rows")

    # Govt-only filter (MBBS+BDS, govt-flavoured quotas)
    cr_gov = cr[
        cr["course"].isin(["MBBS", "BDS"])
        & cr["quota"].isin(GOVT_QUOTAS)
    ].copy()
    cr_gov["institute_type"] = cr_gov["institute"].apply(tag_institute_type)
    cr_gov["is_pwd"] = cr_gov["alloted_category"].str.endswith("PwD")
    cr_gov["category"] = cr_gov["alloted_category"].str.replace(" PwD", "", regex=False)

    cr_gov_out = cr_gov[
        ["institute_type", "institute", "course", "quota", "category",
         "is_pwd", "closing_rank", "opening_rank", "allotted_count"]
    ].sort_values(
        ["institute_type", "institute", "course", "quota", "category", "is_pwd"]
    )
    cr_gov_out.to_csv(
        OUT_DIR / "govt_medical_closing_ranks_r1_2025.csv", index=False
    )
    print(f"  Wrote govt_medical_closing_ranks_r1_2025.csv: {len(cr_gov_out):,} rows")

    # Wide pivot (non-PwD only — Open/EWS/OBC/SC/ST as columns)
    nonpwd = cr_gov_out[~cr_gov_out["is_pwd"]]
    piv = nonpwd.pivot_table(
        index=["institute_type", "institute", "course", "quota"],
        columns="category", values="closing_rank", aggfunc="first",
    ).reset_index()
    cats = ["Open", "EWS", "OBC", "SC", "ST"]
    ordered = ["institute_type", "institute", "course", "quota"] + [
        c for c in cats if c in piv.columns
    ]
    piv = piv[ordered]
    piv.to_csv(
        OUT_DIR / "govt_medical_closing_ranks_r1_2025_pivot.csv", index=False
    )
    print(f"  Wrote govt_medical_closing_ranks_r1_2025_pivot.csv: {len(piv):,} rows")


if __name__ == "__main__":
    main()
