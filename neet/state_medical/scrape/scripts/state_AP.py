"""
Andhra Pradesh NEET UG 2025 — state govt closing ranks pipeline.

Authority: Dr. NTR University of Health Sciences (NTRUHS), Vijayawada.
           https://drntr.uhsap.in
Source PDFs: drntr.uhsap.in/index/notification/

Last round used: CQ Phase-II (latest CQ allotment available; cumulative
                 over Phase 1 + Phase 2). Stray vacancy round excluded
                 per project pattern.

Source files:
  - AP_MBBS_CQ_Phase2_2025.pdf (CQ Phase 2 MBBS, 01-Oct-2025, 164 pp)
  - AP_BDS_CQ_Phase2_2025.pdf  (CQ Phase 2 BDS,  23-Oct-2025, 31 pp)

Schema: per-college sections with columns:
  SNo | NEET RANK | NEET Roll | Score | Name | Gender | Category
      | Local Area | Allotment Details | Phase

Allotment Details encode the seat awarded:
  Format: "<COLL_CODE> - <COURSE> - <LOCAL_AREA> - <SEAT_CAT> [- <SUB_POOL>] - <GENDER> --- <count>"
  - LOCAL_AREA: SVU (Sri Venkateswara Univ), AU (Andhra Univ), APUR (Universal),
                APNL (AP North), APSL (AP South)
  - SEAT_CAT: OC / BCA / BCB / BCC / BCD / BCE / SC[1-3] / ST / EWS
  - SUB_POOL (optional): PH (PwD-Hearing), PMC (Physically/Medically Challenged),
                          MRC (Minority Reservation), NCC, SP, EX, ANG (Anglo Indian)
  - GENDER: G (boys/general) / F (girls)

Govt-college filter: Hard-coded list of 22 known govt MBBS+BDS colleges.
                     "Government Medical College" naming is incomplete in
                     AP (top colleges like Guntur MC, Andhra MC, SV Medical
                     Tirupati lack "Government" in name).

Closing-rank metric: NEET AIR. Headline filter excludes sub-pools (PH/PMC/
                     MRC/etc.) — those are special seat types with very
                     different rank profiles.

Result: 17 govt MBBS + 2 govt BDS = 19 colleges (NMC list 19+2 — close).

Reservation taxonomy (see state_reservation_taxonomy.csv):
  Vertical: OC / BCA 7% / BCB 10% / BCC 1% / BCD 7% / BCE 4% (Muslim) /
            SC 15% (sub-split SC1/SC2/SC3 per 2024 SC rationalization) /
            ST 6% / EWS 10%
  Horizontal: PwD 5%, NCC, Sports, Anglo-Indian
  Local Area sub-pools: SVU/AU/APUR/APNL/APSL — based on candidate's
            10+2 university region

For Avanti JNV AP student: JNV is Central govt school. AP has no Govt-
School-Quota. Compete in regular state quota under their AP community
(BC sub-categories vs central OBC differ — cross-check community).

Outputs (to ../extracted_data/):
  - AP_all_allotments_2025.csv             — raw 2,997 rows
  - AP_closing_ranks_state_govt_2025.csv   — long format
  - AP_closing_ranks_state_govt_2025_pivot.csv — wide
"""
import pdfplumber
import pandas as pd
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "AP"
OUT = ROOT / "extracted_data"
STATE_CODE = "AP"

PDFS = [
    (SOURCE / "AP_MBBS_CQ_Phase2_2025.pdf", "MBBS"),
    (SOURCE / "AP_BDS_CQ_Phase2_2025.pdf", "BDS"),
]

KNOWN_GOVT_AP = {
    "ACSR Government Medical College, Nellore",
    "Andhra Medical College, Visakhapatnam",
    "Government Medical College, Anantapur", "Government Medical College, Eluru",
    "Government Medical College, Kadapa", "Government Medical College, Machilipatnam",
    "Government Medical College, Nandyal", "Government Medical College, Nandyala",
    "Government Medical College, Ongole", "Government Medical College, Paderu",
    "Government Medical College, Rajahmahendravaram",
    "Government Medical College, Rajamahendravaram",
    "Government Medical College, Vizianagaram", "Government Medical College,Srikakulam",
    "Guntur Medical College, Guntur", "Kurnool Medical College, Kurnool",
    "Sri Venkateswara Medical College, Tirupati",
    "Siddhartha Medical College, Vijayawada",
    "Sri Padmavathi Medical College for Women, Tirupati (under SVIMS)",
    "Sri Padmavathi Medical College for Women, (SVIMS) Tirupati",
    "Government Dental College & Hospital , Kadapa",
    "Government Dental College & Hospital, Vijayawada",
}

VALID_CATS = {
    "OC", "BCA", "BCB", "BCC", "BCD", "BCE", "SC", "SC1", "SC2", "SC3",
    "SCI", "SCII", "SCIII", "ST", "EWS", "OBC",
}
SUB_POOLS = {"PH", "PMC", "PWD", "MRC", "NCC", "SP", "ANG", "EX", "CAP", "PHM"}
VERTICAL_ORDER = ["OC", "BCA", "BCB", "BCC", "BCD", "BCE", "SC", "ST", "EWS", "OBC"]


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse PDFs (per-college sections)
# ───────────────────────────────────────────────────────────────────────────
ROW_RE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+(\d{10})\s+(\d+)\s+(.+?)\s+([MF])\s+(\S+)\s+(\S+)"
    r"\s+(.+?)\s+(Phase-\d)\s*$"
)


