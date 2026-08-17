"""
Himachal Pradesh NEET UG 2025 — state govt closing ranks pipeline.

Authority: Atal Medical & Research University (AMRU), HP. https://amruhp.ac.in
Source PDFs: AMRU's MBBS/BDS NEET-UG counselling page.
URLs:
  R1 Final: https://amruhp.ac.in/wp-content/uploads/2025/08/Final-Seat-Allocation-of-MBBS-BDS-1st-Round-Counselling-2025-merged.pdf
  R3 Final: https://amruhp.ac.in/wp-content/uploads/2025/11/Final-Seat-allocation-of-MBBS-BDS-3rd-round-Counselling-2025-merged.pdf

Last round used: cumulative R1 + R3 (R3 captures R3 upgrades; R1 is the
                 bulk allotment). R2 is intermediate. Stray Round excluded.

Schema (per-row): SrNo | Merit | App No | Name | College | All India Rank | Quota | Category

Closing-rank metric: NEET AIR (column header literally says "All India Rank").
                     The "Merit" column is HP's internal sequential merit
                     number — NOT used for closing ranks. AIR is used so HP
                     is comparable to other states on the unified AIR scale.

Govt-college filter: institution name contains "Govt Medical" / "Government
                     Medical" / "Government Dental" / "Indira Gandhi Medical".
Result: 6 govt MBBS + 1 govt BDS (matches NMC list 6+1).

Reservation taxonomy (HP):
  Vertical: General / OBC / EWS / SC / ST + sub-categories (Children of
            J&K Migrants, Tibetan Refugees, IRDP/BPL, Backward Area,
            Single Girl Child, Defence)

Outputs (to ../extracted_data/):
  - HP_all_allotments_2025.csv             — raw rows
  - HP_closing_ranks_state_govt_2025.csv   — long format
  - HP_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "HP"
OUT = ROOT / "extracted_data"
STATE_CODE = "HP"

ROUND_FILES = [
    ("HP_R1_Final_2025.pdf", "R1"),
    ("HP_R3_Final_2025.pdf", "R3"),
]

GOVT_HP_KEYWORDS = [
    "Govt Medical", "Government Medical", "Government Dental",
    "Indira Gandhi Medical", "Govt Dental",
]
CAT_ORDER = ["General", "OBC", "EWS", "SC", "ST"]


def parse_hp_pdf(path: Path, label: str) -> list[dict]:
    """HP table layout differs across rounds:
      R1 PDF: Sr | Merit | App No | Name | Institute | Degree | AdmType | Category
              (NO AIR column — only HP internal Merit number)
      R3 PDF: Sr | Merit | App No | Name | Institute | All India Rank | AdmType | Category

    We extract Merit (always present) and try AIR (only present in R3).
    R1's missing AIR is later imputed via the R3-derived (merit → AIR)
    lookup curve so all rounds share a single AIR scale.
    """
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for r in table:
                    if not r or len(r) < 6:
                        continue
                    sn = str(r[0] or "").strip()
                    if not sn.isdigit():
                        continue
                    merit = str(r[1] or "").strip().replace(",", "")
                    if not merit.isdigit():
                        continue
                    # AIR is in col 5 in R3 but not in R1. Detect by checking
                    # if col 5 is a 4+ digit numeric (AIR) vs a short string
                    # (e.g. "MBBS" / "BDS" in R1).
                    air = None
                    cell5 = str(r[5] or "").strip().replace(",", "")
                    if cell5.isdigit() and len(cell5) >= 4:
                        air = int(cell5)
                    cells = [str(c or "").strip() for c in r]
                    quota = ""
                    category = ""
                    for c in reversed(cells):
                        if c and "Quota" in c and not quota:
                            quota = c
                            continue
                        if c and any(
                            k in c for k in [
                                "General", "OBC", "SC", "ST", "EWS",
                                "NRI", "Migrant", "Single", "Defence",
                                "Tibetan", "BPL", "Backward",
                            ]
                        ) and not category:
                            category = c
                    rec = {
                        "file": label,
                        "sn": int(sn),
                        "merit": int(merit),       # HP internal merit number (sequential)
                        "neet_air": air,            # NEET 2025 AIR (R3 only; imputed for R1 below)
                        "roll": str(r[2] or "").strip(),
                        "name": re.sub(r"\s+", " ", str(r[3] or "")).strip(),
                        "college": re.sub(r"\s+", " ", str(r[4] or "")).strip(),
                        "quota": re.sub(r"\s+", " ", quota),
                        "category": re.sub(r"\s+", " ", category),
                    }
                    rows.append(rec)
    return rows


def impute_air_from_merit(df: pd.DataFrame) -> pd.DataFrame:
    """Build a (merit → AIR) curve from rows where AIR is known (R3) and
    apply it to fill missing AIR (R1)."""
    known = df[df["neet_air"].notna()].copy()
    known["merit"] = known["merit"].astype(int)
    known["neet_air"] = known["neet_air"].astype(int)
    known = known.sort_values("merit")
    print(f"  AIR-known rows: {len(known)}; merit range {known.merit.min()}–{known.merit.max()}; "
          f"AIR range {known.neet_air.min():,}–{known.neet_air.max():,}")
    if known.empty:
        df["air_imputed"] = df["neet_air"]
        return df
    # Piecewise-linear interpolation
    import numpy as np
    df["air_imputed"] = df["neet_air"]
    missing = df[df["neet_air"].isna() & df["merit"].notna()]
    interp_air = np.interp(missing["merit"].astype(int),
                            known["merit"], known["neet_air"])
    df.loc[missing.index, "air_imputed"] = interp_air.astype(int)
    print(f"  Imputed AIR for {len(missing)} R1 rows; combined coverage {df['air_imputed'].notna().sum()}/{len(df)}")
    return df


def is_govt(name: str) -> bool:
    n = str(name)
    return any(k in n for k in GOVT_HP_KEYWORDS)


def base_category(c: str) -> str:
    c = str(c)
    if "General" in c:
        return "General"
    if "OBC" in c:
        return "OBC"
    if "EWS" in c or "Economic" in c:
        return "EWS"
    if "SC" in c and "ST" not in c:
        return "SC"
    if "ST" in c:
        return "ST"
    return c


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R1 + R3...")
    all_rows = []
    for fname, label in ROUND_FILES:
        rows = parse_hp_pdf(SOURCE / fname, label)
        print(f"  {fname}: {len(rows)}")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df)}")

    print("\nStage 2 — impute AIR for R1 rows from R3 merit→AIR curve...")
    df = impute_air_from_merit(df)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)

    print("\nStage 3 — filtering to govt + HP Quota + non-null AIR...")
    gov = df[
        df["college"].apply(is_govt)
        & df["quota"].str.contains("HP Quota", na=False)
        & df["air_imputed"].notna()
    ].copy()
    gov["cat_base"] = gov["category"].apply(base_category)
    print(f"  Govt rows: {len(gov)}")

    print("\nStage 4 — closing ranks (NEET AIR)...")
    cr = (
        gov.groupby(["college", "cat_base"])["air_imputed"]
        .agg(closing_neet_air="max", opening_neet_air="min", allotted_count="count")
        .reset_index()
    )
    cr["program"] = cr["college"].apply(
        lambda c: "BDS" if "Dental" in str(c) else "MBBS"
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 5 — wide pivot...")
    piv = cr.pivot_table(
        index=["college", "program"], columns="cat_base",
        values="closing_neet_air", aggfunc="first",
    ).reset_index()
    piv = piv[["college", "program"] + [c for c in CAT_ORDER if c in piv.columns]]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print("\n=== HP govt by General closing NEET AIR ===")
    print(piv.sort_values("General", na_position="last").to_string(index=False))


if __name__ == "__main__":
    main()
