"""
Telangana NEET UG 2025 — state govt closing ranks pipeline.

Authority: Kaloji Narayana Rao University of Health Sciences (KNRUHS).
           https://www.knruhs.telangana.gov.in
Sources: KNRUHS publishes per-college, per-phase allotment PDFs at
         /uploads/<timestamp><title>.pdf — clean tabular format.

Last round used: cumulative through Mop-up phase (Phase 1 + Phase 2 +
Mop-up). Stray Vacancy phase excluded — fills leftover seats at much
lower ranks, not a meaningful target.

Govt-college filter:
  - "Competent Authority Quota" (CQ) = state government quota; covers
    state-quota seats at govt colleges PLUS the 50% govt-quota at
    private colleges (TG model). For state-govt scope, we filter
    college names containing "GOVT" plus known govt institutions
    (Gandhi MC, Osmania MC, Kakatiya MC, ESI MC, Rajiv Inst Adilabad).
  - Result: 35 govt MBBS + 1 govt BDS (vs NMC list 36+1, missing 1 new
    college).

Reservation taxonomy (see state_reservation_taxonomy.csv):
  - Vertical: OC / BCA / BCB / BCC / BCD / BCE / SC1 / SC2 / SC3 / ST + EWS
    - BCA-E are TG-specific BC sub-categories
    - SC1/SC2/SC3 are SC sub-categories per 2024 SC Rationalization GO
  - Horizontal: GEN (general) vs FEM (33% female reservation)
  - Sub-pools (within each seat type): MRC (Minority Reservation Category),
    PHO (PWD-Orthopaedic), CAP (CAPF wards), CAP-MRC (CAPF + Minority).
    Headline closing rank uses no-subpool entries only.

For Avanti JNV TG student (typical):
  - JNV is Central govt school. TG does not have a separate govt-school
    student quota — student competes in regular state quota under their
    TG community.
  - Look up: TG_closing_ranks_state_govt_2025_pivot_GEN.csv (boys) or
    TG_closing_ranks_state_govt_2025_pivot_FEM.csv (girls)
  - Use candidate's TG community code (OC/BCA/BCB/BCC/BCD/BCE/SC1/SC2/SC3/ST/EWS)

Outputs (to ../extracted_data/):
  - TG_all_allotments_2025.csv                  — raw 16,584 rows
  - TG_closing_ranks_state_govt_2025.csv        — 939 long rows
  - TG_closing_ranks_state_govt_2025_pivot_GEN.csv — wide (general/male)
  - TG_closing_ranks_state_govt_2025_pivot_FEM.csv — wide (female)
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "TG"
OUT = ROOT / "extracted_data"
STATE_CODE = "TG"

ROUNDS = [
    ("TG_MBBS_Phase1_19092025.pdf", "P1", "MBBS"),
    ("TG_MBBS_Phase2_30092025.pdf", "P2", "MBBS"),
    ("TG_MBBS_MopUp_28102025.pdf",  "MopUp", "MBBS"),
    ("TG_BDS_Phase2_04102025.pdf",  "P2", "BDS"),
]

DATA_RE = re.compile(r"^\s*(\d{1,7})\s+(\d{10})\s+(.+)$")
COLL_RE = re.compile(r"^COLL\s*::\s*(\S+)\s*-\s*(.+)$")
CAT_RE = re.compile(r"\b(OC|BC[A-E]?|SC\d?|ST|EWS)\s+([MF])\b")

KNOWN_GOVT_MBBS = {
    "GANDHI MEDICAL COLLEGE", "OSMANIA MEDICAL COLLEGE",
    "KAKATIYA MEDICAL COLLEGE", "ESI MEDICAL COLLEGE",
    "RAJIV INSTITUTE OF MEDICAL SCIENCE",
}

VERTICAL_ORDER = [
    "OPEN", "EWS", "BCA", "BCB", "BCC", "BCD", "BCE",
    "SC", "SC1", "SC2", "SC3", "ST", "MIN",
]


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse round PDFs
# ───────────────────────────────────────────────────────────────────────────
def parse_pdf(path: Path, round_lbl: str, program: str) -> list[dict]:
    rows = []
    with pdfplumber.open(path) as pdf:
        cur_code = None
        cur_name = None
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                ln = ln.rstrip()
                cm = COLL_RE.match(ln)
                if cm:
                    cur_code = cm.group(1).strip()
                    cur_name = cm.group(2).strip()
                    continue
                dm = DATA_RE.match(ln)
                if dm and cur_code:
                    rank = int(dm.group(1))
                    roll = dm.group(2)
                    rest = dm.group(3).strip()
                    adm_m = re.search(r"(\S+-\S+-\S+)\s*$", rest)
                    adm = adm_m.group(1) if adm_m else ""
                    pre = rest[: adm_m.start()].strip() if adm_m else rest
                    cat_m = CAT_RE.search(pre)
                    cand_cat = cat_m.group(1) if cat_m else ""
                    gender = cat_m.group(2) if cat_m else ""
                    rows.append({
                        "round": round_lbl, "program": program,
                        "college_code": cur_code, "college": cur_name,
                        "rank": rank, "roll": roll,
                        "cand_cat": cand_cat, "gender": gender,
                        "adm_details": adm,
                    })
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — govt-only filter
# ───────────────────────────────────────────────────────────────────────────
def is_govt_mbbs(name: str) -> bool:
    n = str(name).upper()
    return "GOVT" in n or any(k in n for k in KNOWN_GOVT_MBBS)


def is_govt_bds(name: str) -> bool:
    return "GOVT DENTAL COLLEGE" in str(name).upper()


# ───────────────────────────────────────────────────────────────────────────
# Stage 3 — decompose adm_details into seat / gender / sub-pool / phase
# ───────────────────────────────────────────────────────────────────────────
def decompose_adm(s: str):
    """Format: SEAT-GENDER[-SUBPOOL]-PHASE.
    e.g. 'OPEN-GEN-P1', 'OPEN-FEM-PHO-P2', 'BCB-GEN-MRC-P1'"""
    parts = str(s).split("-")
    if len(parts) < 3:
        return ("", "", "", "")
    seat = parts[0]
    gender = parts[1]
    phase = parts[-1]
    subpool = "-".join(parts[2:-1])
    return seat, gender, subpool, phase


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing 4 round PDFs (~3 min)...")
    all_rows = []
    for fname, label, program in ROUNDS:
        rows = parse_pdf(SOURCE / fname, label, program)
        print(f"  {fname} ({program} {label}): {len(rows):,} rows")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df):,}")

    print("\nStage 2 — filtering to govt colleges only...")
    mbbs = df[(df["program"] == "MBBS") & df["college"].apply(is_govt_mbbs)].copy()
    bds = df[(df["program"] == "BDS") & df["college"].apply(is_govt_bds)].copy()
    gov = pd.concat([mbbs, bds], ignore_index=True)
    print(f"  Govt: {mbbs['college_code'].nunique()} MBBS + {bds['college_code'].nunique()} BDS = "
          f"{len(gov):,} allotments")

    print("\nStage 3 — decomposing adm_details + closing ranks...")
    deco = gov["adm_details"].apply(lambda s: pd.Series(decompose_adm(s)))
    deco.columns = ["seat_type", "seat_gender", "seat_subpool", "seat_phase"]
    gov = pd.concat([gov.reset_index(drop=True), deco], axis=1)

    cr = (
        gov.groupby(["college_code", "college", "program",
                     "seat_type", "seat_gender", "seat_subpool"])
        .agg(
            closing_rank=("rank", "max"),
            opening_rank=("rank", "min"),
            allotted_count=("rank", "count"),
        )
        .reset_index()
    )
    last_round = (
        gov.sort_values("rank", ascending=False)
        .drop_duplicates(["college_code", "program", "seat_type",
                          "seat_gender", "seat_subpool"])
        [["college_code", "program", "seat_type", "seat_gender",
          "seat_subpool", "round"]]
        .rename(columns={"round": "last_round_with_max"})
    )
    cr = cr.merge(
        last_round,
        on=["college_code", "program", "seat_type", "seat_gender", "seat_subpool"],
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)
    print(f"  {len(cr):,} closing-rank rows")

    print("\nStage 4 — wide pivots (GEN + FEM, no-subpool only)...")
    for gender in ["GEN", "FEM"]:
        sub = cr[(cr["seat_gender"] == gender) & (cr["seat_subpool"] == "")]
        piv = sub.pivot_table(
            index=["college_code", "college", "program"],
            columns="seat_type", values="closing_rank", aggfunc="first",
        ).reset_index()
        present = [c for c in VERTICAL_ORDER if c in piv.columns]
        piv = piv[["college_code", "college", "program"] + present]
        piv.to_csv(
            OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot_{gender}.csv",
            index=False,
        )
        print(f"  pivot_{gender}: {len(piv)} rows")


if __name__ == "__main__":
    main()