def parse_pdf(path: Path, course: str) -> list[dict]:
    rows = []
    cur_college = None
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for ln in text.splitlines():
                ln = ln.rstrip()
                # College header detection: line with 'College'/'Institute'/etc., not boilerplate
                if (
                    re.search(r"(College|Institute|Hospital|University)", ln)
                    and "Dr. N.T.R." not in ln
                    and "NEET" not in ln
                    and "Note" not in ln
                    and "Classes" not in ln
                    and "Allot" not in ln
                    and "S.No." not in ln
                    and not re.match(r"^\s*\d+\s", ln)
                ):
                    candidate = ln.strip()
                    if 10 < len(candidate) < 100:
                        cur_college = candidate
                        continue
                m = ROW_RE.match(ln)
                if m and cur_college:
                    rows.append({
                        "sno": int(m.group(1)),
                        "neet_rank": int(m.group(2)),
                        "neet_roll": m.group(3),
                        "score": int(m.group(4)),
                        "name": m.group(5).strip(),
                        "gender": m.group(6),
                        "cand_category": m.group(7),
                        "local_area": m.group(8),
                        "allotment_details": m.group(9).strip(),
                        "allotted_phase": m.group(10),
                        "college": cur_college,
                        "course": course,
                    })
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — parse allotment_details into seat_cat / gender / sub-pool flag
# ───────────────────────────────────────────────────────────────────────────
def parse_alloc_clean(s: str):
    s = str(s).split("---")[0]
    parts = [p.strip() for p in s.split("-") if p.strip()]
    if not parts:
        return ("", "", False)
    gender = parts[-1] if parts[-1] in ("G", "F", "M") else ""
    for i, p in enumerate(parts):
        if p in VALID_CATS:
            seat_cat = p
            after = parts[i + 1: -1] if gender else parts[i + 1:]
            has_sub = any(t in SUB_POOLS for t in after)
            return (seat_cat, gender, has_sub)
    return ("", "", False)


def canonicalize(name: str) -> str:
    n = re.sub(r"\s+", " ", str(name)).strip()
    n = n.replace("Nandyala", "Nandyal").replace("Rajahmahendravaram", "Rajamahendravaram")
    n = n.replace("(under SVIMS)", "SVIMS").replace("(SVIMS)", "SVIMS")
    return n


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing AP NTRUHS Phase-2 PDFs...")
    all_rows = []
    for path, course in PDFS:
        rows = parse_pdf(path, course)
        print(f"  {path.name}: {len(rows)} rows")
        all_rows.extend(rows)
    df = pd.DataFrame(all_rows)
    df["neet_rank"] = pd.to_numeric(df["neet_rank"], errors="coerce")
    df.to_csv(OUT / f"{STATE_CODE}_all_allotments_2025.csv", index=False)
    print(f"  Total: {len(df)}, colleges: {df['college'].nunique()}")

    print("\nStage 2 — filtering to govt + parsing allotment details...")
    gov = df[df["college"].isin(KNOWN_GOVT_AP)].copy()
    results = gov["allotment_details"].apply(parse_alloc_clean)
    gov["seat_cat"] = [r[0] for r in results]
    gov["seat_gender"] = [r[1] for r in results]
    gov["has_subpool"] = [r[2] for r in results]
    gov = gov.reset_index(drop=True)
    plain = gov[(gov["seat_cat"] != "") & (gov["has_subpool"] == False)].copy()
    print(f"  Govt rows: {len(gov)}, plain (no sub-pool): {len(plain)}")

    print("\nStage 3 — closing ranks per (college, course, vertical)...")
    plain["vert"] = plain["seat_cat"].apply(lambda c: "SC" if c.startswith("SC") else c)
    cr = (
        plain.groupby(["college", "course", "vert"])["neet_rank"]
        .agg(closing_AIR="max", opening_AIR="min", allotted_count="count")
        .reset_index()
    )
    cr["college"] = cr["college"].apply(canonicalize)
    cr = (
        cr.groupby(["college", "course", "vert"])
        .agg(
            closing_AIR=("closing_AIR", "max"),
            opening_AIR=("opening_AIR", "min"),
            allotted_count=("allotted_count", "sum"),
        )
        .reset_index()
    )
    cr.to_csv(OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False)

    print("\nStage 4 — wide pivot...")
    piv = cr.pivot_table(
        index=["college", "course"], columns="vert",
        values="closing_AIR", aggfunc="first",
    ).reset_index()
    present = [c for c in VERTICAL_ORDER if c in piv.columns]
    piv = piv[["college", "course"] + present]
    piv.to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    print(f"  Pivot: {len(piv)} rows ("
          f"{(piv['course']=='MBBS').sum()} MBBS + {(piv['course']=='BDS').sum()} BDS)")

    print(f"\n=== Top 5 AP govt MBBS by OC closing AIR ===")
    print(piv[piv["course"] == "MBBS"]
          .sort_values("OC", na_position="last").head(5)
          [["college", "OC", "BCA", "BCB", "BCD", "SC", "ST", "EWS"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
