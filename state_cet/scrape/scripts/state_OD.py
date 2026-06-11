"""
Odisha OJEE — engineering closing-ranks pipeline.

Authority:  OJEE Cell, Odisha (engineering counselling under SAMS Odisha)
Portal:     https://ojee.nic.in/  (rolled to 2026 mode; 2025 BTECH OR-CR
            never published as a public PDF)
Source:     OJEE 2024 BTECH/BARCH/BPLAN/IntMSc/BCAT Opening-Closing Rank
            consolidated PDF, re-hosted on the NIC SaaS bucket as 2025-cycle
            reference document at
              cdnbbsr.s3waas.gov.in/s36832a7b24bc06775d02b7406880b93fc/
                uploads/2025/05/2025052291.pdf
            (60 pages, ~1.15 MB, dated 22-May-2025)

⚠ 2025 OJEE actual closing ranks are gated behind candidate login —
not publicly downloadable. Same conclusion as the medical-side
state counselling for OD. We use 2024 OR-CR as PROXY for 2025 (same
precedent as KA → 2024, AP → 2022, RJ medical → 2024).

PDF format (text-extracted via pdftotext -layout):
  Each row is whitespace-separated:
    INSTITUTE NAME | STREAM (full branch name) | QUOTA (HS) | CATEGORY |
    SEAT TYPE | OPENING RANK | CLOSING RANK
  Rank numbers are NEET/JEE-style state ranks (state-domicile merit position).

Reservation taxonomy (Odisha):
  Vertical: General (UR) / SC / ST / OBC / SEBC / EWS / TFW
  Horizontal: Gender Neutral / Female Only (33% women's reservation)
  Quota: HS (Home State / Odisha domicile) only in this PDF;
         All-India seats handled separately by JoSAA-equivalent

For canonical 5-cat mapping:
  General      → GEN
  SEBC, OBC    → OBC-NCL  (Odisha SEBC is OBC-equivalent)
  SC           → SC
  ST           → ST
  EWS          → EWS
  TFW          → flagged via sub_pool

For Avanti JNV OD student:
  - JNV is Central govt school. OD has no horizontal "govt school"
    reservation. Compete in regular state quota under their OD-specific
    caste category.

Methodology:
  - 2024 OR-CR is the LATEST publicly downloadable cutoff data
  - Includes Round 1 + Round 2 + Mop-up cumulative (per OJEE convention,
    OR-CR table reflects the final closing position after all main rounds)
  - Stray rounds excluded (not in the OR-CR table by design)

Output (to extracted_data/):
  - OD_engg_all_cutoffs_2024.csv         — long format
  - OD_engg_closing_ranks_govt_2024.csv  — govt scope
  - OD_engg_consolidated_5cat_govt_2024.csv  — schema-canonical
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source" / "OD" / "engineering"
OUT = ROOT / "extracted_data"
STATE_CODE = "OD"
DATA_YEAR = 2024  # 2024 OR-CR used as proxy for 2025
CET_NAME = "OJEE"
SOURCE_URL = ("https://cdnbbsr.s3waas.gov.in/s36832a7b24bc06775d02b7406880b93fc/"
              "uploads/2025/05/2025052291.pdf")
PDF_FILE = "OD_OJEE_2024_BTECH_ORCR.pdf"


# Match any line that ends with "<int> <int>" preceded by SEAT TYPE,
# preceded by CATEGORY, etc. We use a multi-step approach because the
# stream column is freeform-text with many spaces.
#
# Strategy: split each line by whitespace runs (\s{2,}) — pdftotext -layout
# uses multiple spaces to separate columns. The line columns will be:
#   [Institute, Stream, HS, Category, SeatType, Opening, Closing]
# Some lines wrap stream name to next physical line — handle by buffering.

CATEGORIES_OD = {
    "General", "SC", "ST", "OBC", "SEBC", "EWS", "TFW", "PWD",
    "GENERAL-PWD", "SC-PWD", "ST-PWD",
}

SEAT_TYPES_OD = {"Gender Neutral", "Female Only"}


def parse_od_pdf_text(pdf_path: Path) -> list[dict]:
    out = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    rows = []
    pending_lines: list[str] = []   # for wrapped stream names
    for raw in out.splitlines():
        ln = raw.rstrip()
        if not ln.strip():
            pending_lines = []
            continue
        # Skip page headers
        if "OJEE 2024" in ln or "OPENING AND CLOSING RANK" in ln:
            pending_lines = []
            continue
        if ln.lstrip().startswith("INSTITUTE NAME"):
            pending_lines = []
            continue
        if "OPENING" in ln and "CLOSING" in ln:
            pending_lines = []
            continue
        # Try to extract a complete row: line should end with two integers
        m = re.search(r"\s+(\d{1,7})\s+(\d{1,7})\s*$", ln)
        if not m:
            # Possibly a wrapped stream-name continuation line. Buffer.
            pending_lines.append(ln)
            continue
        opening, closing = int(m.group(1)), int(m.group(2))
        body = ln[: m.start()]
        # If we have buffered lines, prepend them (this catches wrapped streams)
        if pending_lines:
            body = "  ".join(pending_lines) + "  " + body
            pending_lines = []
        # Split body by 2+ spaces — get column tokens
        cols = re.split(r"\s{2,}", body.strip())
        if len(cols) < 5:
            continue
        # Reconstruct: institute, stream..., quota=HS, category, seat_type
        # Find where "HS" appears among columns
        hs_idx = None
        for i, c in enumerate(cols):
            if c.strip() == "HS":
                hs_idx = i
                break
        if hs_idx is None or hs_idx < 1 or hs_idx + 2 >= len(cols):
            continue
        institute = cols[0].strip()
        stream = " ".join(c.strip() for c in cols[1:hs_idx]).strip()
        category = cols[hs_idx + 1].strip()
        seat_type = cols[hs_idx + 2].strip()
        if not institute or not stream:
            continue
        rows.append({
            "college_name": institute,
            "branch_name": stream,
            "quota": "HS (Home State)",
            "category_raw": category,
            "seat_type": seat_type,
            "opening_rank": opening,
            "closing_rank": closing,
        })
    return rows


# Govt engineering institutions in Odisha
OD_GOVT_PATTERNS = [
    (r"^BIJU PATNAIK UNIVERSITY OF TECHNOLOGY",                "State-Univ-Dept"),
    (r"^BPUT\b",                                                "State-Univ-Dept"),
    (r"^GOVERNMENT COLLEGE OF ENGINEERING",                     "Govt"),
    (r"^GCE\b",                                                 "Govt"),
    (r"\bGCE\s+(KALAHANDI|KEONJHAR|BHAWANIPATNA)",              "Govt"),
    (r"^IGIT\b|^I\.G\.I\.T\b|^INDIRA GANDHI INSTITUTE OF TECH", "Govt"),
    (r"^OUTR\b|ODISHA UNIVERSITY OF TECHNOLOGY",                "State-Univ-Dept"),
    (r"^VEER SURENDRA SAI UNIVERSITY",                          "State-Univ-Dept"),
    (r"^VSSUT",                                                 "State-Univ-Dept"),
    (r"^GOVT\b.*COLLEGE OF ENGINEERING",                        "Govt"),
    (r"\bCENTRAL TOOL ROOM",                                    "Govt"),
    (r"\bGOVERNMENT POLYTECHNIC",                               "Govt"),
    # College of Engineering & Technology Bhubaneswar (state)
    (r"^COLLEGE OF ENGINEERING AND TECHNOLOGY",                 "Govt"),
    (r"^CET\s+BHUBANESWAR",                                     "Govt"),
    # Govt-Aided
    (r"^PARALA MAHARAJA ENGINEERING COLLEGE",                   "Govt-Aided"),
]


# Normalisation rules — pdftotext sometimes wraps long institute names
# inconsistently, producing spurious duplicates. Collapse to canonical names.
def canonicalise_college(name: str) -> str:
    n = re.sub(r"\s+", " ", (name or "").strip())
    if n.upper().startswith("ODISHA UNIVERSITY OF TECHNOLOGY AND RESEARCH"):
        return "Odisha University of Technology and Research, Bhubaneswar"
    if n.upper().startswith("BIJU PATNAIK UNIVERSITY OF TECHNOLOGY"):
        return "Biju Patnaik University of Technology, Rourkela"
    if n.upper().startswith("VEER SURENDRA SAI UNIVERSITY"):
        return "Veer Surendra Sai University of Technology, Burla"
    if n.upper().startswith("INDIRA GANDHI INSTITUTE OF TECHNOLOGY"):
        return "Indira Gandhi Institute of Technology, Sarang"
    if n.upper().startswith("PARALA MAHARAJA"):
        return "Parala Maharaja Engineering College, Berhampur"
    if "GOVERNMENT COLLEGE OF ENGINEERING" in n.upper() and "KALAHANDI" in n.upper():
        return "Government College of Engineering, Kalahandi (Bhawanipatna)"
    if "GOVERNMENT COLLEGE OF ENGINEERING" in n.upper() and "KEONJHAR" in n.upper():
        return "Government College of Engineering, Keonjhar"
    return n


def classify_od_college(name: str) -> str:
    if not name:
        return "Unknown"
    for pat, cls in OD_GOVT_PATTERNS:
        if re.search(pat, name, re.IGNORECASE):
            return cls
    return "Private/SF"


GOVT_TYPES = {"Govt", "Govt-Aided", "State-Univ-Dept"}


def normalise_category(c: str) -> tuple[str, str]:
    c = c.strip().upper()
    if c == "GENERAL":  return ("GEN", "")
    if c in ("OBC", "SEBC"):  return ("OBC-NCL", c)
    if c == "SC":       return ("SC", "")
    if c == "ST":       return ("ST", "")
    if c == "EWS":      return ("EWS", "")
    if c == "TFW":      return ("OTHER", "TFW")
    if c == "PWD" or c == "GENERAL-PWD":   return ("OTHER", "PWD")
    if c == "SC-PWD":   return ("SC", "PWD")
    if c == "ST-PWD":   return ("ST", "PWD")
    return ("OTHER", c)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parse OJEE 2024 BTECH OR-CR PDF (60 pages)")
    rows = parse_od_pdf_text(SOURCE / PDF_FILE)
    df = pd.DataFrame(rows)
    # Canonicalise institute names (collapse pdftotext wrap variants)
    df["college_name"] = df["college_name"].apply(canonicalise_college)
    print(f"  Total rows: {len(df):,}")
    print(f"  Distinct institutes (after canonical name): {df['college_name'].nunique()}")
    print(f"  Categories: {sorted(df['category_raw'].unique())[:15]}")
    df.to_csv(OUT / f"{STATE_CODE}_engg_all_cutoffs_{DATA_YEAR}.csv", index=False)

    print("\nStage 2 — classify govt scope")
    df["college_type"] = df["college_name"].apply(classify_od_college)
    print("  by college_type:")
    for t, n in (df.groupby(["college_name", "college_type"]).size()
                  .reset_index().college_type.value_counts().items()):
        print(f"    {t:18s} {n:>4} colleges")

    govt = df[df["college_type"].isin(GOVT_TYPES)].copy()
    print(f"  govt-scope colleges: {govt['college_name'].nunique()}")
    print(f"  govt-scope rows:     {len(govt):,}")

    cat_norm = govt["category_raw"].apply(lambda c: pd.Series(normalise_category(c)))
    cat_norm.columns = ["category", "sub_pool"]
    govt = pd.concat([govt, cat_norm], axis=1)
    govt["gender"] = govt["seat_type"].apply(
        lambda s: "Girls" if s == "Female Only" else "All"
    )

    govt["state"] = "ODISHA"
    govt["cet_name"] = CET_NAME
    govt["stream"] = "engineering"
    govt["year"] = DATA_YEAR
    govt["round"] = "OR-CR (cumulative through main rounds, 2024 proxy for 2025)"
    govt["college_code"] = govt["college_name"]
    govt["rank_basis"] = "OJEE State Rank"

    govt_out = govt[[
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_name", "seat_type",
        "quota", "category_raw", "category", "sub_pool", "gender",
        "opening_rank", "closing_rank",
        "rank_basis",
    ]].sort_values(["college_name", "branch_name", "category_raw"])
    govt_out["source_url"] = SOURCE_URL
    govt_out.to_csv(
        OUT / f"{STATE_CODE}_engg_closing_ranks_govt_{DATA_YEAR}.csv", index=False,
    )

    print("\nStage 3 — schema-canonical 5-cat consolidated")
    canon = govt_out[
        govt_out["category"].isin(["GEN", "EWS", "OBC-NCL", "SC", "ST"])
    ].copy()
    canon["branch_code"] = canon["branch_name"]
    canon = canon.groupby([
        "state", "cet_name", "stream", "year", "round",
        "college_code", "college_name", "college_type",
        "branch_code", "branch_name",
        "quota", "category", "gender",
    ], dropna=False).agg(
        opening_rank=("opening_rank", "min"),
        closing_rank=("closing_rank", "max"),
    ).reset_index()
    canon["last_round_with_max"] = "ORCR cumulative"
    canon["rank_basis"] = "OJEE State Rank"
    canon["source_url"] = SOURCE_URL
    canon.to_csv(
        OUT / f"{STATE_CODE}_engg_consolidated_5cat_govt_{DATA_YEAR}.csv", index=False,
    )
    print(f"  consolidated 5-cat rows: {len(canon):,}")

    print("\n=== OD sanity (govt scope, General/Gender Neutral, hardest 12) ===")
    sample = govt_out[
        (govt_out["category_raw"] == "General")
        & (govt_out["seat_type"] == "Gender Neutral")
    ].sort_values("closing_rank").head(12)
    if not sample.empty:
        print(sample[["college_name", "branch_name", "closing_rank"]]
              .to_string(index=False, max_colwidth=55))


if __name__ == "__main__":
    main()
