"""
Assam NEET UG 2025 — state govt closing ranks pipeline.

Authority: Directorate of Medical Education, Assam (DME Assam).
           https://dme.assam.gov.in
Counselling stream: Assam State Quota for govt MBBS + BDS colleges.

Source PDFs hosted at dme.assam.gov.in:
  - AS_R1_2025.pdf   (163 pp, dated 03-Sep-2025) — Round 1 provisional
                      allotment for Assam State Quota
  - AS_State_Merit_2025.pdf — Provisional Assam state revised merit list
                              (no college info, kept for reference only)

Last round used: R1 only.
  R2/R3 PDFs not located on the DME Assam portal as of May-2026; the R1
  list contains the bulk of allotments at top-rank tier so it remains
  the meaningful headline. To extend, drop later round PDFs in
  source/AS/ and union here.

Schema (R1): Sr.No | Reg.L Sr.No | Roll No. + Rank + Score (merged)
            | DME App.No | Revised State Rank | Name | Category
            | Sub Category | Special Category | Code + Quota + College
            (merged in last col)

PDFplumber returns the 'Selection Details' for row N inside row N+1's
last cell — the parser shifts by one row to recover the right alignment.

Closing-rank metric: NEET AIR (Rank column on the PDF — All India Rank,
                     lower = harder).

Reservation taxonomy (Assam):
  Vertical: UR / EWS / OBC/MOBC(NCL) / SC / ST(P) Plain / ST(H) Hill
  Horizontal: PwD, Sports, Ex-Serviceman, Freedom Fighter
  Sub-pools: KOCH-RAJBO (within OBC), MOBC migrant variants

Categories migrate via "X --> UR" syntax — the parser captures the
final pool (post-migration) so closing ranks reflect the bar a candidate
in that pool actually faced.

Govt-college list (13 MBBS + 3 BDS, codes 101-113 + 201-203):
  101 Assam MC Dibrugarh, 102 Gauhati MC, 103 Silchar MC, 104 Jorhat MC,
  105 Fakhruddin Ali Ahmed MC Barpeta, 106 Tezpur MC, 107 Diphu MC,
  108 Lakhimpur MC, 109 Dhubri MC, 110 Nalbari MC, 111 Nagaon MC,
  112 Kokrajhar MC, 113 Tinsukia MC.
  201 Regional Dental Guwahati, 202 Govt Dental Dibrugarh,
  203 Govt Dental Silchar.

Outputs (to ../extracted_data/):
  - AS_all_allotments_2025.csv             — raw allotted rows
  - AS_closing_ranks_state_govt_2025.csv   — long format
  - AS_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "AS"
OUT = ROOT / "extracted_data"
STATE_CODE = "AS"

R1_PDF = "AS_R1_2025.pdf"

# Inst code → canonical college name + program
INSTITUTE_MAP = {
    "101": ("Assam Medical College, Dibrugarh", "MBBS"),
    "102": ("Gauhati Medical College, Guwahati", "MBBS"),
    "103": ("Silchar Medical College, Silchar", "MBBS"),
    "104": ("Jorhat Medical College, Jorhat", "MBBS"),
    "105": ("Fakhruddin Ali Ahmed Medical College, Barpeta", "MBBS"),
    "106": ("Tezpur Medical College, Tezpur", "MBBS"),
    "107": ("Diphu Medical College, Diphu", "MBBS"),
    "108": ("Lakhimpur Medical College, North Lakhimpur", "MBBS"),
    "109": ("Dhubri Medical College, Dhubri", "MBBS"),
    "110": ("Nalbari Medical College, Nalbari", "MBBS"),
    "111": ("Nagaon Medical College, Nagaon", "MBBS"),
    "112": ("Kokrajhar Medical College, Kokrajhar", "MBBS"),
    "113": ("Tinsukia Medical College, Tinsukia", "MBBS"),
    "201": ("Regional Dental College, Guwahati", "BDS"),
    "202": ("Government Dental College, Dibrugarh", "BDS"),
    "203": ("Government Dental College, Silchar", "BDS"),
}

# Final-pool quotas after any migration
QUOTAS = [
    "UR", "EWS", "OBC/MOBC(NCL)", "SC", "ST(P)", "ST(H)",
    "Ex-Serviceman", "Freedom Fighter", "Sports",
]
MAIN_POOLS = {"UR", "EWS", "OBC/MOBC(NCL)", "SC", "ST(P)", "ST(H)"}
ORDER = ["UR", "OBC/MOBC(NCL)", "EWS", "SC", "ST(P)", "ST(H)"]


def parse_selection(s: str):
    """Parse 'CODE QUOTA[ --> POOL] COLLEGE' → (code, quota, pool)."""
    if not s or s == "NA":
        return None
    s = re.sub(r"\s+", " ", s).strip()
    m = re.match(r"^(\d{3})\s+(.+)$", s)
    if not m:
        return None
    code, rest = m.group(1), m.group(2)
    mig = re.match(r"^(\S+)\s+-->\s+(\S+)\s+(.+)$", rest)
    if mig:
        return code, mig.group(1), mig.group(2)
    for q in sorted(QUOTAS, key=len, reverse=True):
        if rest.startswith(q + " ") or rest == q:
            return code, q, q
    return code, None, None


def parse_pdf(path: Path) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for i, r in enumerate(tbl):
                    if not r or len(r) < 10:
                        continue
                    sno = (r[0] or "").strip()
                    if not sno.isdigit():
                        continue
                    # selection-details for THIS row sits in NEXT row's col 9
                    sel = ""
                    if i + 1 < len(tbl) and len(tbl[i + 1]) > 9:
                        sel = (tbl[i + 1][9] or "").strip()
                    if "Code Quota" in sel:
                        sel = sel.split("\n", 1)[-1] if "\n" in sel else ""
                    col2 = (r[2] or "").strip()
                    m_rrs = re.match(r"(\d{10})\s+(\d+)\s+(\d+)", col2)
                    if not m_rrs:
                        continue
                    parsed = parse_selection(sel)
                    if not parsed:
                        continue
                    code, quota, pool = parsed
                    rows.append({
                        "sno": int(sno),
                        "neet_air": int(m_rrs.group(2)),
                        "neet_score": int(m_rrs.group(3)),
                        "state_rank": (r[4] or "").strip(),
                        "name": re.sub(r"\s+", " ", (r[5] or "").strip()),
                        "category": (r[6] or "").strip(),
                        "sub_category": (r[7] or "").strip(),
                        "special_category": (r[8] or "").strip(),
                        "inst_code": code,
                        "quota_seat": quota,
                        "final_pool": pool,
                    })
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R1 PDF...")
    rows = parse_pdf(SOURCE / R1_PDF)
    df = pd.DataFrame(rows)
    df["college_canon"] = df["inst_code"].map(lambda c: INSTITUTE_MAP.get(c, (c, ""))[0])
    df["program"] = df["inst_code"].map(lambda c: INSTITUTE_MAP.get(c, ("", ""))[1])
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Allotments: {len(df)}, MBBS: {(df.program=='MBBS').sum()}, BDS: {(df.program=='BDS').sum()}")

    print("\nStage 2 — filter to main verticals (UR/OBC/EWS/SC/ST(P)/ST(H))...")
    main = df[df["final_pool"].isin(MAIN_POOLS)].copy()
    print(f"  Main-pool rows: {len(main)}")

    print("\nStage 3 — closing ranks per (college, program, final_pool)...")
    cr = (
        main.groupby(["college_canon", "program", "final_pool"])["neet_air"]
        .agg(closing_rank="max", opening_rank="min", allotted_count="count")
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    print(f"  Long rows: {len(cr)}")

    print("\nStage 4 — wide pivot...")
    piv = cr.pivot_table(
        index=["college_canon", "program"], columns="final_pool",
        values="closing_rank", aggfunc="first",
    ).reset_index()
    piv = piv[["college_canon", "program"] + [c for c in ORDER if c in piv.columns]]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print("\n=== Assam govt by UR closing NEET AIR ===")
    print(piv.sort_values("UR", na_position="last").to_string(index=False))


if __name__ == "__main__":
    main()
