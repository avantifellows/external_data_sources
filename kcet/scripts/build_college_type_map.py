"""Build the auditable 2025 KEA college-code classification codemap.

The June 2025 draft engineering seat matrix classifies institutions by
annexure, but does not print KCET college codes. We therefore join its
institution headings to the code-bearing Round 3 cutoff CSV only when the
normalized institution name is contained exactly in the cutoff label.

Some institutions occur in more than one annexure because KEA assigns
different codes to aided, unaided, and university course groups. Seven such
codes are disambiguated below using their distinct course lists. Codes that
cannot be established from these primary files remain Unknown.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
CODEMAP = ROOT / "codemaps" / "college_type_2025.csv"

CUTOFF_FILE = "KA_engg_2025_all_cutoffs_R3.csv"
CUTOFF_PDF_FILE = "KA_engg_2025_GEN_R3.pdf"
CUTOFF_PDF_URL = (
    "https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/"
    "PROF_CODE_E_R_11092025english.pdf"
)
MATRIX_FILE = "KA_engg_2025_draft_seat_matrix.pdf"
MATRIX_URL = (
    "https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/"
    "UG_Seat_Matrix_2025english.pdf"
)

ANNEXURE_TYPES = {
    "A": "Government",
    "B": "Government-Aided",
    "C": "Private Unaided",
    "D": "Private Unaided Minority",
    "O": "Private University",
}

NORMALIZED_TYPES = {
    "Government": "Govt",
    "Government-Aided": "Govt-Aided",
    "Private Unaided": "Private",
    "Private Unaided Minority": "Private",
    "Private University": "Private",
    "Unknown": "Unknown",
}

# Each code below shares its institution name with another KEA code. The
# asserted course signature identifies the matching 2025 matrix annexure.
COURSE_DISAMBIGUATIONS = {
    "E003": ("Government-Aided", 11, "INDUSTRIAL ENGINEERING & MANAGEMENT"),
    "E048": ("Private Unaided", 19, "ARTIFICIAL INTELLIGENCE AND DATA SCIENCE"),
    "E031": ("Government-Aided", 11, "ELECTRICAL & ELECTRONICS ENGINEERING"),
    "E049": ("Private Unaided", 20, "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING"),
    "E041": ("Government-Aided", 11, "INDUSTRIAL & PRODUCTION ENGINEERING"),
    "E059": ("Private Unaided", 52, "CERAMICS & CEMENT ENGINEERING"),
    "E284": ("Private Unaided", 67, "COMPUTER SCIENCE AND ENGINEERING"),
}

# UBDT has an inserted ``(H.GOV)`` marker and a spelling variant in the cutoff
# label, so exact containment cannot match it. The distinctive institution
# name is manually tied to its entry in Government Annexure A.
VERIFIED_NAME_ALIASES = {
    "E066": ("Government", 9, "University B.D.T College of Engineering, Davanagere"),
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).upper()
    value = value.replace("&", " AND ")
    value = re.sub(r"\bENGG\b", "ENGINEERING", value)
    value = re.sub(r"\bTECH\b", "TECHNOLOGY", value)
    value = re.sub(r"\bINST(?:ITUTE)?\b", "INSTITUTE", value)
    value = re.sub(r"\bUNIV(?:ERSITY)?\b", "UNIVERSITY", value)
    value = re.sub(r"\bCOLL\b", "COLLEGE", value)
    value = re.sub(r"[^A-Z0-9]+", " ", value)
    return " ".join(value.split())


def extract_matrix_institutions(path: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    with pdfplumber.open(path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            annexure_match = re.search(r"ANNEXURE\s*:\s*([A-Z])", text)
            if not annexure_match or annexure_match.group(1) not in ANNEXURE_TYPES:
                continue
            annexure = annexure_match.group(1)
            for match in re.finditer(r"(?m)^(\d+)\s+(.+?)\nAddress\s*:", text):
                rows.append(
                    {
                        "annexure": annexure,
                        "college_type_detail": ANNEXURE_TYPES[annexure],
                        "matrix_number": int(match.group(1)),
                        "matrix_name": match.group(2).strip(),
                        "source_page": page_number,
                    }
                )
    matrix = pd.DataFrame(rows).drop_duplicates(
        ["annexure", "matrix_number", "matrix_name"]
    )
    matrix["normalized_name"] = matrix["matrix_name"].map(normalize)
    expected = {
        "Government": 21,
        "Government-Aided": 3,
        "Private Unaided": 140,
        "Private Unaided Minority": 14,
        "Private University": 25,
    }
    actual = matrix["college_type_detail"].value_counts().to_dict()
    if actual != expected:
        raise ValueError(f"Seat-matrix anchors changed: expected {expected}, got {actual}")
    return matrix


def _record(
    code: str,
    name: str,
    detail: str,
    method: str,
    page: int | None,
    evidence_name: str,
    *,
    cutoff_label: bool = False,
) -> dict[str, object]:
    return {
        "college_code": code,
        "college_name_2025": name,
        "college_type": NORMALIZED_TYPES[detail],
        "college_type_detail": detail,
        "classification_method": method,
        "classification_source_file": CUTOFF_PDF_FILE if cutoff_label else MATRIX_FILE,
        "classification_source_url": CUTOFF_PDF_URL if cutoff_label else MATRIX_URL,
        "classification_source_page": page,
        "classification_evidence": evidence_name,
    }


def build() -> pd.DataFrame:
    cutoffs = pd.read_csv(
        RAW / CUTOFF_FILE, dtype={"college_code": "string"}
    )
    colleges = cutoffs[["college_code", "college_name"]].drop_duplicates()
    if len(colleges) != 229 or colleges["college_code"].duplicated().any():
        raise ValueError("Expected exactly one cutoff label for each of 229 college codes")
    colleges["normalized_name"] = colleges["college_name"].map(normalize)
    matrix = extract_matrix_institutions(RAW / MATRIX_FILE)

    rows: list[dict[str, object]] = []
    for college in colleges.sort_values("college_code").itertuples(index=False):
        candidates = matrix[
            matrix["normalized_name"].map(
                lambda matrix_name: (
                    matrix_name in college.normalized_name
                    or college.normalized_name in matrix_name
                )
            )
        ]
        candidate_types = sorted(candidates["college_type_detail"].unique())

        if college.college_code in COURSE_DISAMBIGUATIONS:
            detail, page, signature = COURSE_DISAMBIGUATIONS[college.college_code]
            courses = set(
                cutoffs.loc[
                    cutoffs["college_code"] == college.college_code, "course_name"
                ]
            )
            if signature not in courses:
                raise ValueError(
                    f"{college.college_code} lost disambiguating course {signature!r}"
                )
            if college.college_code == "E284" and courses != {signature}:
                raise ValueError(
                    "E284 is only disambiguated while its complete course set is CSE"
                )
            evidence = candidates[
                (candidates["college_type_detail"] == detail)
                & (candidates["source_page"] == page)
            ]
            if evidence.empty:
                raise ValueError(f"Missing matrix evidence for {college.college_code}")
            rows.append(
                _record(
                    college.college_code,
                    college.college_name,
                    detail,
                    "course-list disambiguation",
                    page,
                    f"{evidence.iloc[0]['matrix_name']}; signature: {signature}",
                )
            )
        elif college.college_code in VERIFIED_NAME_ALIASES:
            detail, page, matrix_name = VERIFIED_NAME_ALIASES[college.college_code]
            evidence = matrix[
                (matrix["college_type_detail"] == detail)
                & (matrix["source_page"] == page)
                & (matrix["matrix_name"] == matrix_name)
            ]
            if len(evidence) != 1:
                raise ValueError(f"Missing alias evidence for {college.college_code}")
            rows.append(
                _record(
                    college.college_code,
                    college.college_name,
                    detail,
                    "verified name variant",
                    page,
                    matrix_name,
                )
            )
        elif college.college_code == "E001":
            marker = "STATE AUTONOMOUS PUBLIC UNIVERSITY"
            if marker not in normalize(college.college_name):
                raise ValueError("E001 lost its explicit public-university marker")
            rows.append(
                _record(
                    college.college_code,
                    college.college_name,
                    "Government",
                    "explicit cutoff label",
                    None,
                    marker.title(),
                    cutoff_label=True,
                )
            )
        elif len(candidate_types) == 1:
            evidence = candidates.iloc[0]
            rows.append(
                _record(
                    college.college_code,
                    college.college_name,
                    candidate_types[0],
                    "exact normalized name containment",
                    int(evidence["source_page"]),
                    str(evidence["matrix_name"]),
                )
            )
        else:
            reason = (
                "ambiguous across matrix annexures"
                if len(candidate_types) > 1
                else "not identified in June 2025 draft matrix"
            )
            rows.append(
                _record(
                    college.college_code,
                    college.college_name,
                    "Unknown",
                    "unclassified",
                    None,
                    reason,
                )
            )

    result = pd.DataFrame(rows)
    if len(result) != 229 or result["college_code"].duplicated().any():
        raise ValueError("Codemap must contain each of the 229 college codes exactly once")
    expected_counts = {
        "Private": 174,
        "Govt": 24,
        "Govt-Aided": 3,
        "Unknown": 28,
    }
    actual_counts = result["college_type"].value_counts().to_dict()
    if actual_counts != expected_counts:
        raise ValueError(
            f"Classification anchors changed: expected {expected_counts}, got {actual_counts}"
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate committed codemap")
    args = parser.parse_args()
    result = build()

    if args.check:
        committed = pd.read_csv(CODEMAP, dtype={"college_code": "string"})
        pd.testing.assert_frame_equal(result, committed, check_dtype=False)
        print(f"Validated {CODEMAP}: {len(result)} codes")
    else:
        CODEMAP.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(CODEMAP, index=False)
        print(f"Written {CODEMAP}: {len(result)} codes")
    print(result["college_type"].value_counts().to_string())
    print("\nDetails:")
    print(result["college_type_detail"].value_counts().to_string())


if __name__ == "__main__":
    main()
