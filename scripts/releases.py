"""
Release configuration for PLFS unit-level data.

Each release describes:
- Where its layout XLSX lives
- Where its data .txt files live (input)
- Where to write per-file CSVs (output)
- For each file, byte-totals + how to extract field names from the XLSX

Three release shapes the docs use:

1. ANNUAL (Jul-Jun, e.g. catalog 213): 4 files (HHV1, HHRV, PERV1, PERRV).
   The Data Layout sheet contains all 4 sections (with byte positions). The
   per-file sheet (`hhv1`, `hhrv`, `perv1`, `perrv`) carries field_name only.
   Join by Srl (column 1).

2. CALENDAR-2024 (catalog 254): 2 files (CHHV1, CPERV1). Same shape as
   ANNUAL — Data Layout has byte positions; per-file sheet has field_name.
   Join by Srl (`chhv1` sheet) or by row order (`cperv1` sheet, no Srl col).

3. CALENDAR-2025 (catalog 284): 2 files (CHHV1, CPERV1). Per-file sheet
   already contains byte_start, byte_end, field_name — fully self-contained.
   `Data Layout` is informational only.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# byte_total = expected record length (matches "RECORD LENGTH:N+1" in XLSX)
# section = (start_row, end_row) inclusive in 'Data Layout' sheet (set None
#           when the per-file sheet is self-contained)
# fieldname_sheet = sheet to read field names from
# fieldname_col = 1-indexed column with field_name in that sheet
# srl_join = whether to join Data Layout to fieldname_sheet via Srl (col A)
#            or by row order (False = use ordinal position)

RELEASES = {
    # ---- Annual Jul 2018 – Jun 2019 (catalog 216) ----
    # Pre-COVID baseline. CSV input (txt2csv pre-converted).
    # 4 files: HH_FV.txt, HH_RV.txt, PER_FV.txt, PER_RV.txt
    # HH_FV and HH_RV share the same 32-field schema in this release.
    "annual_2018_19": {
        "label": "PLFS Annual, July 2018 – June 2019 (catalog 216)",
        "input_kind": "csv",  # source CSVs already exist (txt2csv pre-converted)
        "xlsx": ROOT / "raw" / "docs_annual_2018_19" / "Data_Layout_PLFS.xlsx",
        "data_dir": ROOT / "raw" / "216 - PLFS_2018_19_CSV",
        "out_dir": ROOT / "clean" / "annual_2018_19",
        "layout_dir": ROOT / "clean" / "annual_2018_19" / "layout",
        "files": [
            # 2018-19 HH_FV and HH_RV share one section (rows 4-36, 32 fields, 86 bytes)
            {"key": "hhv1",  "section": (4, 36),    "byte_total": 86,  "csv_name": "HHV1_2018-19 (1).csv"},
            {"key": "hhrv",  "section": (4, 36),    "byte_total": 86,  "csv_name": "HHRV-2018-19 (1).csv"},
            {"key": "perv1", "section": (40, 169),  "byte_total": 319, "csv_name": "PerV1_2018-19.csv"},
            {"key": "perrv", "section": (173, 276), "byte_total": 275, "csv_name": "PerRV_2018-19.csv"},
        ],
    },

    # ---- Calendar Year 2022 (catalog 211) ----
    # Same schema as CY2024. CSV input (txt2csv pre-converted).
    "calendar_2022": {
        "label": "PLFS Calendar Year 2022, January – December 2022 (catalog 211)",
        "input_kind": "csv",
        "xlsx": ROOT / "raw" / "docs_calendar_2022" / "Data_LayoutPLFS_Calendar_2022.xlsx",
        "data_dir": ROOT / "raw" / "211 - PLFS_Data_2022-22_CSV",
        "out_dir": ROOT / "clean" / "calendar_2022",
        "layout_dir": ROOT / "clean" / "calendar_2022" / "layout",
        "files": [
            {"key": "chhv1",  "section": (4, 44),   "byte_total": 129, "csv_name": "chhv1.csv"},
            {"key": "cperv1", "section": (46, 296), "byte_total": 333, "csv_name": "cperv1.csv"},
        ],
    },

    "annual_2023_24": {
        "label": "PLFS Annual, July 2023 – June 2024 (catalog 213)",
        "input_kind": "txt",
        "xlsx": ROOT / "raw" / "docs" / "Data_Layout_PLFS_2023-24.xlsx",
        "data_dir": ROOT / "raw" / "data",
        "out_dir": ROOT / "clean" / "annual_2023_24",
        "layout_dir": ROOT / "clean" / "annual_2023_24" / "layout",
        "self_contained": False,
        "files": [
            {"key": "hhv1",  "section": (2, 42),    "fieldname_sheet": "hhv1",  "fieldname_col": 6, "srl_join": True,  "byte_total": 126, "data_filename": "HHV1.txt"},
            {"key": "hhrv",  "section": (44, 79),   "fieldname_sheet": "hhrv",  "fieldname_col": 6, "srl_join": True,  "byte_total":  86, "data_filename": "HHRV.txt"},
            {"key": "perv1", "section": (81, 223),  "fieldname_sheet": "perv1", "fieldname_col": 6, "srl_join": True,  "byte_total": 330, "data_filename": "PERV1.txt"},
            {"key": "perrv", "section": (225, 330), "fieldname_sheet": "perrv", "fieldname_col": 6, "srl_join": True,  "byte_total": 275, "data_filename": "PERRV.txt"},
        ],
    },
    "calendar_2024": {
        "label": "PLFS Calendar Year 2024, January – December 2024 (catalog 254)",
        "xlsx": ROOT / "raw" / "docs_calendar_2024" / "Data_Layout_PLFS_Calendar_2024.xlsx",
        "data_dir": ROOT / "raw" / "data_calendar_2024",
        "out_dir": ROOT / "clean" / "calendar_2024",
        "layout_dir": ROOT / "clean" / "calendar_2024" / "layout",
        "self_contained": False,
        "files": [
            # chhv1 sheet has Srl col (6 cols total). Section in Data Layout: rows 2-44.
            {"key": "chhv1",  "section": (2, 45),    "fieldname_sheet": "chhv1",  "fieldname_col": 6, "srl_join": True,  "byte_total": 129, "data_filename": "CHHV1.TXT"},
            # cperv1 sheet has NO Srl col (5 cols, headers at row 2). Pair by row order.
            {"key": "cperv1", "section": (46, 297),  "fieldname_sheet": "cperv1", "fieldname_col": 5, "srl_join": False, "byte_total": 333, "data_filename": "CPERV1.TXT"},
        ],
    },
    "calendar_2025": {
        "label": "PLFS Calendar Year 2025, January – December 2025 (catalog 284)",
        "xlsx": ROOT / "raw" / "docs_calendar_2025" / "FV_Data_Layout_2025.xlsx",
        "data_dir": ROOT / "raw" / "data_calendar_2025",
        "out_dir": ROOT / "clean" / "calendar_2025",
        "layout_dir": ROOT / "clean" / "calendar_2025" / "layout",
        "self_contained": True,
        "files": [
            # CY2025 per-file sheet has all 9 cols including byte positions (start in F, end in G,
            # field_name in H). Source-of-truth is the per-file sheet.
            {"key": "chhv1",  "fieldname_sheet": "CHHV1",  "fieldname_col": 8,
             "byte_start_col": 6, "byte_end_col": 7, "byte_total": 218,
             "data_filename": "CHHV1.TXT"},
            {"key": "cperv1", "fieldname_sheet": "CPERV1", "fieldname_col": 8,
             "byte_start_col": 6, "byte_end_col": 7, "byte_total": 371,
             "data_filename": "CPERV1.TXT"},
        ],
    },
}
