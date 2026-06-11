"""
Uttar Pradesh NEET UG 2025 — state govt closing ranks pipeline.

Authority: Director General of Medical Education & Training (DGMET) UP,
           Lucknow. https://upneet.gov.in
Counselling portal: https://upneet.gov.in/vaccant_result/onallotmainCStatus.aspx
                    (institute-wise allotted candidates list)

Source data: UP_all_allotments_2025_raw.csv
            Scraped via Chrome MCP from the institute-wise allotment page
            (114 institutes × ASP.NET postback per institute).
            14,162 candidate-level allotment rows.

Last round used: cumulative R1+R2+R3. UP also had Stray Vacancy and Special
Stray rounds — excluded per the project pattern (~250 leftover seats at
much lower ranks).

Schema (raw CSV):
  institute_code | institute_name | branch | serial | round | category
                 | rollno | name | father | rank | allot_date
                 | left_inst | left_course

Category coding: 4-letter codes = caste(2) + sub(2):
  Caste: UR (Unreserved/Open) / SC / BC (OBC) / ST / EW (EWS)
  Sub:   OP (Open Boys/default) / GL (Girls)
         PH (PwD) / EX (Ex-Servicemen) / FF (Freedom Fighter) / NC (NCC)
  e.g. UROP = Unreserved Open Boys, SCGL = SC Girls

Govt-college filter:
  - MBBS: name pattern contains AUTONOMOUS STATE MEDICAL / GOVERNMENT
    MEDICAL / GOVERNMENT INSTITUTE / KING GEORGE / BABA RAGHAVDAS /
    DR.RAM MANOHAR LOHIA / GANESH SHANKER / LALA LAJPAT RAI /
    MAHARANI LAXMIBAI / MOTI LAL NEHRU / SAROJINI NAIDU /
    UTTAR PRADESH UNIVERSITY OF MEDICAL / ESIC, OR has [PPP] suffix
    (Public-Private Partnership = govt-society equivalent)
  - BDS: limited govt list — codes 100 (KGMU Faculty of Dental Sciences)
    and 107 (Dental College Azamgarh)
  - Result: 50 govt MBBS + 2 govt BDS (vs NMC list 41 MBBS + 4 BDS;
    UP also includes ESIC + PPP colleges in our scope)

Reservation taxonomy (see state_reservation_taxonomy.csv) — vertical:
  General/UR (~50%) / OBC (27%) / SC (21%) / ST (2%) / EWS (10%);
  horizontal: Women 20% (separate seat type), PwD 5%, Ex-Servicemen 5%,
  Freedom Fighter 2%, NCC small.

For Avanti JNV UP student (typical):
  - JNV is Central govt school. UP doesn't have a horizontal Govt-School
    quota. Student competes in regular state quota under their UP caste
    category (UR/OBC/SC/ST/EWS).
  - Look up: pivot_M.csv (boys) or pivot_F.csv (girls)

Outputs (to ../extracted_data/):
  - UP_all_allotments_2025.csv                  — govt rows only (5,200)
  - UP_closing_ranks_state_govt_2025.csv        — long format (429 rows)
  - UP_closing_ranks_state_govt_2025_pivot_M.csv — wide (boys)
  - UP_closing_ranks_state_govt_2025_pivot_F.csv — wide (girls)

To refresh data:
  Re-run the Chrome MCP scrape against the live institute-wise page
  (https://upneet.gov.in/vaccant_result/onallotmainCStatus.aspx).
  See state_counselling/CLAUDE.md "UP scraping recipe" section.
"""
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "UP"
OUT = ROOT / "extracted_data"
STATE_CODE = "UP"
RAW_CSV = SOURCE / "UP_all_allotments_2025_raw.csv"

GOVT_BDS_CODES = {"100", "107"}
GOVT_MBBS_KEYWORDS = [
    "AUTONOMOUS STATE MEDICAL", "GOVERNMENT MEDICAL", "GOVERNMENT INSTITUTE",
    "KING GEORGE", "BABA RAGHAVDAS",
    "DR.RAM MANOHAR LOHIA", "DR. RAM MANOHAR LOHIA",
    "GANESH SHANKER", "LALA LAJPAT RAI", "MAHARANI LAXMIBAI",
    "MOTI LAL NEHRU", "SAROJINI NAIDU",
    "UTTAR PRADESH UNIVERSITY OF MEDICAL", "ESIC",
]
VERTICAL_ORDER = ["UR", "OBC", "EWS", "SC", "ST"]


