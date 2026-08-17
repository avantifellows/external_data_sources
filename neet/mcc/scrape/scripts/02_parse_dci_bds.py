"""
Parse the DCI (Dental Council of India) college search HTML into clean CSVs.

Source: ../source/dci_bds_search.html
        Downloaded from
        https://dciindia.gov.in/CollegeSearch.aspx?ColName=&CourseId=1&SplId=0&StateId=&Hospital=&Type=0&Status=--Select--
        (live HTML, snapshot taken May 2026)

Outputs (to ../extracted_data/):
  - bds_all_colleges_2025-26.csv   — all 330 BDS colleges
  - bds_govt_colleges_2025-26.csv  — 60 govt BDS colleges
"""
import pandas as pd
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
HTML = ROOT / "source" / "dci_bds_search.html"
OUT_DIR = ROOT / "extracted_data"


def main():
    print(f"Parsing {HTML.name}...")
    tables = pd.read_html(HTML)
    # The main data table is the largest one
    df = max(tables, key=len)
    df.columns = ["sno", "college", "state", "est_year", "mgmt", "seats_raw",
                  "remark", "more"]
    df = df.drop(columns=["more"])

    # Seat field looks like "BDSN/A100" — trailing integer is intake
    df["intake_2025_26"] = df["seats_raw"].apply(
        lambda s: int(re.search(r"(\d+)\s*$", str(s)).group(1))
        if pd.notna(s) and re.search(r"(\d+)\s*$", str(s))
        else None
    )
    df["mgmt"] = df["mgmt"].fillna("Unknown")

    print(f"  {len(df)} colleges, {df['intake_2025_26'].sum():,.0f} BDS seats")
    print("  By management:")
    print(df.groupby("mgmt").agg(
        colleges=("college", "count"),
        intake=("intake_2025_26", "sum"),
    ))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_DIR / "bds_all_colleges_2025-26.csv", index=False)

    gov = df[df["mgmt"] == "Govt."].copy()
    gov = gov[["sno", "state", "college", "mgmt", "est_year",
               "intake_2025_26", "remark"]]
    gov.to_csv(OUT_DIR / "bds_govt_colleges_2025-26.csv", index=False)

    print(f"\n=== Govt BDS 2025-26 ===")
    print(f"  {len(gov)} colleges, {gov['intake_2025_26'].sum():,.0f} seats")


if __name__ == "__main__":
    main()
