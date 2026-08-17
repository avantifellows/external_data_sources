"""
Uttarakhand NEET UG 2025 — state govt closing ranks pipeline.

Authority: Hemwati Nandan Bahuguna Uttarakhand Medical Education University
           (HNBUMU). https://hnbumu.ac.in
Counselling portal (third-party meta-secure):
           https://meta-secure.com/HNBUMU_NEETUG

Source PDF: UK_R3_broadsheet_2025.pdf
URL: https://meta-secure.com/HNBUMUCollegLogin/UploadDocs/UG2025SeatAllocationRound3.pdf
     ("PROVISIONAL BROADSHEET (ROUND-3) for NEET UG 2025", 299 pages)

Last round used: Round 3 (last main round; Round 5/Stray excluded).
                 R3 broadsheet shows current-round allotments only —
                 R1/R2 stickers (people retained) appear with empty
                 current allotment and only previous-round info, which
                 the table extraction doesn't reliably capture.
                 → Captures ~196 govt-state-quota rows; closing ranks
                 represent R3 fresh allotments + upgrades primarily.

Schema (26 cols): UK State Rank | Name | Sex | Rollno | NEET Marks
                  | NEET Percentile | NEET AIR | Domicile UK | 10th | 12th
                  | PCB% | NEET Cat | UK Cat Claimed | UK Subcat | WKM | PwD
                  | Prev Allotted Cat | Prev Allotted College | Prev Quota
                  | Opted Prefs | Opted College
                  | Allotted Quota | Allotted Cat | Allotted College
                  | Pref# | Remark

Govt-college filter: name contains "GOVT" / "GOVERNMENT" / "SOBAN" / "VEER CHANDRA".
Result: 5 govt MBBS (Doon, Haldwani, Haridwar, SSJ Almora, VCSGGMC Srinagar
        Garhwal). UK has no govt BDS in NMC list.

Reservation taxonomy (UK):
  Vertical: UR / OBC (NCL Central List) / EWS / SC / ST
  Sub-pools (in allotted_cat parens): OPEN (boys), WOMEN (girls 30%),
            DPW, FF (Freedom Fighter), ORPHAN, PWD

Outputs (to ../extracted_data/):
  - UK_all_allotments_2025.csv             — raw rows with current+prev fallback
  - UK_closing_ranks_state_govt_2025.csv   — long format
  - UK_closing_ranks_state_govt_2025_pivot_M.csv — wide (boys)
  - UK_closing_ranks_state_govt_2025_pivot_F.csv — wide (girls)
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "UK"
OUT = ROOT / "extracted_data"
STATE_CODE = "UK"
PDF_FILE = SOURCE / "UK_R3_broadsheet_2025.pdf"

VERTICAL_ORDER = ["UR", "OBC", "EWS", "SC", "ST"]


def parse_uk_pdf(path: Path) -> pd.DataFrame:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 18:
                        continue
                    sr = str(r[0] or "").strip()
                    if not sr.isdigit():
                        continue
                    neet_air = str(r[6] or "").strip().replace(",", "")
                    if not neet_air.isdigit():
                        continue
                    prev_cat = re.sub(r"\s+", " ", str(r[16] or "")).strip()
                    prev_college = re.sub(r"\s+", " ", str(r[17] or "")).strip()
                    prev_quota = re.sub(r"\s+", " ", str(r[18] or "")).strip()
                    cur_quota = (
                        re.sub(r"\s+", " ", str(r[21] or "")).strip()
                        if len(r) > 21 else ""
                    )
                    cur_cat = (
                        re.sub(r"\s+", " ", str(r[22] or "")).strip()
                        if len(r) > 22 else ""
                    )
                    cur_college = (
                        re.sub(r"\s+", " ", str(r[23] or "")).strip()
                        if len(r) > 23 else ""
                    )
                    final_cat = cur_cat or prev_cat
                    final_college = cur_college or prev_college
                    final_quota = cur_quota or prev_quota
                    if not final_college:
                        continue
                    rows.append({
                        "uk_rank": int(sr),
                        "name": re.sub(r"\s+", " ", str(r[1] or "")).strip(),
                        "sex": str(r[2] or "").strip(),
                        "neet_air": int(neet_air),
                        "allotted_cat": final_cat,
                        "allotted_college": final_college,
                        "allotted_quota": final_quota,
                        "source": "cur" if cur_cat else "prev",
                    })
    return pd.DataFrame(rows)


def is_govt(name: str) -> bool:
    n = str(name).upper()
    return any(k in n for k in ["GOVT", "GOVERNMENT", "SOBAN", "VEER CHANDRA"])


def decompose_cat(c: str):
    c = str(c).strip()
    vert = ""
    for v in ["UR", "OBC", "SC", "ST", "EWS"]:
        if c.startswith(v) or f"{v}(" in c[:6]:
            vert = v
            break
    if not vert:
        return ("", "")
    sub = "M"
    if "WOMEN" in c:
        sub = "F"
    elif "OPEN" in c:
        sub = "M"
    else:
        sub = "OTHER"
    return vert, sub


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print(f"Stage 1 — parsing {PDF_FILE.name} (~1 min for 299 pages)...")
    df = parse_uk_pdf(PDF_FILE)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df)}")

    print("\nStage 2 — filtering to STATE QUOTA at govt colleges...")
    state = df[df["allotted_quota"] == "STATE QUOTA SEATS"].copy()
    gov = state[state["allotted_college"].apply(is_govt)].copy()
    deco = gov["allotted_cat"].apply(lambda c: pd.Series(decompose_cat(c)))
    deco.columns = ["vert", "sub"]
    gov = pd.concat([gov.reset_index(drop=True), deco], axis=1)
    plain = gov[gov["sub"].isin(["M", "F"])].copy()
    plain["program"] = plain["allotted_college"].apply(
        lambda c: "BDS" if "Dental" in str(c) else "MBBS"
    )
    print(f"  Govt: {len(gov)} rows, plain: {len(plain)}")

    print("\nStage 3 — closing ranks per (college, program, vert, sub)...")
    cr = (
        plain.groupby(["allotted_college", "program", "vert", "sub"])["neet_air"]
        .agg(closing_AIR="max", opening_AIR="min", allotted_count="count")
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 4 — wide pivots (M / F)...")
    for gender in ("M", "F"):
        sub = cr[cr["sub"] == gender]
        piv = sub.pivot_table(
            index=["allotted_college", "program"], columns="vert",
            values="closing_AIR", aggfunc="first",
        ).reset_index()
        piv = piv[["allotted_college", "program"]
                  + [c for c in VERTICAL_ORDER if c in piv.columns]]
        piv.to_csv(
            OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_{gender}.csv",
            index=False,
        )
        print(f"  pivot_{gender}: {len(piv)} rows")

    print(f"\n=== UK govt MBBS by UR-Boys closing AIR ===")
    piv_m = pd.read_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_M.csv"
    )
    sort_col = "UR" if "UR" in piv_m.columns else piv_m.columns[2]
    print(piv_m.sort_values(sort_col, na_position="last").to_string(index=False))


if __name__ == "__main__":
    main()
