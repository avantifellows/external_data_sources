"""
Maharashtra NEET UG 2025 — state govt closing ranks pipeline.

Authority: State Common Entrance Test (CET) Cell, Maharashtra.
           https://cetcell.mahacet.org / https://medicalug2025.mahacet.org
Source PDFs: https://statecetcell.s3.ap-south-1.amazonaws.com/Notifications_UG25/

Last round used: cumulative through CAP Round 3 (R1 + R2 + R3).
  - Three CAP main rounds (Aug-Oct 2025), each ~1,000 pages, ~11k allotments
  - Stray Rounds R4, R5 (Nov 2025) excluded — small mop-ups
  - Closing rank per (college_code, allotted_quota) = MAX(AIR) across rounds.

Govt-college filter:
  - The MH seat matrix splits colleges into GOVT / PVT sections per program
  - Pages 1-7 of seat matrix = GOVT MBBS (42 codes)
  - Page 10 = GOVT BDS (5 codes)
  - Other pages are PVT — dropped per "no management quota" scope

Reservation taxonomy (see state_reservation_taxonomy.csv):
  - Vertical: OPEN / OBC / SC / ST / EWS / SEBC (Maratha) / VJA (Vimukta Jati)
            / NTB / NTC / NTD / SBC (Special Backward Class) — each with its own
            allocation %.
  - Horizontal "(W)" — 30% women reservation across all categories
  - Modifiers seen in allotted-quota field:
      - "(EMD)" — Educationally backward Marathwada Domicile (regional)
      - "(EMR)" — variant of regional reservation
      - "MINO" — Open Minority sub-pool
      - EMOBC/EMSEBC — Economic + caste combined sub-quotas
      - I.Q. — Institutional quota (own students)
      - D1/DEF1 — Defence personnel children
      - ORP — Orphan quota

For Avanti JNV MH student (typical):
  - JNV is Central govt school — Maharashtra does not have a separate
    "govt school student" reservation, so JNV doesn't get a horizontal
    bump. Compete in the regular state quota under their MH caste category.
  - Look up: state govt college × candidate's vertical category in the
    pivot file. (W) seats add 30% horizontal benefit if female.

Outputs (to ../extracted_data/):
  - MH_all_allotments_2025.csv             — raw 32,923 rows
  - MH_closing_ranks_state_govt_2025.csv   — 1,905 long rows (47 govt colleges)
  - MH_closing_ranks_state_govt_2025_pivot.csv — wide format,
                                                  Open/OBC/SC/ST/EWS/SEBC/VJA/
                                                  NTB/NTC/NTD as columns
"""
import pdfplumber
import pandas as pd
import re
import subprocess
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "MH"
OUT = ROOT / "extracted_data"
STATE_CODE = "MH"

