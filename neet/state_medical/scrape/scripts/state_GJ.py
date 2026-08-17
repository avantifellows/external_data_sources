"""
Gujarat NEET UG 2025 — state govt closing ranks pipeline.

Authority: Admission Committee for Professional UG Medical Educational Courses
           (ACPUGMEC), Gandhinagar. https://medadmgujarat.org
Source: Gujarat publishes a clean "Last Merit Round-04" PDF that gives
        per-college closing ranks (Gujarat state merit rank) directly,
        broken out by category. No need to parse per-candidate allotments.

Last round used: Round 4 (last MAIN round; R5 BDS-only stray and R6
                 Special Stray excluded).

File source: GJ_R4_lastrank.pdf
URL: https://medadmgujarat.ncode.in/web/UG2025/R4/ROUND4_last_merit_mopwise.pdf

Government-college filter:
  - Suffix "-GQ" = Government Quota (state-quota seats — both at govt
    colleges and govt-fee seats at private colleges).
  - The * marker in the PDF identifies STRICT govt colleges (7 in MBBS):
    AMED (BJ Medical Ahmedabad), BMED (Baroda), SMED (Surat), RMED (Rajkot),
    JMED (Jamnagar), BHMED (Bhavnagar), ESICMED (ESIC).
  - GMERS colleges (Gujarat Medical Education and Research Society — 13
    state-funded govt-society colleges) lack * but ARE govt per project
    definition: SOL, GMED, GOT, VAL, JU, HIM, MOR, PAT, VAD, NAV, RAJ, POR, GODH
  - NHL = Municipal Corp Ahmedabad, also govt-society
  - Result: 7 Govt + 13 GMERS + 1 NHL = 21 MBBS govt + 2 BDS govt = 23
    colleges (matches NMC list of 23 govt MBBS for Gujarat)

Reservation taxonomy (see state_reservation_taxonomy.csv):
  - Vertical: OPEN / SC (7%) / ST (15% — high due to tribal districts)
            / SE=SEBC (27% — Gujarat's OBC label) / EW=EWS (10%)
  - Horizontal: PH (5% PwD across categories)
  - State quota eligibility STRICTER than most: needs Gujarat 10+2 OR
    Gujarat MBBS, not just domicile

For Avanti JNV GJ student (typical):
  - JNV is Central govt school. GJ has no horizontal Govt-School quota.
  - Look up: GJ_closing_ranks_state_govt_2025_pivot.csv with student's
    GJ vertical category (OPEN / SC / ST / SE / EW)

NOTE on rank interpretation:
  - These closing ranks are GUJARAT STATE MERIT RANKS (not NEET AIR).
    Gujarat assigns its own state merit rank to each domicile candidate
    based on NEET marks. State rank 180 = top 180 NEET candidates among
    GJ-domicile applicants.
  - "99999" in the source PDF means "no candidate took this seat" (seat
    converted) — we map to NaN.

Outputs (to ../extracted_data/):
  - GJ_closing_ranks_state_govt_2025.csv         — 23 rows (long)
  - GJ_closing_ranks_state_govt_2025_pivot.csv   — same (already wide)
  - GJ_closing_ranks_GQ_all_2025.csv             — all -GQ incl private
"""
import subprocess
import re
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "source" / "GJ"
OUT = ROOT / "extracted_data"
STATE_CODE = "GJ"

GMERS_BASES = {
    "SOLMED", "GMED", "GOTMED", "VALMED", "JUMED", "HIMMED", "MORMED",
    "PATMED", "VADMED", "NAVMED", "RAJMED", "PORMED", "GODHMED",
}
MUNICIPAL_BASES = {"NHL"}  # NHL Med College Ahmedabad — Municipal Corp


