"""
Maharashtra B.Arch (Architecture) CAP closing-ranks pipeline (2025-26).

Authority: State CET Cell Maharashtra
Portal:    https://arch2025.mahacet.org.in/
Source:    Per-institute provisional allotment PDFs, one PDF per
           (institute × CAP round). 59 institutes × 4 rounds = 236 PDFs
           (we got 234 — institute 6245 had no R1/R2 allotments).

PDF format (different from engineering):
  - Per-candidate allotment list (1 row per allotted seat)
  - Header block: college code/name, branch code/name, Status, sanctioned intake
  - Quota section header (e.g. "Home University Seats Allotted to Home University Candidates")
  - Body row: SrNo, MeritNo, MeritScore, ApplicationID, Name, Gender (M/F),
    Category (e.g., OPEN, OBC, SC, SBC/OBC$, SEBC$, etc.), SeatType (e.g., LOPENH, GOBCH)
  - The SeatType column is what we want — it's the same MH category code
    we use for engineering (G/L prefix + caste + H/O/S suffix).

Closing rank methodology:
  - For each (college, branch, quota_section, seat_type), take MAX(MeritNo)
    across all 4 CAP rounds → that's the closing rank.
  - This is consistent with the methodology applied to engineering and pharmacy.

Output: standard schema CSVs in extracted_data/.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "MH" / "architecture" / "pdfs"
INSTITUTE_LIST = ROOT / "source" / "MH" / "architecture" / "arch_institutes.tsv"
OUT = ROOT / "extracted_data"
STATE_CODE = "MH"
YEAR = 2025
CET_NAME = "MAH-AAC-CET / NATA"
SOURCE_URL = "https://arch2025.mahacet.org.in/"
STREAM = "architecture"
OUT_PREFIX = "arch"

QUOTA_SECTIONS = {
    "State Level": "State Level",
    "Home University Seats": "Home → (group)",  # umbrella label
    "Home University Seats Allotted to Home University Candidates": "Home → Home",
    "Home University Seats Allotted to Other Than Home University Candidates": "Home → Other",
    "Other Than Home University Seats Allotted to Other Than Home University Candidates": "Other → Other",
    "Other Than Home University Seats Allotted to Home University Candidates": "Other → Home",
    "All India Seats Allotted to All India Candidates": "All India",
    "Minority Seats Allotted to Minority Candidates": "Minority",
    "Institute Seats": "Institute",
}

# Allotment row pattern:
#   1   25   156.60   AR25101615  VATSALYA SARVESH PATHAK   F   OPEN   ^ LOPENH
# SrNo MeritNo MeritScore Application Name (variable spaces) Gender Cat SeatType
ALLOT_PATTERN = re.compile(
    r"^\s*(\d{1,5})\s+"                       # SrNo
    r"(\d{1,7})\s+"                           # MeritNo  (= state merit / AI rank)
    r"([\d.]+)\s+"                            # MeritScore (NATA / merit total)
    r"(AR\d+|[A-Z]{1,4}\d+)\s+"               # Application ID (AR25... typical)
    r"(.+?)\s+"                               # Name
    r"([MF])\s+"                              # Gender
    r"([A-Z][A-Z/$#0-9-]*)\s+"                # Category (raw cat, may have $/#/SC/OBC/SBC/OBC$)
    r"[*@~^&]\s*"                             # color marker (^/~/*/@ etc.)
    r"([A-Z]{4,12})\s*$"                      # SeatType (e.g., LOPENH, GOBCH)
)


def _pdftotext(pdf: Path) -> str:
    res = subprocess.run(
        ["pdftotext", "-layout", str(pdf), "-"],
        capture_output=True, text=True, check=True,
    )
    return res.stdout


def parse_arch_pdf(pdf_path: Path, round_label: str) -> list[dict]:
    """Parse one B.Arch CAP-round allotment PDF (per-candidate rows)."""
    text = _pdftotext(pdf_path)
    rows: list[dict] = []

    college_code = college_name = None
    branch_code = branch_name = None
    status = None
    quota_section = None

    for raw in text.splitlines():
        ln = raw.rstrip()
        stripped = ln.strip()
        if not stripped:
            continue

        # Skip page header/footer
        if stripped.startswith(("Government of Maharashtra",
                                "State Common Entrance",
                                "Provisional Allotment List",
                                "Full Time Degree Course",
                                "Sanction Intake:",
                                "Legends for SeatType",
                                "PWDR:", "Merit No",
                                "* Green", "@ Blue", "~ Red", "^ Gray", "& Black",
                                "Page ")):
            continue

        # College header — variant: "3019 Sir J. J. College of Architecture, Mumbai"
        m = re.match(r"^(\d{4,5})\s+([A-Z][^\d].+)$", stripped)
        if m and college_code != m.group(1):
            college_code = m.group(1)
            college_name = m.group(2).strip()
            continue

        # Branch header: "0301903210 - Architecture"
        m = re.match(r"^(\d{10})\s*-\s*(.+)$", stripped)
        if m:
            branch_code = m.group(1)
            branch_name = m.group(2).strip()
            continue

        # Status line: "Status: Government-Aided ... Home University: Mumbai University"
        m = re.match(r"^Status:\s*([^\n]+?)(?:\s*Home University:.*)?$", stripped)
        if m:
            status = m.group(1).strip()
            continue

        # Skip column header line (contains all of "SrNo", "MeritNo", "Merit Score", etc.)
        if all(k in stripped for k in ("SrNo", "MeritNo", "Merit Score", "SeatType")):
            continue

        # Quota section header (string match)
        if stripped in QUOTA_SECTIONS:
            quota_section = QUOTA_SECTIONS[stripped]
            continue

        # Allotment row
        am = ALLOT_PATTERN.match(ln)
        if am and college_code and branch_code and quota_section:
            sr, merit_no, merit_score, app_id, name, gender, cat, seat_type = am.groups()
            rows.append({
                "round": round_label,
                "sr_no": int(sr),
                "merit_no": int(merit_no),
                "merit_score": float(merit_score),
                "application_id": app_id,
                "candidate_name": name.strip(),
                "gender": gender,
                "category_raw_input": cat,        # candidate's declared category
                "seat_type": seat_type,           # this is what we treat as the cell category
                "college_code": college_code,
                "college_name": college_name,
                "branch_code": branch_code,
                "branch_name": branch_name,
                "status": status,
                "quota_section": quota_section,
            })

    return rows


def normalise_seat_type(seat_type: str) -> tuple[str, str, str]:
    """Map MH seat-type code → (canonical_category, gender, sub_pool).
    Same logic as engg/pharm parser."""
    c = seat_type.upper()
    if c == "TFWS":  return ("OTHER", "All", "TFWS")
    if c == "ORPHAN":return ("OTHER", "All", "ORPHAN")
    if c.startswith("DEFR"): return ("OTHER", "All", "DEFR")
    if c.startswith("DEF"):  return ("OTHER", "All", "DEF")
    if c.startswith("PWD"):
        body = c[3:]
        if body.startswith("R"): body = body[1:]
        cat, _, _ = _decode_body(body)
        return (cat, "All", "PWD")
    if c == "EWS":  return ("EWS", "All", "")
    if c in ("MI", "MINO", "MIH", "MIO", "MIS"): return ("OTHER", "All", "MIN")
    if c[0] in ("G", "L"):
        gender = "Boys" if c[0] == "G" else "Girls"
        body = c[1:]
        cat, _, _ = _decode_body(body)
        return (cat, gender, "")
    return ("OTHER", "All", "UNKNOWN")


def _decode_body(body: str) -> tuple[str, str, str]:
    if body and body[-1] in ("H", "O", "S"):
        sub = body[-1]
        mid = body[:-1]
    else:
        sub, mid = "", body
    mapping = {
        "OPEN": "GEN", "OBC": "OBC-NCL", "SC": "SC", "ST": "ST", "EWS": "EWS",
        "VJ": "OTHER", "NT1": "OTHER", "NT2": "OTHER", "NT3": "OTHER",
        "NTD": "OTHER", "SEBC": "OTHER", "SBC": "OTHER", "MI": "OTHER",
        "MIN": "OTHER",
    }
    return (mapping.get(mid, "OTHER"), mid, sub)


def classify_college_type(status: str | None) -> str:
    if not status: return "Unknown"
    s = status.strip()
    if s.startswith("Un-Aided"):
        return "Private-Minority" if "Minority" in s else "Private-Unaided"
    if s.startswith("Government-Aided"): return "Govt-Aided"
    if s.startswith("Government"): return "Govt"
    if s.startswith("University"): return "State-Univ-Dept"
    if s.startswith("Deemed"): return "Deemed"
    return "Other"

GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing 234 architecture allotment PDFs (4 rounds × 59 institutes)")
    pdfs = sorted(SOURCE.glob("MH_arch_CAP*.pdf"))
    all_rows = []
    for p in pdfs:
        m = re.match(r"MH_arch_CAP(\d)_(\d+)\.pdf", p.name)
        if not m:
            continue
        rlabel = f"R{m.group(1)}"
        rows = parse_arch_pdf(p, rlabel)
        all_rows.extend(rows)
    print(f"  Total allotment rows parsed: {len(all_rows):,}")

    df = pd.DataFrame(all_rows)
    if df.empty:
        print("ERROR: no rows parsed")
        return

    df.to_csv(OUT / f"{STATE_CODE}_{OUT_PREFIX}_all_allotments_{YEAR}.csv", index=False)
    print(f"  Distinct (college × branch × quota × seat_type): "
          f"{df.groupby(['college_code','branch_code','quota_section','seat_type']).ngroups:,}")

    print("\nStage 2 — closing ranks (MAX MeritNo per cell across rounds)")
    agg = (df.groupby(
        ["college_code", "college_name", "branch_code", "branch_name",
         "status", "quota_section", "seat_type"], dropna=False)
        .agg(closing_rank=("merit_no", "max"),
             opening_rank=("merit_no", "min"),
             closing_score=("merit_score", "min"),  # lower merit_no = higher score
             opening_score=("merit_score", "max"),
             allotted_count=("merit_no", "count"))
        .reset_index())
    last_round = (df.sort_values("merit_no", ascending=False)
                    .drop_duplicates(["college_code", "branch_code", "quota_section", "seat_type"])
                    [["college_code", "branch_code", "quota_section", "seat_type", "round"]]
                    .rename(columns={"round": "last_round_with_max"}))
    agg = agg.merge(last_round, on=["college_code", "branch_code", "quota_section", "seat_type"])

    cat_norm = agg["seat_type"].apply(lambda s: pd.Series(normalise_seat_type(s)))
    cat_norm.columns = ["category", "gender", "sub_pool"]
    agg = pd.concat([agg, cat_norm], axis=1)

    agg["state"] = "MAHARASHTRA"
    agg["cet_name"] = CET_NAME
    agg["stream"] = STREAM
    agg["year"] = YEAR
    agg["round"] = "R1+R2+R3+R4 (cumulative)"
    agg["quota"] = agg["quota_section"]
    agg["rank_basis"] = "MH AAC-CET / NATA State Merit Rank"
    agg["source_url"] = SOURCE_URL
    agg["college_type"] = agg["status"].apply(classify_college_type)

    cols_out = [
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type", "status",
        "branch_code", "branch_name",
        "quota", "seat_type", "category", "gender", "sub_pool",
        "opening_rank", "closing_rank", "opening_score", "closing_score",
        "allotted_count", "last_round_with_max",
        "rank_basis", "source_url",
    ]
    out_all = agg[cols_out].sort_values(["college_code", "branch_code", "quota", "seat_type"])
    out_all.to_csv(
        OUT / f"{STATE_CODE}_{OUT_PREFIX}_state_quota_closing_ranks_{YEAR}.csv", index=False
    )
    print(f"  closing-rank rows (all institutes):  {len(out_all):,}")

    govt = out_all[out_all["college_type"].isin(GOVT_TYPES)].copy()
    govt.to_csv(
        OUT / f"{STATE_CODE}_{OUT_PREFIX}_state_quota_closing_ranks_govt_{YEAR}.csv", index=False
    )
    print(f"  by college_type:")
    for t, n in out_all.college_type.value_counts().items():
        print(f"    {t:20s} {n:>5,}")
    print(f"  unique govt-scope colleges:          {govt['college_code'].nunique()}")
    print(f"  unique govt-scope college × branch:  {govt.groupby(['college_code','branch_code']).ngroups}")

    # Schema-canonical 5-cat consolidated
    print("\nStage 3 — schema-canonical 5-cat consolidated")
    canon = govt[
        (govt["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"]))
        & (govt["sub_pool"].isna() | (govt["sub_pool"] == ""))
    ].copy()
    canon = (canon.groupby(
        ["state", "cet_name", "stream", "year", "round",
         "college_code", "college_name", "college_type",
         "branch_code", "branch_name",
         "quota", "category", "gender"], dropna=False)
        .agg(opening_rank=("opening_rank", "min"),
             closing_rank=("closing_rank", "max"),
             last_round_with_max=("last_round_with_max",
                                   lambda s: s.value_counts().index[0]))
        .reset_index())
    canon["rank_basis"] = "MH AAC-CET / NATA State Merit Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_{OUT_PREFIX}_consolidated_5cat_govt_{YEAR}.csv", index=False
    )
    print(f"  consolidated 5-cat rows:             {len(canon):,}")

    # Sanity check
    print("\n=== Architecture sanity (govt scope, GOPENH/LOPENH/State Level) ===")
    sample = govt[govt["seat_type"].isin(["GOPENH", "LOPENH", "GOPENS", "LOPENS"])].sort_values("closing_rank").head(10)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "seat_type", "closing_rank", "last_round_with_max"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