ROUND_FILES = [
    ("MH_R1_2025.pdf", "R1"),
    ("MH_R2_2025.pdf", "R2"),
    ("MH_R3_2025.pdf", "R3"),
]
SEAT_MATRIX = SOURCE / "MH_seatmatrix_R2.pdf"
GOVT_MBBS_PAGES = range(1, 8)  # pages 1-7
GOVT_BDS_PAGES = [10]


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse round PDFs (text-based, MH tables aren't fully gridded)
# ───────────────────────────────────────────────────────────────────────────
LINE_PATTERN = re.compile(
    r"^\s*(\d{1,5})\s+(\d{1,7})\s+(\d{10})\s+(\d{9})\s+(.+?)\s+([MF])\s+(.*?)$"
)
COLLEGE_PATTERN = re.compile(r"(\d{4}):\s*(.+)$")
CANDIDATE_CATS = {
    "OBC", "SC", "ST", "NTB", "NTC", "NTD", "VJA", "SBC",
    "SEBC", "EWS", "VJ", "NT-B", "NT-C", "NT-D", "MI",
}


def parse_mh_pdf(path: Path, round_label: str) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                m = LINE_PATTERN.match(ln)
                if not m:
                    continue
                sr, air, roll, form, name, gender, tail = m.groups()
                cm = COLLEGE_PATTERN.search(tail)
                if not cm:
                    continue
                code = cm.group(1)
                college = cm.group(2).strip()
                pre = tail[: cm.start()].strip()  # "<Cat>? <Quota> [(W)] [(EMD)]"
                tokens = pre.split()
                cand_cat = ""
                if tokens and tokens[0] in CANDIDATE_CATS:
                    cand_cat = tokens.pop(0)
                quota = " ".join(tokens) if tokens else ""
                rows.append({
                    "round": round_label,
                    "sr_no": int(sr),
                    "air": int(air),
                    "neet_roll": roll,
                    "cet_form": form,
                    "name": name.strip(),
                    "gender": gender,
                    "cand_cat": cand_cat,
                    "allotted_quota": quota,
                    "college_code": code,
                    "college": college,
                })
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — extract govt college codes from seat matrix
# ───────────────────────────────────────────────────────────────────────────
def codes_from_seat_matrix(pdf_path: Path, pages) -> dict:
    """Return {code: name} for govt colleges in given page range."""
    out = {}
    for p in pages:
        txt = subprocess.run(
            ["pdftotext", "-layout", "-f", str(p), "-l", str(p), str(pdf_path), "-"],
            capture_output=True, text=True,
        ).stdout
        for ln in txt.splitlines():
            m = re.match(
                r"^\s*\d+\s+(\d{4})\s+([A-Z].+?)(?:\s{2,}|\s+Y\s|\s+N\s)", ln
            )
            if m:
                out.setdefault(m.group(1), m.group(2).strip())
    return out


# ───────────────────────────────────────────────────────────────────────────
# Stage 3 — closing ranks + decompose quota into vertical / women / modifiers
# ───────────────────────────────────────────────────────────────────────────
def decompose_quota(q: str):
    q = q.strip()
    is_w = "(W)" in q
    is_emd = "(EMD)" in q
    is_emr = "(EMR)" in q
    is_mino = "MINO" in q
    is_orph = "ORP" in q
    is_def = "DEF" in q.upper() or re.search(r"\bD\d\b", q) is not None
    base = re.sub(r"\(W\)|\(EMD\)|\(EMR\)|MINO|ORP\w*|DEF\d*|\bD\d\b", "", q).strip()
    base = re.sub(r"\s+", " ", base)
    return base, is_w, (is_emd or is_emr or is_mino), is_orph, is_def


VERTICAL_ORDER = [
    "OPEN", "OBC", "SC", "ST", "EWS", "SEBC", "VJA", "NTB", "NTC", "NTD", "SBC",
]


# ───────────────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────────────
def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R1+R2+R3 PDFs (~5 min)...")
    all_rows = []
    for fname, label in ROUND_FILES:
        path = SOURCE / fname
        rows = parse_mh_pdf(path, label)
        print(f"  {fname} ({label}): {len(rows):,} rows")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df):,}")

    print("\nStage 2 — extracting govt college codes from seat matrix...")
    mbbs_codes = codes_from_seat_matrix(SEAT_MATRIX, GOVT_MBBS_PAGES)
    bds_codes = codes_from_seat_matrix(SEAT_MATRIX, GOVT_BDS_PAGES)
    gov_codes = {**{c: "MBBS" for c in mbbs_codes}, **{c: "BDS" for c in bds_codes}}
    print(f"  Govt: {len(mbbs_codes)} MBBS + {len(bds_codes)} BDS = {len(gov_codes)} codes")

    print("\nStage 3 — filtering to govt + computing closing ranks...")
    df["college_code"] = df["college_code"].astype(str)
    gov = df[df["college_code"].isin(gov_codes)].copy()
    gov["program"] = gov["college_code"].map(gov_codes)
    print(f"  Govt allotments: {len(gov):,}")

    best_name = gov.groupby("college_code")["college"].agg(lambda s: s.mode().iat[0])

    cr = (
        gov.groupby(["college_code", "program", "allotted_quota"])
        .agg(
            closing_air=("air", "max"),
            opening_air=("air", "min"),
            allotted_count=("air", "count"),
        )
        .reset_index()
    )
    last_round = (
        gov.sort_values("air", ascending=False)
        .drop_duplicates(["college_code", "program", "allotted_quota"])
        [["college_code", "program", "allotted_quota", "round"]]
        .rename(columns={"round": "last_round_with_max"})
    )
    cr = cr.merge(last_round, on=["college_code", "program", "allotted_quota"])
    cr["college"] = cr["college_code"].map(best_name)

    deco = cr["allotted_quota"].apply(lambda q: pd.Series(decompose_quota(q)))
    deco.columns = ["vertical", "is_women", "has_modifier", "is_orphan", "is_defence"]
    cr = pd.concat([cr, deco], axis=1)

    cr = cr[
        [
            "college_code", "college", "program", "allotted_quota", "vertical",
            "is_women", "has_modifier", "is_orphan", "is_defence",
            "closing_air", "opening_air", "allotted_count", "last_round_with_max",
        ]
    ].sort_values(["program", "college", "allotted_quota"])
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    print(f"  {len(cr):,} closing-rank rows over {cr['college_code'].nunique()} colleges")

    print("\nStage 4 — wide pivot (plain vertical, no women/modifier/orphan/def)...")
    plain = cr[
        (~cr["is_women"]) & (~cr["has_modifier"])
        & (~cr["is_orphan"]) & (~cr["is_defence"])
    ]
    piv = plain.pivot_table(
        index=["college_code", "college", "program"],
        columns="vertical", values="closing_air", aggfunc="first",
    ).reset_index()
    present = [c for c in VERTICAL_ORDER if c in piv.columns]
    piv = piv[["college_code", "college", "program"] + present]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows")

    print(f"\n=== Top 5 MH state govt MBBS by OPEN closing AIR ===")
    print(piv[piv["program"] == "MBBS"].sort_values("OPEN").head(5).to_string(index=False))


if __name__ == "__main__":
    main()