# ───────────────────────────────────────────────────────────────────────────
# Stage 1 — parse the closing-rank PDF (one row per college × seat type)
# ───────────────────────────────────────────────────────────────────────────
def parse_lastrank_pdf(path: Path) -> pd.DataFrame:
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True, text=True,
    ).stdout

    rows = []
    program = "MBBS"
    for ln in text.splitlines():
        raw = ln.rstrip()
        if not raw.strip():
            continue
        # Section markers
        if "DENTAL" in raw and "College" not in raw and "PROFESSIONAL" not in raw \
           and "Page" not in raw:
            program = "BDS"
            continue
        if "MEDICAL" in raw and "College" not in raw and "PROFESSIONAL" not in raw \
           and "Page" not in raw:
            program = "MBBS"
            continue
        s = raw.lstrip()
        is_starred = s.startswith("*")
        if is_starred:
            s = s.lstrip("*").lstrip()
        m = re.match(r"^([A-Z]+)\s*-\s*(GQ|MQ|NQ|Local)\s+(.+)$", s, re.IGNORECASE)
        if not m:
            continue
        base, suffix, rest = m.group(1), m.group(2).upper(), m.group(3)
        nums = [int(n) for n in re.findall(r"\b(\d+)\b", rest)]
        rows.append({
            "is_starred_govt": is_starred,
            "code": f"{base}-{suffix}",
            "base": base,
            "suffix": suffix,
            "program": program,
            "nums": nums,
        })

    df = pd.DataFrame(rows)
    cols = ["OPEN", "SC", "ST", "SE", "EW",
            "OPEN_PH", "SC_PH", "ST_PH", "SE_PH", "EW_PH", "NRI"]
    for i, c in enumerate(cols):
        df[c] = df["nums"].apply(lambda n, ii=i: n[ii] if ii < len(n) else None)
    for c in cols:
        df[c] = df[c].apply(lambda x: None if x == 99999 else x)
    return df.drop(columns=["nums"])


# ───────────────────────────────────────────────────────────────────────────
# Stage 2 — classify each row as Govt / Govt-Society / Private
# ───────────────────────────────────────────────────────────────────────────
def classify_mgmt(row) -> str:
    if row["suffix"] != "GQ":
        return "Other"
    if row["is_starred_govt"]:
        return "Govt"
    if row["base"] in GMERS_BASES:
        return "Govt-Society (GMERS)"
    if row["base"] in MUNICIPAL_BASES:
        return "Govt-Society (Municipal)"
    return "Private (govt-quota)"


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    print("Stage 1 — parsing R4 last-rank PDF...")
    df = parse_lastrank_pdf(SOURCE / "GJ_R4_lastrank.pdf")
    print(f"  {len(df)} rows")

    print("\nStage 2 — classifying govt vs private...")
    df["mgmt"] = df.apply(classify_mgmt, axis=1)
    print(df.groupby(["program", "mgmt"]).size())

    print("\nStage 3 — filtering to Govt + Govt-Society...")
    govt_mgmts = ["Govt", "Govt-Society (GMERS)", "Govt-Society (Municipal)"]
    gov = df[df["mgmt"].isin(govt_mgmts)].copy()
    print(f"  {len(gov)} govt rows ("
          f"{gov[gov['program']=='MBBS']['code'].nunique()} MBBS + "
          f"{gov[gov['program']=='BDS']['code'].nunique()} BDS)")

    out_cols = ["code", "base", "program", "mgmt",
                "OPEN", "SC", "ST", "SE", "EW",
                "OPEN_PH", "SC_PH", "ST_PH", "SE_PH", "EW_PH"]
    gov[out_cols].to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025.csv", index=False
    )
    gov[out_cols].to_csv(
        OUT / f"{STATE_CODE}_closing_ranks_state_govt_2025_pivot.csv", index=False
    )
    df.to_csv(OUT / f"{STATE_CODE}_closing_ranks_GQ_all_2025.csv", index=False)

    print(f"\n=== Top 5 GJ state-govt MBBS by OPEN closing (state merit) ===")
    print(gov[gov["program"] == "MBBS"]
          .sort_values("OPEN", na_position="last")
          [["code", "mgmt", "OPEN", "SC", "ST", "SE", "EW"]]
          .head(5).to_string(index=False))


if __name__ == "__main__":
    main()
