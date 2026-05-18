"""
Release configuration for PLFS unit-level data.

Each release describes:
- Source metadata: catalog ID + URL, label, reference period, weight rule
- Where its layout XLSX lives + where its data files live (input)
- Per-file byte totals + section bounds in the layout XLSX
- How field names are extracted from the layout (csv input + canonicalize, or
  self-contained per-file sheet, or txt fixed-width)

The single source of truth — when you add a new release, only this file changes.

A small helper `dump_registry_csv()` writes `clean/releases.csv` so the release
list + source URLs are also queryable as plain data.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Weight rules (per release, applied by analyses; documented in WEIGHTS.md):
#   combined      — mult / no_qtr / IF(nss=nsc, 100, 200)
#                   The standard PLFS rule, used by all annual releases +
#                   CY2022, CY2024.
#   half_yearly   — combined / 2
#                   CY2023 (cat 208) uses half-yearly panels; standard formula
#                   gives a half-year estimate, divide by 2 for full calendar.
#   simple        — mult / 100
#                   CY2025 (cat 284) redesigned rule. Each row's mult is
#                   already calibrated for the full year.
#   limited       — schema lacks tedu_lvl / pas / ind_pas / ern_reg
#                   CY2021 (cat 209) was a stripped-down release. Useful only
#                   for demographics + CWS, not for engineering-jobs work.

NADA = "https://microdata.gov.in/nada43/index.php/catalog"

RELEASES = {
    # ---- Annual Jul 2018 – Jun 2019 (catalog 216) ----
    # Pre-COVID baseline. CSV input (txt2csv pre-converted, user-supplied).
    # 4 files: HH_FV.txt, HH_RV.txt, PER_FV.txt, PER_RV.txt
    # HH_FV and HH_RV share the same 32-field schema in this release.
    "annual_2018_19": {
        "label":        "PLFS Annual, July 2018 – June 2019",
        "format":       "annual",
        "year_label":   "2018-19",
        "period_start": "2018-07",
        "period_end":   "2019-06",
        "catalog_id":   "216",
        "catalog_url":  f"{NADA}/216",
        "weight_rule":  "combined",
        "input_kind":   "csv",
        "xlsx":         ROOT / "raw" / "docs_annual_2018_19" / "Data_Layout_PLFS.xlsx",
        "data_dir":     ROOT / "raw" / "216 - PLFS_2018_19_CSV",
        "out_dir":      ROOT / "clean" / "annual_2018_19",
        "files": [
            {"key": "hhv1",  "section": (4, 36),    "byte_total": 86,  "csv_name": "HHV1_2018-19 (1).csv"},
            {"key": "hhrv",  "section": (4, 36),    "byte_total": 86,  "csv_name": "HHRV-2018-19 (1).csv"},
            {"key": "perv1", "section": (40, 169),  "byte_total": 319, "csv_name": "PerV1_2018-19.csv"},
            {"key": "perrv", "section": (173, 276), "byte_total": 275, "csv_name": "PerRV_2018-19.csv"},
        ],
    },

    # ---- Annual Jul 2019 – Jun 2020 (catalog 217) ----
    # Pre-COVID + first-quarter-of-COVID lockdown. TSV input (Nesstar export).
    "annual_2019_20": {
        "label":        "PLFS Annual, July 2019 – June 2020",
        "format":       "annual",
        "year_label":   "2019-20",
        "period_start": "2019-07",
        "period_end":   "2020-06",
        "catalog_id":   "217",
        "catalog_url":  f"{NADA}/217",
        "weight_rule":  "combined",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs_annual_2019_20" / "Data_Layout_PLFS_2019-20.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2019-2020",
        "out_dir":      ROOT / "clean" / "annual_2019_20",
        "files": [
            {"key": "hhv1",  "section": (4, 36),    "byte_total": 86,  "csv_name": "HHFV_2019-20.txt"},
            {"key": "hhrv",  "section": (4, 36),    "byte_total": 86,  "csv_name": "HHRV_2019-20.txt"},
            {"key": "perv1", "section": (40, 169),  "byte_total": 319, "csv_name": "PERFV_2019-20.txt"},
            {"key": "perrv", "section": (173, 279), "byte_total": 275, "csv_name": "PERRV_2019-20.txt"},
        ],
    },

    # ---- Annual Jul 2020 – Jun 2021 (catalog 206) ----
    # COVID year. New separate HHV1 (37 fields) / HHRV (32) split.
    "annual_2020_21": {
        "label":        "PLFS Annual, July 2020 – June 2021",
        "format":       "annual",
        "year_label":   "2020-21",
        "period_start": "2020-07",
        "period_end":   "2021-06",
        "catalog_id":   "206",
        "catalog_url":  f"{NADA}/206",
        "weight_rule":  "combined",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs_annual_2020_21" / "Data_Layout_PLFS_2020-21.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2020-21",
        "out_dir":      ROOT / "clean" / "annual_2020_21",
        "files": [
            {"key": "hhv1",  "section": (4, 45),    "byte_total": 126, "csv_name": "hhv1.txt"},
            {"key": "hhrv",  "section": (46, 82),   "byte_total":  86, "csv_name": "hhrv.txt"},
            {"key": "perv1", "section": (83, 246),  "byte_total": 362, "csv_name": "perv1.txt"},
            {"key": "perrv", "section": (247, 350), "byte_total": 275, "csv_name": "perrv.txt"},
        ],
    },

    # ---- Calendar Year 2021 (catalog 209) ----
    # First calendar release. Stripped-down schema — only Blocks 1, 4, 6.
    # No tedu_lvl / pas / ind_pas / ern_reg. Demographic + CWS only.
    "calendar_2021": {
        "label":        "PLFS Calendar Year 2021",
        "format":       "calendar",
        "year_label":   "CY2021",
        "period_start": "2021-01",
        "period_end":   "2021-12",
        "catalog_id":   "209",
        "catalog_url":  f"{NADA}/209",
        "weight_rule":  "limited",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs_calendar_2021" / "Data_Layout_PLFS_Calendar_2021.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2021-21",
        "out_dir":      ROOT / "clean" / "calendar_2021",
        "files": [
            {"key": "chhv1",  "section": (4, 47),  "byte_total": 128, "csv_name": "hhv1.txt"},
            {"key": "cperv1", "section": (48, 74), "byte_total":  71, "csv_name": "cperv1.txt"},
        ],
    },

    # ---- Annual Jul 2021 – Jun 2022 (catalog 214) ----
    "annual_2021_22": {
        "label":        "PLFS Annual, July 2021 – June 2022",
        "format":       "annual",
        "year_label":   "2021-22",
        "period_start": "2021-07",
        "period_end":   "2022-06",
        "catalog_id":   "214",
        "catalog_url":  f"{NADA}/214",
        "weight_rule":  "combined",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs_annual_2021_22" / "Data_Layout_PLFS_2021-22.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2021-22",
        "out_dir":      ROOT / "clean" / "annual_2021_22",
        "files": [
            {"key": "hhv1",  "section": (4, 45),    "byte_total": 126, "csv_name": "hhv1.txt"},
            {"key": "hhrv",  "section": (46, 82),   "byte_total":  86, "csv_name": "hhrv.txt"},
            {"key": "perv1", "section": (83, 230),  "byte_total": 333, "csv_name": "perv1.txt"},
            {"key": "perrv", "section": (231, 334), "byte_total": 275, "csv_name": "perrv.txt"},
        ],
    },

    # ---- Calendar Year 2022 (catalog 211) ----
    # Same schema as CY2024. CSV input (txt2csv pre-converted, user-supplied).
    "calendar_2022": {
        "label":        "PLFS Calendar Year 2022",
        "format":       "calendar",
        "year_label":   "CY2022",
        "period_start": "2022-01",
        "period_end":   "2022-12",
        "catalog_id":   "211",
        "catalog_url":  f"{NADA}/211",
        "weight_rule":  "combined",
        "input_kind":   "csv",
        "xlsx":         ROOT / "raw" / "docs_calendar_2022" / "Data_LayoutPLFS_Calendar_2022.xlsx",
        "data_dir":     ROOT / "raw" / "211 - PLFS_Data_2022-22_CSV",
        "out_dir":      ROOT / "clean" / "calendar_2022",
        "files": [
            {"key": "chhv1",  "section": (4, 44),   "byte_total": 129, "csv_name": "chhv1.csv"},
            {"key": "cperv1", "section": (46, 296), "byte_total": 333, "csv_name": "cperv1.csv"},
        ],
    },

    # ---- Annual Jul 2022 – Jun 2023 (catalog 210) ----
    # Has documented high-multiplier outlier (one Assam uninhabited village).
    # See raw/docs_annual_2022_23/Technical clarification...pdf.
    "annual_2022_23": {
        "label":        "PLFS Annual, July 2022 – June 2023",
        "format":       "annual",
        "year_label":   "2022-23",
        "period_start": "2022-07",
        "period_end":   "2023-06",
        "catalog_id":   "210",
        "catalog_url":  f"{NADA}/210",
        "weight_rule":  "combined",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs_annual_2022_23" / "Data_Layout_PLFS_2022-23.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2022-23",
        "out_dir":      ROOT / "clean" / "annual_2022_23",
        "files": [
            {"key": "hhv1",  "section": (4, 45),    "byte_total": 126, "csv_name": "hhv1.txt"},
            {"key": "hhrv",  "section": (46, 82),   "byte_total":  86, "csv_name": "hhrv.txt"},
            {"key": "perv1", "section": (83, 226),  "byte_total": 330, "csv_name": "perv1.txt"},
            {"key": "perrv", "section": (227, 330), "byte_total": 275, "csv_name": "perrv.txt"},
        ],
    },

    # ---- Calendar Year 2023 (catalog 208) ----
    # Half-yearly panel design — weight rule needs an extra /2.
    "calendar_2023": {
        "label":        "PLFS Calendar Year 2023",
        "format":       "calendar",
        "year_label":   "CY2023",
        "period_start": "2023-01",
        "period_end":   "2023-12",
        "catalog_id":   "208",
        "catalog_url":  f"{NADA}/208",
        "weight_rule":  "half_yearly",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs_calendar_2023" / "Data_LayoutPLFS_Calendar_2023.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2023-23",
        "out_dir":      ROOT / "clean" / "calendar_2023",
        "files": [
            {"key": "chhv1",  "section": (4, 45),   "byte_total": 129, "csv_name": "CHHV1.txt"},
            {"key": "cperv1", "section": (46, 297), "byte_total": 333, "csv_name": "cperv1.txt"},
        ],
    },

    # ---- Annual Jul 2023 – Jun 2024 (catalog 213) ----
    "annual_2023_24": {
        "label":        "PLFS Annual, July 2023 – June 2024",
        "format":       "annual",
        "year_label":   "2023-24",
        "period_start": "2023-07",
        "period_end":   "2024-06",
        "catalog_id":   "213",
        "catalog_url":  f"{NADA}/213",
        "weight_rule":  "combined",
        "input_kind":   "tsv",
        "xlsx":         ROOT / "raw" / "docs" / "Data_Layout_PLFS_2023-24.xlsx",
        "data_dir":     ROOT / "raw" / "_extracted_from_nesstar" / "DDI-IND-CSO-PLFS-2023-24",
        "out_dir":      ROOT / "clean" / "annual_2023_24",
        "files": [
            {"key": "hhv1",  "section": (2, 42),    "byte_total": 126, "csv_name": "hhv1.txt"},
            {"key": "hhrv",  "section": (44, 79),   "byte_total":  86, "csv_name": "hhrv.txt"},
            {"key": "perv1", "section": (81, 223),  "byte_total": 330, "csv_name": "perv1.txt"},
            {"key": "perrv", "section": (225, 330), "byte_total": 275, "csv_name": "perrv.txt"},
        ],
    },

    # ---- Calendar Year 2024 (catalog 254) ----
    "calendar_2024": {
        "label":        "PLFS Calendar Year 2024",
        "format":       "calendar",
        "year_label":   "CY2024",
        "period_start": "2024-01",
        "period_end":   "2024-12",
        "catalog_id":   "254",
        "catalog_url":  f"{NADA}/254",
        "weight_rule":  "combined",
        "input_kind":   "txt",  # fixed-width — only release where we still parse fixed-width
        "xlsx":         ROOT / "raw" / "docs_calendar_2024" / "Data_Layout_PLFS_Calendar_2024.xlsx",
        "data_dir":     ROOT / "raw" / "data_calendar_2024",
        "out_dir":      ROOT / "clean" / "calendar_2024",
        "self_contained": False,
        "files": [
            {"key": "chhv1",  "section": (2, 45),    "fieldname_sheet": "chhv1",  "fieldname_col": 6, "srl_join": True,  "byte_total": 129, "data_filename": "CHHV1.TXT"},
            {"key": "cperv1", "section": (46, 297),  "fieldname_sheet": "cperv1", "fieldname_col": 5, "srl_join": False, "byte_total": 333, "data_filename": "CPERV1.TXT"},
        ],
    },

    # ---- Calendar Year 2025 (catalog 284) ----
    # New simplified weight rule: mult/100. New variance fields (bstrm/zst/...).
    "calendar_2025": {
        "label":        "PLFS Calendar Year 2025",
        "format":       "calendar",
        "year_label":   "CY2025",
        "period_start": "2025-01",
        "period_end":   "2025-12",
        "catalog_id":   "284",
        "catalog_url":  f"{NADA}/284",
        "weight_rule":  "simple",
        "input_kind":   "txt",
        "xlsx":         ROOT / "raw" / "docs_calendar_2025" / "FV_Data_Layout_2025.xlsx",
        "data_dir":     ROOT / "raw" / "data_calendar_2025",
        "out_dir":      ROOT / "clean" / "calendar_2025",
        "self_contained": True,
        "files": [
            {"key": "chhv1",  "fieldname_sheet": "CHHV1",  "fieldname_col": 8,
             "byte_start_col": 6, "byte_end_col": 7, "byte_total": 218,
             "data_filename": "CHHV1.TXT"},
            {"key": "cperv1", "fieldname_sheet": "CPERV1", "fieldname_col": 8,
             "byte_start_col": 6, "byte_end_col": 7, "byte_total": 371,
             "data_filename": "CPERV1.TXT"},
        ],
    },
}


# -- Helper: a tiny registry CSV --------------------------------------------

def dump_registry_csv(out_path: Path = ROOT / "clean" / "releases.csv") -> None:
    """Emit a flat CSV summary of all releases — source URLs, period, weight
    rule, file counts. Lives at clean/releases.csv as a quick reference."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "release_id", "label", "format", "year_label",
            "period_start", "period_end",
            "catalog_id", "catalog_url",
            "weight_rule", "input_kind",
            "n_files", "file_keys",
        ])
        for rid, cfg in RELEASES.items():
            w.writerow([
                rid, cfg["label"], cfg["format"], cfg["year_label"],
                cfg["period_start"], cfg["period_end"],
                cfg["catalog_id"], cfg["catalog_url"],
                cfg["weight_rule"], cfg["input_kind"],
                len(cfg["files"]),
                "|".join(f["key"] for f in cfg["files"]),
            ])


if __name__ == "__main__":
    dump_registry_csv()
    print(f"Wrote {len(RELEASES)} releases → clean/releases.csv")
