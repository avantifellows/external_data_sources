"""
Kerala NEET UG 2025 — state govt closing ranks pipeline.

Authority: Commissioner for Entrance Examinations (CEE), Kerala.
           https://cee.kerala.gov.in
Source: Kerala publishes a clean per-college "Last Rank Table" PDF after
        each phase. Phase 3 (Final) used.

URL: https://cee.kerala.gov.in/keam2025/list/lastrank/mbbs_lrank_p3_final2.pdf

Last round used: Phase 3 (Final, dated 03-Nov-2025). Stray Vacancy round
                 excluded per project pattern.

Schema: Per-college row with closing rank for each category column.
  - Code (3-letter), Name, Type (G=Govt / S=Self-financing/Private)
  - Categories: SM (State Merit/Open) / EZ (Ezhava) / MU (Muslim) /
    BH (Backward Hindu — OBH) / LA (Latin Catholic & Anglo Indian) /
    DV (Dheevara) / VK (Viswakarma) / BX (Backward Christian — OBX) /
    KN (Kusavan) / KU / SC / ST / EW (EWS)
  - "Other Categories" column for special quotas (DA Defence, PD PwD,
    PI, SD, XS, HR Hindi-belt, AC Anglo-Christian, AM, NC, NR-Non-Resident,
    MM, NM)

Govt-college filter: Type = "G" — straightforward.
Result: 14 govt MBBS + 6 govt BDS (vs NMC list 12+6 — 2 new MBBS added).

Reservation taxonomy (see state_reservation_taxonomy.csv):
  Vertical: SM 50% / SEBC 30% (sub-split: EZ 9% + MU 8% + OBH 3% + LA 3%
            + DV 2% + VK 2% + KN 1% + BX 1%) / SC 8% / ST 2% / EWS 10%
  Horizontal: PwD 5%, Ex-Servicemen 2%
  Note: Central OBC certificate is NOT valid — Kerala-specific community
        certificates required (e.g., a candidate needs to be specifically
        EZ/MU/OBH etc., not generic OBC-NCL).

For Avanti JNV KL student (typical):
  - JNV is Central govt school. Kerala has no Govt-School horizontal
    quota. Student competes in regular state quota under their KL-specific
    community (most common for JNV: SM if non-reserved, EZ/MU if from
    those communities, SC/ST as applicable).

Closing-rank metric: Kerala publishes "Last Rank" = the worst (highest)
                     KEAM rank of any candidate admitted to that
                     (college, category). Lower = harder.
                     Numbers are KEAM state rank (state-specific NEET-
                     based merit), NOT NEET AIR.

Outputs (to ../extracted_data/):
  - KL_all_colleges_lastrank_2025.csv          — all 35 MBBS + 25 BDS
  - KL_closing_ranks_state_govt_2025.csv       — 20 govt rows
  - KL_closing_ranks_state_govt_2025_pivot.csv — same (already wide)
"""
import pdfplumber
import pandas as pd
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "KL"
OUT = ROOT / "extracted_data"
STATE_CODE = "KL"
PDF_FILE = SOURCE / "KL_lastrank_P3_final.pdf"

CATS = ["SM", "EZ", "MU", "BH", "LA", "DV", "VK", "BX", "KN", "KU",
        "SC", "ST", "EW"]


def parse_kl_pdf(path: Path) -> pd.DataFrame:
    rows = []
    program = "MBBS"
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r:
                        continue
                    if r[0] in ("MBBS", "BDS") and not r[2]:
                        program = r[0]
                        continue
                    if r[0] == "Name of College":
                        continue
                    if not r[0] or not r[2]:
                        continue
                    if len(r) < 16:
                        continue
                    rec = {
                        "program": program,
                        "college_code": str(r[0]).strip(),
                        "college": str(r[1]).replace("\n", " ").strip() if r[1] else "",
                        "type": str(r[2]).strip(),
                    }
                    for i, cat in enumerate(CATS):
                        val = str(r[3 + i]).strip() if r[3 + i] else "-"
                        rec[cat] = (
                            None if val in ("-", "")
                            else int(val) if val.isdigit() else None
                        )
                    rec["other_categories"] = (
                        str(r[16]).replace("\n", " ").strip()
                        if len(r) > 16 and r[16] else ""
                    )
                    rows.append(rec)
    return pd.DataFrame(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Stage 1 — parsing {PDF_FILE.name}...")
    df = parse_kl_pdf(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_all_colleges_lastrank_2025.csv", index=False)
    print(f"  {len(df)} rows ("
          f"{(df.program=='MBBS').sum()} MBBS + {(df.program=='BDS').sum()} BDS)")

    print("\nStage 2 — filtering to Govt colleges (type='G')...")
    gov = df[df["type"] == "G"].copy()
    gov.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    gov.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Govt: {len(gov)} ("
          f"{(gov.program=='MBBS').sum()} MBBS + {(gov.program=='BDS').sum()} BDS)")

    print(f"\n=== Top 5 KL govt MBBS by SM (Open) closing rank ===")
    print(gov[gov["program"] == "MBBS"]
          .sort_values("SM", na_position="last").head(5)
          [["college_code", "college", "SM", "EZ", "MU", "SC", "ST", "EW"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
