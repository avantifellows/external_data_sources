"""
HCES 2023-24 microdata transformer.

Builds a single household-level analytical master table from the 15 NSS HCES
level files. One row per household with:

  - composite HHID (stable across levels)
  - geography: state, sector (rural/urban), NSS region, district, stratum
  - demographics: HH size, type, religion, social group
  - assets/dwelling: land, dwelling type, ration card, cooking/lighting fuel
  - expenditure: monthly consumption expenditure (food/non-food/durables split + total)
  - MPCE = total monthly expenditure / HH size
  - survey weight (Multiplier / 100, per NSS convention)

Outputs:
  output/hces_household_master.csv
  output/hces_household_master.parquet
  output/hces_household_master_dictionary.csv  (column descriptions)

Approach: pandas, in-memory. The lower-level item files (L5, L9, L14 etc.)
are line-level and not needed for the household master; this script
deliberately ignores them to stay simple and fast.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

HCES_DIR = Path(__file__).resolve().parent.parent   # external_data_sources/hces
# The 15 raw NSS level CSVs (3.4 GB) are NOT in git — they live in GCS
# (gs://avantifellows-external-data/hces/raw/HCES_Data_2023-24_Csv/). Stage them
# locally (default hces/raw/) or point HCES_RAW_DIR at the dir that holds the CSVs:
#   gsutil -m cp -r gs://avantifellows-external-data/hces/raw/HCES_Data_2023-24_Csv hces/raw/
DATA_DIR = Path(os.environ.get("HCES_RAW_DIR", HCES_DIR / "raw" / "HCES_Data_2023-24_Csv"))
# transform writes the intermediate consumption master into clean/ (gitignored);
# add_income.py then derives income and writes the final BQ table parquet.
OUT_DIR = HCES_DIR / "clean"
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Composite household key
# ---------------------------------------------------------------------------
# The NSS HCES uses these five fields together to uniquely identify a sampled
# household. Sub_Division_No is sometimes blank (urban), so we coerce to "".
ID_COLS = [
    "FSU_Serial_No",
    "Sample_SU_No",
    "Sample_Sub_Division_No",
    "Second_Stage_Stratum_No",
    "Sample_Household_No",
]


def make_hhid(df: pd.DataFrame) -> pd.Series:
    parts = []
    for c in ID_COLS:
        s = df[c].astype("string").fillna("")
        parts.append(s)
    return parts[0].str.cat(parts[1:], sep="_")


# ---------------------------------------------------------------------------
# NSS standard code lookups
# ---------------------------------------------------------------------------
STATE_LABELS = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman & Diu", "26": "Dadra & Nagar Haveli", "27": "Maharashtra",
    "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "A & N Islands", "36": "Telangana",
    "37": "Ladakh", "38": "DNH & DD",
}

SECTOR_LABELS = {1: "Rural", 2: "Urban"}

RELIGION_LABELS = {
    1: "Hindu", 2: "Islam", 3: "Christianity", 4: "Sikhism",
    5: "Jainism", 6: "Buddhism", 7: "Zoroastrianism", 9: "Others",
}

SOCIAL_GROUP_LABELS = {1: "ST", 2: "SC", 3: "OBC", 9: "Others"}

# HCES 2023-24 uses a unified household-type coding (different from older NSS
# rural/urban split). 1=Self-employed in agri, 2=Self-employed in non-agri,
# 3=Regular wage/salary, 4=Casual labour in agri, 5=Casual labour in non-agri,
# 6=Others (rural); urban codes 7,8,9. We label generically here.
HH_TYPE_LABELS = {
    1: "Self-employed in agriculture",
    2: "Self-employed in non-agriculture",
    3: "Regular wage/salary earning",
    4: "Casual labour in agriculture",
    5: "Casual labour in non-agriculture",
    6: "Others (rural)",
    7: "Self-employed (urban)",
    8: "Regular wage/salary earning (urban)",
    9: "Casual labour (urban)",
    10: "Others (urban)",
}

RATION_CARD_LABELS = {
    1: "Antyodaya (AAY)",
    2: "BPL (non-AAY)",
    3: "Above Poverty Line (APL)",
    4: "Other ration card",
    9: "No card",
}

COOKING_FUEL_LABELS = {
    1: "Coke / coal",
    2: "Firewood and chips",
    3: "LPG",
    4: "Gobar gas",
    5: "Dung cake",
    6: "Charcoal",
    7: "Kerosene",
    8: "Electricity",
    9: "Others",
    10: "No cooking arrangement",
    11: "Piped natural gas (PNG)",
}

LIGHTING_FUEL_LABELS = {
    1: "Kerosene",
    2: "Other oil",
    3: "Gas",
    4: "Candle",
    5: "Electricity",
    6: "Solar energy",
    7: "Others",
    9: "No lighting arrangement",
}

DWELLING_LABELS = {1: "Owned", 2: "Hired", 3: "No dwelling unit", 9: "Others"}

LAND_OWNERSHIP_LABELS = {
    1: "Less than 0.005 hectares",
    2: "0.005 - 0.40 hectares",
    3: "0.41 - 1.00 hectares",
    4: "1.01 - 2.00 hectares",
    5: "2.01 - 4.00 hectares",
    6: "4.01 - 10.00 hectares",
    7: "More than 10.00 hectares",
}


# ---------------------------------------------------------------------------
# Load levels
# ---------------------------------------------------------------------------
def log(msg: str) -> None:
    print(f"[transform] {msg}", flush=True)


def load_level1() -> pd.DataFrame:
    """L1: household identification + sample weight (Multiplier)."""
    f = DATA_DIR / "LEVEL - 01(Section 1 and 1_1).csv"
    log(f"Reading L1 {f.name}")
    df = pd.read_csv(
        f,
        dtype={
            "State": "string",
            "Sector": "Int8",
            "NSS_Region": "string",
            "District": "string",
            "Stratum": "string",
            "Sub_stratum": "string",
        },
    )
    df["HHID"] = make_hhid(df)
    out = df[
        [
            "HHID",
            "State",
            "Sector",
            "NSS_Region",
            "District",
            "Stratum",
            "Sub_stratum",
            "Panel",
            "Sub_sample",
            "Multiplier",
        ]
    ].copy()
    # NSS convention: divide multiplier by 100 (or 200 if combined sub-samples).
    out["weight"] = out["Multiplier"] / 100.0
    return out


def load_level3() -> pd.DataFrame:
    """L3: household characteristics (size, type, religion, dwelling, fuels)."""
    f = DATA_DIR / "LEVEL - 03.csv"
    log(f"Reading L3 {f.name}")
    df = pd.read_csv(f)
    df["HHID"] = make_hhid(df)
    out = df[
        [
            "HHID",
            "HH_Size_FDQ",
            "Household_Type",
            "Religion_of_HH_Head",
            "Social_Group_of_HH_Head",
            "Land_Ownership",
            "Total_Area_Land_Owned_Acres",
            "Type_of_Dwelling_Unit",
            "Energy_Source_Cooking",
            "Energy_Source_Lighting",
            "Ration_Card_Type",
            "Benefitted_From_PMGKY",
        ]
    ].copy()
    return out


def load_level15_expenditure() -> pd.DataFrame:
    """L15: monthly consumption expenditure per visit/section.

    Each household has rows for SECTION in {A2 (food), B2 (consumables),
    C2 (durables)} across one or more visits. We sum MONTHLY_CONSUMPTION_EXP
    per (household, section), then pivot to wide.
    """
    f = DATA_DIR / "LEVEL - 15 (Section 1_1, A2,B2  C2).csv"
    log(f"Reading L15 {f.name}")
    df = pd.read_csv(f, low_memory=False)
    df["HHID"] = make_hhid(df)

    sec_df = df[df["SECTION"].isin(["A2", "B2", "C2"])].copy()
    # NB: many households appear only once per section (one visit per basket).
    # We sum defensively in case of multiple rows.
    agg = (
        sec_df.groupby(["HHID", "SECTION"], dropna=False)["MONTHLY_CONSUMPTION_EXP"]
        .sum(min_count=1)
        .unstack("SECTION")
        .rename(
            columns={
                "A2": "monthly_exp_food",
                "B2": "monthly_exp_consumables",
                "C2": "monthly_exp_durables",
            }
        )
        .reset_index()
    )
    for c in ["monthly_exp_food", "monthly_exp_consumables", "monthly_exp_durables"]:
        if c not in agg.columns:
            agg[c] = 0.0
        agg[c] = agg[c].fillna(0.0)

    # Online expenditure across all three visits (sum where present).
    online = (
        sec_df.groupby("HHID")["ONLINE_EXPENDITURE"].sum(min_count=1).rename("online_exp_total")
    )
    agg = agg.merge(online, on="HHID", how="left")

    agg["monthly_exp_total"] = (
        agg["monthly_exp_food"]
        + agg["monthly_exp_consumables"]
        + agg["monthly_exp_durables"]
    )
    return agg


# ---------------------------------------------------------------------------
# Build master
# ---------------------------------------------------------------------------
def build_master() -> pd.DataFrame:
    l1 = load_level1()
    l3 = load_level3()
    l15 = load_level15_expenditure()

    log(f"L1={len(l1):,}  L3={len(l3):,}  L15-agg={len(l15):,}")

    df = l1.merge(l3, on="HHID", how="left").merge(l15, on="HHID", how="left")
    log(f"Merged master rows: {len(df):,}")

    # ---- decoded labels ----
    df["state_name"] = df["State"].map(STATE_LABELS)
    df["sector_name"] = df["Sector"].map(SECTOR_LABELS)
    df["religion_name"] = df["Religion_of_HH_Head"].map(RELIGION_LABELS)
    df["social_group_name"] = df["Social_Group_of_HH_Head"].map(SOCIAL_GROUP_LABELS)
    df["household_type_name"] = df["Household_Type"].map(HH_TYPE_LABELS)
    df["ration_card_name"] = df["Ration_Card_Type"].map(RATION_CARD_LABELS)
    df["cooking_fuel_name"] = df["Energy_Source_Cooking"].map(COOKING_FUEL_LABELS)
    df["lighting_fuel_name"] = df["Energy_Source_Lighting"].map(LIGHTING_FUEL_LABELS)
    df["dwelling_type_name"] = df["Type_of_Dwelling_Unit"].map(DWELLING_LABELS)
    df["land_ownership_name"] = df["Land_Ownership"].map(LAND_OWNERSHIP_LABELS)

    # ---- MPCE ----
    df["mpce"] = df["monthly_exp_total"] / df["HH_Size_FDQ"].where(df["HH_Size_FDQ"] > 0)

    # ---- tidy column order ----
    col_order = [
        # identifiers
        "HHID",
        "State", "state_name",
        "Sector", "sector_name",
        "NSS_Region", "District", "Stratum", "Sub_stratum",
        "Panel", "Sub_sample",
        # demographics
        "HH_Size_FDQ",
        "Household_Type", "household_type_name",
        "Religion_of_HH_Head", "religion_name",
        "Social_Group_of_HH_Head", "social_group_name",
        # assets / dwelling
        "Land_Ownership", "land_ownership_name", "Total_Area_Land_Owned_Acres",
        "Type_of_Dwelling_Unit", "dwelling_type_name",
        "Energy_Source_Cooking", "cooking_fuel_name",
        "Energy_Source_Lighting", "lighting_fuel_name",
        "Ration_Card_Type", "ration_card_name",
        "Benefitted_From_PMGKY",
        # expenditure
        "monthly_exp_food",
        "monthly_exp_consumables",
        "monthly_exp_durables",
        "monthly_exp_total",
        "online_exp_total",
        "mpce",
        # weights
        "Multiplier", "weight",
    ]
    df = df[col_order]
    df = df.rename(
        columns={
            "HH_Size_FDQ": "hh_size",
            "Total_Area_Land_Owned_Acres": "land_area_acres",
            "Benefitted_From_PMGKY": "benefitted_from_pmgky",
            "NSS_Region": "nss_region",
            "District": "district",
            "Stratum": "stratum",
            "Sub_stratum": "sub_stratum",
            "Panel": "panel",
            "Sub_sample": "sub_sample",
            "State": "state_code",
            "Sector": "sector_code",
            "Household_Type": "household_type_code",
            "Religion_of_HH_Head": "religion_code",
            "Social_Group_of_HH_Head": "social_group_code",
            "Land_Ownership": "land_ownership_code",
            "Type_of_Dwelling_Unit": "dwelling_type_code",
            "Energy_Source_Cooking": "cooking_fuel_code",
            "Energy_Source_Lighting": "lighting_fuel_code",
            "Ration_Card_Type": "ration_card_code",
            "Multiplier": "multiplier_raw",
        }
    )
    return df


DICTIONARY_ROWS = [
    ("HHID", "Composite household ID (FSU_SU_SubDiv_SSS_HHno)"),
    ("state_code", "NSS 2-digit state code"),
    ("state_name", "State / UT name"),
    ("sector_code", "1=Rural, 2=Urban"),
    ("sector_name", "Decoded sector"),
    ("nss_region", "NSS Region code (3-digit)"),
    ("district", "District code (within state)"),
    ("stratum", "Sampling stratum"),
    ("sub_stratum", "Sampling sub-stratum"),
    ("panel", "Panel number"),
    ("sub_sample", "Sub-sample number"),
    ("hh_size", "Household size from FDQ"),
    ("household_type_code", "NSS household type code"),
    ("household_type_name", "Decoded household type"),
    ("religion_code", "Religion of HH head, NSS code"),
    ("religion_name", "Decoded religion"),
    ("social_group_code", "Social group of HH head"),
    ("social_group_name", "Decoded social group"),
    ("land_ownership_code", "Land ownership category"),
    ("land_ownership_name", "Decoded land ownership category"),
    ("land_area_acres", "Total land owned (acres)"),
    ("dwelling_type_code", "Dwelling unit ownership code"),
    ("dwelling_type_name", "Decoded dwelling type"),
    ("cooking_fuel_code", "Primary cooking-energy code"),
    ("cooking_fuel_name", "Decoded cooking fuel"),
    ("lighting_fuel_code", "Primary lighting-energy code"),
    ("lighting_fuel_name", "Decoded lighting fuel"),
    ("ration_card_code", "Ration card type code"),
    ("ration_card_name", "Decoded ration card type"),
    ("benefitted_from_pmgky", "1=Yes, 2=No: PMGKY beneficiary"),
    ("monthly_exp_food", "Monthly food expenditure (Section A2)"),
    ("monthly_exp_consumables", "Monthly consumables expenditure (Section B2)"),
    ("monthly_exp_durables", "Monthly durables-equivalent expenditure (Section C2)"),
    ("monthly_exp_total", "Sum of food + consumables + durables (Rs/month)"),
    ("online_exp_total", "Total online expenditure across visits (Rs/month)"),
    ("mpce", "Monthly per-capita expenditure = total / hh_size"),
    ("multiplier_raw", "Raw NSS multiplier (Multiplier column)"),
    ("weight", "Survey weight = multiplier_raw / 100"),
]


def main() -> int:
    df = build_master()

    csv_path = OUT_DIR / "hces_household_master.csv"
    parquet_path = OUT_DIR / "hces_household_master.parquet"
    dict_path = OUT_DIR / "hces_household_master_dictionary.csv"

    log(f"Writing {csv_path}")
    df.to_csv(csv_path, index=False)

    log(f"Writing {parquet_path}")
    try:
        df.to_parquet(parquet_path, index=False)
    except Exception as e:  # parquet engine optional
        log(f"  parquet skipped: {e}")

    log(f"Writing {dict_path}")
    pd.DataFrame(DICTIONARY_ROWS, columns=["column", "description"]).to_csv(
        dict_path, index=False
    )

    # quick summary
    log("=== summary ===")
    log(f"households:           {len(df):,}")
    log(f"weighted households:  {df['weight'].sum():,.0f}")
    log(f"mean MPCE (unweighted): Rs {df['mpce'].mean():,.0f}")
    w = df["weight"]
    log(f"mean MPCE (weighted):   Rs {(df['mpce'] * w).sum() / w.sum():,.0f}")
    log("by sector (weighted mean MPCE):")
    grp = (
        df.assign(_wexp=df["mpce"] * df["weight"])
        .groupby("sector_name", dropna=False)
        .agg(weighted_mpce=("_wexp", "sum"), total_weight=("weight", "sum"))
    )
    grp["weighted_mpce"] /= grp["total_weight"]
    log("\n" + grp.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
