"""
Parse the NMC MBBS Final Seat Matrix PDF (2025-26) into clean CSVs.

Source: ../source/nmc_mbbs_seat_matrix_2025-26_03Dec2025.pdf
        Downloaded from https://www.nmc.org.in/wp-content/uploads/2025/12/UG%20Seat%20Matrix%2003-12-2025.pdf
        This is the final NMC seat matrix used for NEET 2025 counselling
        (issued by UGMEB on 11-Dec-2025, dated 03-Dec-2025).

Outputs (to ../extracted_data/):
  - mbbs_all_colleges_2025-26.csv   — all 819 colleges
  - mbbs_govt_colleges_2025-26.csv  — 455 govt colleges (Govt + Govt-Society)
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # suppress pdfplumber FontBBox warnings

ROOT = Path(__file__).parent.parent
PDF = ROOT / "source" / "nmc_mbbs_seat_matrix_2025-26_03Dec2025.pdf"
OUT_DIR = ROOT / "extracted_data"


def parse_pdf(pdf_path: Path) -> pd.DataFrame:
    """Extract all rows from the NMC seat-matrix PDF using pdfplumber tables."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                rows.extend(table)

    # Keep only rows where col 0 is a valid S.No. (1-1500)
    def is_sno(x):
        if x is None:
            return False
        s = str(x).strip()
        return s.isdigit() and 1 <= int(s) <= 1500

    clean = []
    for r in rows:
        r = [(c or "").replace("\n", " ").strip() for c in r]
        r = [re.sub(r"\s+", " ", c) for c in r]
        if not is_sno(r[0]) or len(r) < 6:
            continue
        sno, state, name, mgmt, s24, s25 = r[0], r[1], r[2], r[3], r[4], r[5]
        remarks = r[6] if len(r) >= 7 else ""

        def parse_int(x):
            try:
                return int(re.sub(r"[^\d]", "", x)) if x else 0
            except ValueError:
                return 0

        clean.append({
            "sno": int(sno),
            "state": state,
            "college": name,
            "mgmt": mgmt,
            "intake_2024_25": parse_int(s24),
            "intake_2025_26": parse_int(s25),
            "remarks": remarks,
        })
    return pd.DataFrame(clean)


def normalise_management(m: str) -> str:
    """Collapse OCR variants of management types into 4 canonical buckets."""
    m = m.strip()
    if m in {"Govt.", "Govt"}:
        return "Govt"
    if "Govt" in m and "ociety" in m:
        return "Govt-Society"
    if m in {"COMPANY", "TRUST", "SOCIETY"}:  # all-caps OCR variants
        return m.title()
    return m


def main():
    print(f"Parsing {PDF.name}...")
    df = parse_pdf(PDF)
    print(f"  {len(df)} rows extracted")
    print(f"  Total intake 2024-25: {df['intake_2024_25'].sum():,}")
    print(f"  Total intake 2025-26: {df['intake_2025_26'].sum():,}")

    df["mgmt_norm"] = df["mgmt"].apply(normalise_management)

    # Write all-colleges output
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "mbbs_all_colleges_2025-26.csv", index=False)

    # Govt-only slice (Govt + Govt-Society)
    gov = df[df["mgmt_norm"].isin(["Govt", "Govt-Society"])].copy()
    gov = gov[
        ["sno", "state", "college", "mgmt_norm", "intake_2024_25",
         "intake_2025_26", "remarks"]
    ].rename(columns={"mgmt_norm": "mgmt"})
    gov.to_csv(OUT_DIR / "mbbs_govt_colleges_2025-26.csv", index=False)

    print(f"\n=== Govt MBBS 2025-26 ===")
    print(f"  {len(gov)} colleges, {gov['intake_2025_26'].sum():,} seats")
    print(gov.groupby("mgmt").agg(
        colleges=("college", "count"),
        intake=("intake_2025_26", "sum"),
    ))


if __name__ == "__main__":
    main()