def is_govt(row) -> bool:
    if row["branch"] == "BDS":
        return str(row["institute_code"]) in GOVT_BDS_CODES
    n = str(row["institute_name"]).upper()
    return (
        any(k in n for k in GOVT_MBBS_KEYWORDS)
        or "[ PPP]" in n or "[PPP]" in n
    )


def decompose_category(c: str):
    """4-letter UP code → (vertical, gender, sub_type).

    e.g. 'UROP' → ('UR','M','plain'), 'BCGL' → ('OBC','F','plain'),
         'SCPH' → ('SC','','PwD')
    """
    c = str(c)
    if len(c) != 4:
        return ("", "", "")
    caste = c[:2]
    sub = c[2:]
    vert = {"UR": "UR", "SC": "SC", "BC": "OBC", "ST": "ST", "EW": "EWS"}.get(
        caste, caste
    )
    sub_map = {
        "OP": ("M", "plain"), "GL": ("F", "plain"),
        "PH": ("", "PwD"), "EX": ("", "ExSvc"),
        "FF": ("", "FF"), "NC": ("", "NCC"),
    }
    g, st = sub_map.get(sub, ("", sub))
    return vert, g, st


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — loading raw CSV (scraped via Chrome MCP)...")
    df = pd.read_csv(RAW_CSV, dtype={"institute_code": str})
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    print(f"  {len(df):,} rows, {df['institute_code'].nunique()} institutes")

    print("\nStage 2 — filtering to govt + main rounds (R1+R2+R3)...")
    df["is_govt"] = df.apply(is_govt, axis=1)
    gov = df[df["is_govt"]].copy()
    gov = gov[gov["round"].isin(["Round1", "Round2", "Round3"])].copy()
    gov = gov.reset_index(drop=True)  # critical: align index for concat
    print(f"  Govt: {len(gov):,} rows ("
          f"{(gov.branch=='MBBS').sum()} MBBS + {(gov.branch=='BDS').sum()} BDS)")

    print("\nStage 3 — decomposing categories...")
    deco = gov["category"].apply(lambda c: pd.Series(decompose_category(c)))
    deco.columns = ["vert", "seat_gender", "seat_subtype"]
    gov = pd.concat([gov, deco], axis=1)
    plain = gov[gov["seat_subtype"] == "plain"].copy()
    print(f"  Plain rows: {len(plain):,}")

    print("\nStage 4 — closing ranks per (institute, branch, vert, gender)...")
    cr = (
        plain.groupby(
            ["institute_code", "institute_name", "branch", "vert", "seat_gender"]
        )
        .agg(
            closing_AIR=("rank", "max"),
            opening_AIR=("rank", "min"),
            allotted_count=("rank", "count"),
        )
        .reset_index()
    )
    last_round = (
        plain.sort_values("rank", ascending=False)
        .drop_duplicates(["institute_code", "branch", "vert", "seat_gender"])
        [["institute_code", "branch", "vert", "seat_gender", "round"]]
        .rename(columns={"round": "last_round_with_max"})
    )
    cr = cr.merge(
        last_round, on=["institute_code", "branch", "vert", "seat_gender"]
    )
    cr["institute"] = cr["institute_name"].str.replace(
        r"\s*\(\s*\d+\s*\)\s*$", "", regex=True
    )
    cr = cr[[
        "institute_code", "institute", "branch", "vert", "seat_gender",
        "closing_AIR", "opening_AIR", "allotted_count", "last_round_with_max",
    ]]
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    gov.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  CR: {len(cr):,} rows")

    print("\nStage 5 — wide pivots (M boys + F girls)...")
    for gender in ("M", "F"):
        sub = cr[cr["seat_gender"] == gender]
        piv = sub.pivot_table(
            index=["institute_code", "institute", "branch"],
            columns="vert", values="closing_AIR", aggfunc="first",
        ).reset_index()
        present = [c for c in VERTICAL_ORDER if c in piv.columns]
        piv = piv[["institute_code", "institute", "branch"] + present]
        piv.to_csv(
            OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_{gender}.csv",
            index=False,
        )
        print(f"  pivot_{gender}: {len(piv)} rows "
              f"({(piv['branch']=='MBBS').sum()} MBBS + {(piv['branch']=='BDS').sum()} BDS)")

    print(f"\n=== Top 5 UP govt MBBS by UR-Boys closing AIR (2025) ===")
    piv_m = pd.read_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_M.csv"
    )
    print(piv_m[piv_m["branch"] == "MBBS"]
          .sort_values("UR", na_position="last").head(5)
          [["institute", "UR", "OBC", "EWS", "SC", "ST"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
