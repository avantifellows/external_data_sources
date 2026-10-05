"""
Jamia Millia Islamia UG admission (CUET) cut-offs — source configuration.

Source: JMI's 2025-26 selection lists for its nine CUET-based UG programmes
(admission.jmi.ac.in/application/assets/uploadedResults/UG1/CUET_<code>_SL<n>.pdf),
whose last pages print a category-wise cut-off table, and the University
Prospectus 2025-26 (p. 139: the CUET paper each programme counts).

The lists' candidate pages carry roll / registration / application numbers:
kept private for provenance, never published; only the cut-off tables are.

GCS layout:
    gs://avantifellows-external-data/jamiaug/raw/<file>
    gs://avantifellows-external-data/jamiaug/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CLEAN = ROOT / "clean"
YEAR = 2025

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "jamiaug"
BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"

# programme code -> (programme, CUET paper counted)  [Prospectus 2025-26 p. 139]
PROGRAMS = {
    "B28": ("B.A. (Hons.) Turkish Language & Literature", "General Test"),
    "B30": ("B.A. (Hons.) Sanskrit", "General Test"),
    "B60": ("B.A. (Hons.) French & Francophone Studies", "General Test"),
    "B61": ("B.A. (Hons.) Spanish & Latin American Studies", "General Test"),
    "B29": ("B.A. (Hons.) Hindi", "Hindi"),
    "B35": ("B.A. (Hons.) Urdu", "Urdu"),
    "B58": ("B.A. (Hons.) Korean Language", "General Test"),
    "B66": ("B.Sc. (Hons.) Applied Mathematics", "Mathematics"),
    "B64": ("B.Sc. (Multidisciplinary)", "General Test"),
}
# lists published per programme (SL1.. until the first missing one)
LISTS = {"B28": 3, "B29": 3, "B30": 1, "B35": 3, "B58": 3, "B60": 3, "B61": 3, "B64": 3, "B66": 3}
LIST_URL = "https://admission.jmi.ac.in/application/assets/uploadedResults/UG1/{name}"
PROSPECTUS = ("University_Prospectus_2025-2026.pdf",
              "https://admission.jmi.ac.in/application/assets/pdfFile/prospectus/UniversityProspectus/University_Prospectus_2025-2026.pdf")


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str
    role: str                 # list / rules
    code: str | None = None
    list_no: int | None = None
    has_ids: bool = False     # candidate roll / application numbers

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"


RAW_FILES = [RawFile(f"CUET_{c}_SL{n}.pdf", LIST_URL.format(name=f"CUET_{c}_SL{n}.pdf"), "list", c, n, True)
             for c, k in LISTS.items() for n in range(1, k + 1)] + [RawFile(*PROSPECTUS, "rules")]


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
    def local_path(self) -> Path:
        return CLEAN / self.parquet

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"


TABLES = [Table("jamiaug_fact_cutoffs", "jamiaug_fact_cutoffs.parquet", "(program_code, list_no, category)")]
