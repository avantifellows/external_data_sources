"""
AISHE source configuration — the single source of truth.

Everything downstream (clean_aishe.py, build_institution_directory.py,
upload_to_gcs.py, load_bq.py) reads from here.

Two pipelines:

1. Higher-ed students (aishe_fact_higher_ed_students)
   Student enrolment + graduates from AISHE Final Report workbooks (Tables 33,
   34a, 12+35). Parsed by clean_aishe.py.

2. Institution directory (aishe_dim_colleges, aishe_dim_universities, etc.)
   Live registry of all HE institutions downloaded from the AISHE HE Directory
   dashboard (dashboard.aishe.gov.in/hedirectory). Parsed by
   build_institution_directory.py. One row per institution.

GCS layout:
    aishe/raw/<year>/<sheet>.parquet   — Final Report raw sheets (traceability)
    aishe/raw/institution_directory/   — Institution directory raw xlsx files
    aishe/clean/<table>.parquet        — loaded to BQ
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"        # source Final Report workbooks (.xlsx, gitignored)
CLEAN = ROOT / "clean"    # parsed parquet, ready for upload (gitignored)
CODEMAPS = ROOT / "codemaps"

SENTINEL = "All"          # dimension value for "not broken out on this cut"

# ─── Basis: actual response vs estimated ──────────────────────────────────────
# AISHE publishes two kinds of figure and says which in the table caption:
#
#   "based on actual response"  the totals reported BY the institutions that
#                               responded to the survey that year.
#   "Estimated"                 those totals grossed up to the full registered
#                               population, to account for non-response.
#
# They are not comparable. Response rates vary by year and state, so an estimated
# figure is systematically larger than the actual-response one for the same cell —
# comparing across the two reads as growth that did not happen. Every row carries
# `basis` so the two can never be mixed silently.
BASIS_ACTUAL = "actual response"
BASIS_ESTIMATED = "estimated"

# ─── Raw source workbooks (gitignored; fetched from the URLs below by fetch.py) ─
REPORTS: dict[str, Path] = {
    "2019-20": RAW / "aishe_2019-20_final_report.xlsx",
    "2020-21": RAW / "aishe_2020-21_final_report.xlsx",
    "2021-22": RAW / "aishe_2021-22_final_report.xlsx",
    "2022-23": RAW / "aishe_2022-23_final_report.xlsx",
    "2023-24": RAW / "aishe_2023-24_final_report.xlsx",
}

# ─── Excel editions — 2019-20 onward only ─────────────────────────────────────
# The download path is `assets/excel/<year>.xlsx`. That is worth spelling out
# because it was wrong here for a long time: the previous URLs used the *download
# filename* the viewer sets ("AISHE Final Report 2021-22.xlsx") as if it were the
# path, so all five 404'd and the workbooks looked unfetchable. The real pattern is
# in the viewer's own bundle:
#
#   downloadFile(e){ const i = `assets/excel/${e}.xlsx`; …
#                    r.download = `AISHE Final Report ${e}.xlsx` }
#
# Probed every year from 2010-11: 2019-20 through 2023-24 return 200, and every
# earlier year 404s. So there is no Excel edition before 2019-20 — the PDF is not a
# fallback for those years, it is the only thing that exists. Re-check with:
#   for y in 2018-19 2019-20; do curl -sI -o /dev/null -w "$y %{http_code}\n" \
#     https://he.nic.in/aishereport/assets/excel/$y.xlsx; done
_XLS = "https://he.nic.in/aishereport/assets/excel"
REPORT_URLS: dict[str, str] = {
    "2019-20": f"{_XLS}/2019-20.xlsx",
    "2020-21": f"{_XLS}/2020-21.xlsx",
    "2021-22": f"{_XLS}/2021-22.xlsx",
    "2022-23": f"{_XLS}/2022-23.xlsx",
    "2023-24": f"{_XLS}/2023-24.xlsx",
}

# Canonical source URLs — AISHE Final Report PDFs, on the MoE content CDN. These
# are the *only* machine-fetchable edition, and the only edition at all for
# 2012-13 … 2018-19. Verified 2026-08-03.
_CDN = ("https://cdnbbsr.s3waas.gov.in/s392049debbe566ca5782a3045cf300a3c/uploads")
PDF_REPORT_URLS: dict[str, str] = {
    "2012-13": f"{_CDN}/2025/06/20250604192794875.pdf",
    "2013-14": f"{_CDN}/2025/06/202506041593835380.pdf",
    "2014-15": f"{_CDN}/2025/06/202506041473712372.pdf",
    "2015-16": f"{_CDN}/2025/06/20250604868258281.pdf",
    "2016-17": f"{_CDN}/2025/06/20250604257561305.pdf",
    "2017-18": f"{_CDN}/2025/06/202506041358047572.pdf",
    "2018-19": f"{_CDN}/2025/06/20250604802450485.pdf",
    "2019-20": f"{_CDN}/2025/06/20250604434323531.pdf",
    "2020-21": f"{_CDN}/2025/06/202506041612700081.pdf",
    "2021-22": f"{_CDN}/2025/06/2025060466438560.pdf",
    "2022-23": f"{_CDN}/2026/07/20260708401535366.pdf",
    "2023-24": f"{_CDN}/2026/07/202607131602421770.pdf",
}

PDF_REPORTS: dict[str, Path] = {
    year: RAW / f"aishe_{year}_final_report.pdf" for year in PDF_REPORT_URLS
}

# The GER / GPI time series, published as standalone PDFs rather than inside a
# report. Both cover 2011-12 → 2021-22 and are not yet ingested — see
# schemas/README.md for the status line.
TIMESERIES_URLS: dict[str, str] = {
    "ger": f"{_CDN}/2025/06/202506041164303308.pdf",
    "gpi": f"{_CDN}/2025/06/20250604850977088.pdf",
}

# ─── GCS ──────────────────────────────────────────────────────────────────────
GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "aishe"

# ─── BigQuery ───────────────────────────────────────────────────────────────
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"         # asia-south1
BQ_LOCATION = "asia-south1"


# ─── Clean table (parsed → GCS clean/ → loaded to BQ) ─────────────────────────
@dataclass(frozen=True)
class Table:
    bq_name: str
    parquet: str
    grain: str

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet


TABLES: list[Table] = [
    # ── Pipeline 1: higher-ed students (from Final Report workbooks) ───────────
    Table(
        bq_name="aishe_fact_higher_ed_students",
        parquet="higher_ed.parquet",
        grain="(cut, aishe_year, metric, level, state, discipline, programme, social_category, gender)",
    ),
    # ── Pipeline 2: institution directory (from HE Directory dashboard xlsx) ───
    Table(
        bq_name="aishe_dim_colleges",
        parquet="aishe_dim_colleges.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_universities",
        parquet="aishe_dim_universities.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_standalone_institutions",
        parquet="aishe_dim_standalone_institutions.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_research_institutions",
        parquet="aishe_dim_research_institutions.parquet",
        grain="(aishe_code)",
    ),
    Table(
        bq_name="aishe_dim_pm_vidyalaxmi_eligible_institutions",
        parquet="aishe_dim_pm_vidyalaxmi_eligible_institutions.parquet",
        grain="(aishe_code)",
    ),
]

# Convenience lookups
TABLE_BY_NAME: dict[str, Table] = {t.bq_name: t for t in TABLES}


# ─── Institution directory — per-table config for build_institution_directory.py ─
# Separate dataclass because these tables have xlsx-specific fields (raw filename,
# header row, column renames) that the higher-ed pipeline doesn't need.

@dataclass(frozen=True)
class DirectoryTable:
    bq_name: str                          # must match a bq_name in TABLES
    raw_file: str                         # xlsx filename under raw/institution_directory/
    header_row: int                       # 0-based row of the column header in the xlsx
    column_renames: dict[str, str]        # raw Excel header → snake_case BQ column name

    @property
    def raw_path(self) -> Path:
        return RAW / "institution_directory" / self.raw_file

    @property
    def clean_path(self) -> Path:
        return CLEAN / f"{self.bq_name}.parquet"


COLLEGES_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "State": "state",
    "District": "district",
    "Website": "website",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "College Type": "college_type",
    "Manegement": "management",
    "University Aishe Code": "university_aishe_code",
    "University Name": "university_name",
    "University Type": "university_type",
}

UNIVERSITIES_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "State": "state",
    "District": "district",
    "Website": "website",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "University Type": "university_type",
}

STANDALONE_RENAMES = {
    "Aishe Code": "aishe_code",
    "Name": "name",
    "Web Url": "website",
    "State": "state",
    "District": "district",
    "Year Of Establishment": "year_of_establishment",
    "Location": "location",
    "Standalone Type": "standalone_type",
    "Manegement": "management",
}

RD_RENAMES = {
    "S. No.": "sno",
    "AISHE Code": "aishe_code",
    "Institute Name": "institute_name",
    "State Name": "state_name",
    "District Name": "district_name",
    "Administrative Ministry": "administrative_ministry",
}

PM_VIDYALAXMI_RENAMES = {
    "S. No.": "sno",
    "AISHE Code": "aishe_code",
    "Institute Name": "institute_name",
    "State Name": "state_name",
    "Management Type": "management_type",
}

DIRECTORY_TABLES: list[DirectoryTable] = [
    DirectoryTable(
        bq_name="aishe_dim_colleges",
        raw_file="College-ALL COLLEGE.xlsx",
        header_row=2,
        column_renames=COLLEGES_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_universities",
        raw_file="University-ALL UNIVERSITIES.xlsx",
        header_row=2,
        column_renames=UNIVERSITIES_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_standalone_institutions",
        raw_file="Standalone-ALL_STANDALONE_with_URLs.xlsx",
        header_row=2,
        column_renames=STANDALONE_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_research_institutions",
        raw_file="R & D Institutes.xlsx",
        header_row=2,
        column_renames=RD_RENAMES,
    ),
    DirectoryTable(
        bq_name="aishe_dim_pm_vidyalaxmi_eligible_institutions",
        raw_file="vidya_lakshmiAll.xlsx",
        header_row=2,
        column_renames=PM_VIDYALAXMI_RENAMES,
    ),
]

DIRECTORY_TABLE_BY_NAME: dict[str, DirectoryTable] = {t.bq_name: t for t in DIRECTORY_TABLES}

# Institution directory raw Excel files — for upload_to_gcs.py
INSTITUTION_DIRECTORY_RAW_FILES: list[str] = [t.raw_file for t in DIRECTORY_TABLES]

# ─── Raw sheets — the parse registry ──────────────────────────────────────────
# Doubles as (a) what clean_aishe.py parses and (b) what upload_to_gcs.py mirrors
# to GCS raw/ as parquet for traceability. One entry per (year, sheet): adding a
# year means adding its entries here, which is what makes a year contribute a cut.
@dataclass(frozen=True)
class RawSheet:
    year: str
    sheet: str
    cut: str      # state_level | state_social | programme_social | ug_discipline
    metric: str   # 'graduates' | 'enrolment'
    # Cross-tab group labels AS PRINTED IN THIS YEAR'S SHEET, in order. The read is
    # positional, and AISHE relabels between editions ("All" vs "All Categories",
    # "Other Backward Class" vs "…Classes", EWS absent before 2020-21), so this
    # cannot be one shared list. None means the reader's own default.
    groups: tuple[str, ...] | None = None
    basis: str = "actual response"

    @property
    def workbook(self) -> Path:
        return REPORTS[self.year]

    @property
    def stem(self) -> str:
        return self.sheet.replace(" ", "").lower()

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.year}/{self.stem}.parquet"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


# The source sheets the fact is built from: 2021-22 carries all cuts; 2019-20 /
# 2020-21 contribute the UG-discipline trend. Table 12 = UG enrolment by
# discipline, Table 35 = UG graduates by discipline (same layout).
#
# Adding a new year: run `inspect_workbook.py --year <new> --all-sheets` FIRST and
# copy the *actual* sheet names in here. AISHE renumbers tables between editions,
# so "33OutTurnState" is not guaranteed to be Table 33 in a later report.
# Social-group column headings, as each edition prints them. Order is load
# bearing. Note 2019-20 has no EWS column (the category starts in 2020-21) and
# labels drift, which is why these are per-sheet rather than one constant.
SOCIAL_XLS_2019 = ("All", "Scheduled Caste", "Scheduled Tribe",
                   "Other Backward Classes", "Persons with Disability", "Muslim",
                   "Other Minority Communities")
SOCIAL_XLS_2020 = ("All Categories", "Scheduled Caste", "Scheduled Tribe",
                   "Other Backward Class", "Persons with Disability", "Muslim",
                   "Other Minority Communities", "EWS")
SOCIAL_XLS_FULL = ("All Categories", "Scheduled Caste", "Scheduled Tribe",
                   "Other Backward Classes", "Persons with Disability", "Muslim",
                   "Other Minority Communities", "EWS")
# The 2019-20 programme table is not broken out by category at all — one
# Male/Female/Total block, which the cross-tab reader handles as a single group.
SOCIAL_XLS_NONE = ("All Categories",)
# 2022-23 moves PwD from 5th to 7th; 2023-24 moves it last AND renames it
# "Persons with Benchmark Disability". Both are positional reads, so both need
# their own tuple — and the rename is absorbed by canonical_social_group.
SOCIAL_XLS_2022_ENR = ("All Categories", "Scheduled Caste", "Scheduled Tribe",
                       "Other Backward Classes", "Muslim",
                       "Other Minority Communities", "Persons with Disability",
                       "EWS")
SOCIAL_XLS_2023_ENR = ("All Categories", "Scheduled Caste", "Scheduled Tribe",
                       "Other Backward Classes", "Muslim",
                       "Other Minority Communities", "EWS",
                       "Persons with Benchmark Disability")
# 2023-24 drops the minority/PwD/EWS columns from its out-turn tables entirely.
SOCIAL_XLS_CASTE4 = ("All Categories", "Scheduled Caste", "Scheduled Tribe",
                     "Other Backward Classes")

RAW_SHEETS: list[RawSheet] = [
    RawSheet("2021-22", "33OutTurnState", "state_level",      "graduates"),
    RawSheet("2021-22", "34a",            "programme_social", "graduates",
             SOCIAL_XLS_FULL),
    RawSheet("2021-22", "35UGDisc",       "ug_discipline",    "graduates"),
    RawSheet("2021-22", "12UGDisc",       "ug_discipline",    "enrolment"),
    RawSheet("2020-21", "35UGDisc",       "ug_discipline",    "graduates"),
    RawSheet("2020-21", "12UGDisc",       "ug_discipline",    "enrolment"),
    RawSheet("2019-20", "35UGDisc",       "ug_discipline",    "graduates"),
    RawSheet("2019-20", "12UGDisc",       "ug_discipline",    "enrolment"),

    # ── Sheets the workbooks always had but nothing read ──────────────────────
    # Cheaper coverage than any PDF: already-clean Excel in files we hold. Found
    # by listing the workbooks' sheet names against RAW_SHEETS.
    #
    # state_level for the two years it was missing.
    RawSheet("2019-20", "33OutTurnState", "state_level",      "graduates"),
    RawSheet("2020-21", "33OutTurnState", "state_level",      "graduates"),
    #
    # The social cut, carried forward from the PDF years to 2021-22. Table 14 is
    # captioned "Estimated" in every edition, so it joins the estimated series.
    RawSheet("2019-20", "14TotalEnrCategory",        "state_social", "enrolment",
             SOCIAL_XLS_2019, BASIS_ESTIMATED),
    RawSheet("2020-21", "14-15TotalEnrCategory",     "state_social", "enrolment",
             SOCIAL_XLS_2020, BASIS_ESTIMATED),
    RawSheet("2021-22", "14-15TotalEnrCategory (2)", "state_social", "enrolment",
             SOCIAL_XLS_FULL, BASIS_ESTIMATED),
    #
    # Table 33a — GRADUATES by state x social group. Same grain as the enrolment
    # social cut, so it shares `state_social` and is told apart by `metric`. Its
    # caption states no basis, but its All Categories column equals Table 33's
    # Grand Total exactly in both years, which makes it actual-response and gives
    # it a built-in anchor.
    RawSheet("2020-21", "33a CategoryOutTurn", "state_social", "graduates",
             SOCIAL_XLS_FULL),
    RawSheet("2021-22", "33a CategoryOutTurn", "state_social", "graduates",
             SOCIAL_XLS_FULL),
    #
    # The programme cut for 2019-20 and 2020-21. 2019-20 prints no category
    # breakdown, so it lands as the All Categories slice, exactly like the PDF
    # years' Table 34.
    RawSheet("2019-20", "34OutTurn Prog", "programme_social", "graduates",
             SOCIAL_XLS_NONE),
    RawSheet("2020-21", "34a",            "programme_social", "graduates",
             SOCIAL_XLS_FULL),

    # ── 2022-23 and 2023-24 ───────────────────────────────────────────────────
    # Reachable at last: the Excel download path was wrong in REPORT_URLS (see the
    # note there), so these two workbooks had never been fetched. Sheet names are
    # renamed again in both editions — hence the exact strings below.
    #
    # NB 2022-23 publishes BOTH "34 Out Turn Prog" (no category split) and "34a"
    # (with it). Only 34a is registered: they are the same population, and taking
    # both would double the programme cut.
    RawSheet("2022-23", "12UGDisc",                    "ug_discipline", "enrolment"),
    RawSheet("2022-23", "35 UG Discipline",            "ug_discipline", "graduates"),
    RawSheet("2022-23", "33 Out Turn",                 "state_level",   "graduates"),
    RawSheet("2022-23", "33 (a)(b) Category Out Turn", "state_social",  "graduates",
             SOCIAL_XLS_FULL),
    RawSheet("2022-23", "14-15TotalEnrCategory (2)",   "state_social",  "enrolment",
             SOCIAL_XLS_2022_ENR, BASIS_ESTIMATED),
    RawSheet("2022-23", "34a",                         "programme_social", "graduates",
             SOCIAL_XLS_FULL),
    #
    # 2023-24 renumbers the programme-by-category table to "Table 35" — its sheet
    # is called "Table 35 (34a E)" but its caption reads "Table 35. Programme-wise
    # Out-turn/Pass-Out at Various Social group", so it is 34a's successor and NOT
    # the UG-discipline Table 35. This edition publishes no UG-discipline out-turn
    # table at all, and drops the minority/PwD/EWS columns from its out-turn cuts.
    RawSheet("2023-24", "12UGDisc",                  "ug_discipline", "enrolment"),
    RawSheet("2023-24", "33 Out Turn",               "state_level",   "graduates"),
    RawSheet("2023-24", "33 (a) Category Out Turn",  "state_social",  "graduates",
             SOCIAL_XLS_CASTE4),
    RawSheet("2023-24", "14-15TotalEnrCategory (2)", "state_social",  "enrolment",
             SOCIAL_XLS_2023_ENR, BASIS_ESTIMATED),
    RawSheet("2023-24", "Table 35 (34a E)",          "programme_social", "graduates",
             SOCIAL_XLS_CASTE4),
    # 2022-23 / 2023-24 — fetch, then inspect_workbook.py, then fill in the real
    # sheet names and uncomment. Left commented rather than guessed: a wrong sheet
    # name here is a silent miss, and the table numbers are likely to have moved.
    # RawSheet("2022-23", "<33?>",  "state_level",      "graduates"),
    # RawSheet("2022-23", "<34a?>", "programme_social", "graduates"),
    # RawSheet("2022-23", "<35?>",  "ug_discipline",    "graduates"),
    # RawSheet("2022-23", "<12?>",  "ug_discipline",    "enrolment"),
]


# ─── State names — one spelling per state, across editions ────────────────────
# AISHE respells states between editions: "Chhatisgarh" then "Chhattisgarh",
# "Uttrakhand" then "Uttarakhand", "Daman & Diu" then "Daman and Diu", and the
# 2021-22 workbook abbreviates "A & N Islands". Left as published, one state
# becomes two values and every per-state trend silently splits in 2017-18.
#
# Genuine boundary changes are NOT mapped away — they are different places:
#   Ladakh                        carved out of Jammu and Kashmir in 2019
#   D & N Haveli and Daman & Diu  the two UTs merged in 2020, so 2021-22 reports
#                                 one row where earlier years report two
# A series spanning those years has to decide how to treat the change; hiding it
# behind a rename would make that decision invisible.
def _load_state_canonical() -> dict[str, str]:
    path = CODEMAPS / "state_canonical.csv"
    if not path.exists():
        return {}
    import csv
    with path.open() as f:
        return {r["as_published"]: r["canonical"] for r in csv.DictReader(f)}


STATE_CANONICAL: dict[str, str] = _load_state_canonical()


def canonical_state(name: str) -> str:
    """Map a published state label to the one spelling used across editions."""
    return STATE_CANONICAL.get(name.strip(), name.strip())


# ─── PDF tables — the parse registry for the historical (pre-Excel) years ─────
# parse_report_pdf.py reads these. Same role as RAW_SHEETS above, for the years
# where no Excel edition exists.
@dataclass(frozen=True)
class PdfTable:
    year: str
    label: str        # the table as printed, for logs — e.g. "T33"
    title_re: str     # regex matching the table's printed caption
    cut: str          # state_level | state_social | programme_social | ug_discipline
    metric: str       # 'graduates' | 'enrolment'
    # Cross-tab column groups, in printed order, for the cuts whose reader is
    # positional. None for the line-based readers (T12/T34/T35), which have a
    # single Male/Female/Total block and so have no groups to verify.
    groups: tuple[str, ...] | None = None
    # Whether the table's figures are the responding institutions' own totals or
    # grossed up to full coverage. AISHE prints this in the caption and the two
    # are DIFFERENT POPULATIONS — see BASIS_* below.
    basis: str = "actual response"

    @property
    def pdf(self) -> Path:
        return PDF_REPORTS[self.year]



# Social categories as printed across Tables 14 and 15. Order matters — the
# cross-tab read is positional — and the labels match the Excel-era
# SOCIAL_CATEGORIES vocabulary so both eras share one dimension.
SOCIAL_T14 = ("All Categories", "Scheduled Caste", "Scheduled Tribe",
              "Other Backward Classes")
SOCIAL_T15 = ("Persons with Disability", "Muslim", "Other Minority Communities")

# Tables are located by their printed caption, not a page number — pagination
# moves between editions but the captions are stable. The separator after the
# table number varies ('.' in 2015-18, ':' in 2018-19), hence `[.:]`.
T12 = ("T12", r"Table\s*12\s*[.:]\s*Enrolment at Under Graduate",
       "ug_discipline", "enrolment")
T14 = ("T14", r"Table\s*14\s*[.:]\s*Estimated State[-‐‑‒–]?\s*wise Enrolment",
       "state_social", "enrolment", SOCIAL_T14, BASIS_ESTIMATED)
T15 = ("T15", r"Table\s*15\s*[.:]\s*State[-‐‑‒–]?\s*wise Enrolment in PWD",
       "state_social", "enrolment", SOCIAL_T15, BASIS_ESTIMATED)
T33 = ("T33", r"Table\s*33\s*[.:]\s*State-wise Out-?turn",
       "state_level", "graduates")
T34 = ("T34", r"Table\s*34\s*[.:]\s*Programme-wise Out-?turn",
       "programme_social", "graduates")
T35 = ("T35", r"Table\s*35\s*[.:]\s*Out-?turn/Pass-Out at Under Graduate",
       "ug_discipline", "graduates")

# Registered (year, table) pairs — ONLY those whose parse reconciles exactly
# against the table's own published Grand Total. parse_report_pdf.py refuses to
# emit a table that doesn't reconcile, so anything listed here has been checked
# cell-for-cell against the report, and anything commented out below is a known
# gap rather than an oversight.
#
# All four editions print tables 12/33/34/35 with matching captions, but they do
# NOT all lay them out the same way, so this is deliberately not a cross product.
#
# NOT YET INGESTED, with the reason each fails its check. T34's population is the
# same as T33's Grand Total, so the deltas below are measured against that — an
# external anchor that works even for the editions printing no Grand Total of
# their own. clean_aishe._check_programme_vs_state enforces it on every build.
#
#   (2015-16, T34)  parses 3,825,596 Male against T33's 4,463,710 (-638,114).
#                   A large block of programmes is missing, not a stray row — this
#                   edition needs its layout looked at before anything else.
#   (2016-17, T34)  parses 4,397,315 against 4,398,169 (-854). Very close; likely
#                   a handful of rows still printing fewer than three figures in a
#                   shape _sparse_row does not yet accept.
#   (2017-18, T34)  sums to 4,315,863 Male vs its own published 4,323,271
#                   (-7,408).
#   (2017-18, T12)  disciplines sum to 14,891,226 Male vs published 14,852,574
#                   (+38,652). One subject row is being taken as a discipline;
#                   this edition indents the discipline/subject columns
#                   differently from the other three.
#   (2016-17, T35)  NOT a ranked list — that earlier note was wrong, and looking at
#   (2017-18, T35)  the rendered page is what corrected it. The layout is the
#                   standard discipline/subject hierarchy, same shape as Table 12.
#                   The real defect is a constant ONE-ROW VERTICAL OFFSET between
#                   the label column and the value columns, so pdfplumber's line
#                   banding pairs every label with the NEXT row's figures:
#
#                     'Journalism & Mass Communication'          <- values missing
#                     'Social Work 2831 2372 5203'               <- Journalism's
#                     'Fashion Technology 2573 2567 5140'        <- Social Work's
#                     'Grand Total 314264395 33137378 645638463' <- two rows merged
#
#                   Hence the absurd "published Grand Total" of 314,264,395: the
#                   last data row's digits are merged into the total's.
#                   THE FIX is to pair the k-th label with the k-th value-triple by
#                   rank down the page rather than by text-line banding — a constant
#                   offset is exactly what banding cannot survive. Wrapped labels
#                   would break naive rank-pairing, so count both columns first and
#                   only rank-pair when they agree.
#                   A good anchor already exists: this table's Grand Total equals
#                   Table 33's Under Graduate level (3,142,649 Male for 2016-17,
#                   confirmed against the page).
#                   Do NOT transcribe these from the image. That freezes the
#                   figures, breaks on the next edition, and leaves the rows checked
#                   only against a total read by the same fallible eye.
#
#   (2018-19, T34)  FIXED and registered. Was -51: nine rows printing fewer than
#                   three figures (a blank gender cell, or no out-turn at all)
#                   were dropped whole. _sparse_row now reads them, and the result
#                   matches T33's Grand Total exactly on all three genders.
#
#   Tables 14 and 15 (the social-category cut) are registered for all seven
#   editions — unlike 12/33/34/35 they are laid out identically throughout, and
#   each reconciles against its own published All India row per category.
PDF_TABLES: list[PdfTable] = [
    PdfTable(year, *spec)
    for year, spec in [
        ("2012-13", T14), ("2012-13", T15),
        ("2013-14", T14), ("2013-14", T15),
        ("2014-15", T14), ("2014-15", T15),
        ("2015-16", T12), ("2015-16", T33), ("2015-16", T34), ("2015-16", T35),
        ("2015-16", T14), ("2015-16", T15),
        ("2016-17", T12), ("2016-17", T33),
        ("2016-17", T14), ("2016-17", T15),
        ("2017-18", T33),
        ("2017-18", T14), ("2017-18", T15),
        ("2018-19", T12), ("2018-19", T33), ("2018-19", T34), ("2018-19", T35),
        ("2018-19", T14), ("2018-19", T15),
    ]
]
