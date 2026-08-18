#!/usr/bin/env python3
"""
The nine tracks that take neet_fact_cutoffs from 19 to 28 — built from the same
staged extracts the 2026 matrix used, with each source's quirks handled the way
the corresponding matrix builder handles them (documented per track below).

Two of the nine are not new data but RE-TRACKING fixes applied in
build_fact_parquet.main(): rows with seat_type 'Delhi University Quota' and
'Internal -Puducherry UT Domicile' were sitting under track='All India', but
neither is the 15% AIQ competition — they are Delhi's and Puducherry's own
domicile doors, and the matrix has always treated them as separate tracks.

The mirror image also appears here twice: ZMCH (Mizoram) and GMCH-32
(Chandigarh) publish admitted-student lists that MIX their state pool with the
15% AIQ seats hosted at the college. Those AIQ admits become
track='All India' with college_state naming the host state — the exact case
the track/college_state split exists for.

Where a source has no AIR (Mizoram is marks-native), closing_rank comes from
the validated 2025 marks->AIR model — same conversion the matrix uses for TN.
"""
from __future__ import annotations

import csv
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEET = HERE.parent
CP = Path("/Users/surya/jan2023/college-predictor")
SMD = CP / "amogh-csv/medical-state-counselling/extracted_data"
EXTR = NEET / "extracted"

# merge-time stamps, same values the matrix's TRACKS registry carries
ROUNDS = {
    "Assam": "State R1+merit list", "Himachal Pradesh": "State R3 (final)",
    "Jammu & Kashmir": "State R1/R3 (merit-list marks)", "Manipur": "R2 allotment",
    "Tripura": "R1 only (strict)", "Mizoram": "Final admitted register",
    "Chandigarh": "Final admitted list",
}

# ── marks -> AIR, for the marks-native sources (the validated 2025 model) ──
_M = json.load(open(CP / "public/data/NEETUG/score_rank_model.json"))

def _air_of(marks: float) -> int:
    m = max(_M["min_trusted_score"], min(float(marks), _M["max_trusted_score"]))
    v = 0.0
    for a in _M["coeffs"]:
        v = v * m + a
    return int(round(10 ** v))


def _row(track, college_state, institute, program, category, category_raw,
         sub_pool, air, college_type, source, seat_type="State Quota",
         gender="Gender-Neutral", label=""):
    return dict(track=track, college_state=college_state,
                institute=institute, address="", program=program,
                category=category, category_raw=category_raw,
                category_label=label, sub_pool=sub_pool, seat_type=seat_type,
                college_type=college_type, college_type_method="R0-source-stated",
                seat_gender=gender, closing_rank=air, rank_space="NEET AIR",
                round=ROUNDS.get(track, ""), exam_year=2025, source=source)


def himachal():
    """HP: closing AIR per college x cat_base, govt-only source. Direct."""
    out = []
    for r in csv.DictReader(open(SMD / "HP_closing_ranks_state_govt_2025.csv", encoding="utf-8-sig")):
        cat = r["cat_base"].strip()
        canon = {"General": "Gen", "OBC": "OBC", "SC": "SC", "ST": "ST"}.get(cat)
        if not canon:
            continue
        out.append(_row("Himachal Pradesh", "Himachal Pradesh", r["college"].strip(),
                        "MBBS" if "MBBS" in r["program"].upper() else "BDS",
                        canon, cat, "", int(float(r["closing_neet_air"])),
                        "Govt", "himachal_2025_r3_dropbox"))
    return out


def jk():
    """J&K: closing UT rank per institution x vert -> AIR via the UT merit list
    (5,707 exact state_rank<->AIR pairs — a lookup, not a model). OM=Open Merit.
    Verticals beyond the five base categories (RBA/ALC/PSP...) are J&K's
    residual-reservation pools -> sub_pool, category NULL."""
    merit = {}
    for r in csv.DictReader(open(SMD / "JK_meritlist_state_rank_air.csv", encoding="utf-8-sig")):
        merit[int(r["state_rank"])] = int(r["air"])
    ranks = sorted(merit)

    def air_of_ut(ut):
        # nearest listed rank at or below; merit list is dense so this is tight
        lo = max((x for x in ranks if x <= ut), default=ranks[0])
        return merit[lo]

    CANON = {"OM": ("Gen", ""), "EWS": ("Gen-EWS", ""), "OBC": ("OBC", ""),
             "SC": ("SC", ""), "ST": ("ST", "")}
    out = []
    for r in csv.DictReader(open(SMD / "JK_closing_ranks_state_govt_2025.csv", encoding="utf-8-sig")):
        vert = r["vert"].strip()
        canon, sub = CANON.get(vert, (None, vert.lower()))
        ut = r.get("closing_UT_rank", "").strip()
        if not ut.replace(".", "").isdigit():
            continue
        prog = "BDS" if "BDS" in r["discipline"].upper() or "DENTAL" in r["discipline"].upper() else "MBBS"
        out.append(_row("Jammu & Kashmir", "Jammu & Kashmir", r["institution"].strip(),
                        prog, canon, vert, sub, air_of_ut(int(float(ut))),
                        "Govt", "jk_2025_meritlist_dropbox"))
    return out


def assam():
    """Assam: 1,298 per-student allotments -> closing AIR per (college, pool).
    Two builder rules carried over: the >=350-marks sanity guard (the source's
    documented mis-pool bug dumps ~150-210-mark candidates into wrong pools at
    absurd AIRs), and ST(P)/ST(H) both -> ST with the plains/hills split kept
    in sub_pool. Ex-Serviceman/Freedom Fighter/Sports -> sub_pool, category NULL."""
    POOL = {"UR": ("Gen", ""), "EWS": ("Gen-EWS", ""), "OBC/MOBC(NCL)": ("OBC", ""),
            "SC": ("SC", ""), "ST(P)": ("ST", "plains"), "ST(H)": ("ST", "hills")}
    best = {}
    for r in csv.DictReader(open(SMD / "AS_all_allotments_2025.csv", encoding="utf-8-sig")):
        try:
            air, score = int(r["neet_air"]), float(r["neet_score"])
        except ValueError:
            continue
        if score < 350:                     # the mis-pool guard
            continue
        pool = r["final_pool"].strip()
        canon, sub = POOL.get(pool, (None, pool.lower()))
        prog = "BDS" if r["inst_code"].startswith("2") else "MBBS"
        key = (r["college_canon"].strip(), prog, pool)
        if key not in best or air > best[key][0]:
            best[key] = (air, canon, sub)
    return [_row("Assam", "Assam", coll, prog, canon, pool, sub, air,
                 "Govt", "assam_2025_allotments_dropbox")
            for (coll, prog, pool), (air, canon, sub) in best.items()]


def manipur():
    """Manipur: 40 OCR'd R2 allotments, AIR-native, 4 institutes. RIMS/JNIMS are
    the government pool (the matrix's rule); others carry NULL college_type."""
    # the matrix's rule: RIMS/JNIMS/CMC form the government pool; SAHS is private
    GOVT = re.compile(r"RIMS|JNIMS|CMC", re.I)
    best = {}
    for r in csv.DictReader(open(EXTR / "MN_allotments_ocr.csv")):
        try:
            air = int(r["neet_air"])
        except ValueError:
            continue
        cat = r["category"].strip()
        canon = {"Gen": "Gen", "OBC": "OBC", "SC": "SC", "ST": "ST"}.get(cat)
        key = (r["institute"].strip(), cat)
        if key not in best or air > best[key]:
            best[key] = air
    return [_row("Manipur", "Manipur", inst, "MBBS",
                 {"Gen": "Gen", "OBC": "OBC", "SC": "SC", "ST": "ST"}.get(cat), cat, "",
                 air, "Govt" if GOVT.search(inst) else "Private",
                 "manipur_2025_r2_ocr")
            for (inst, cat), air in best.items()]


def tripura():
    """Tripura: R1 allotments, AIR+marks native, 3 institutes. AGMC is government;
    TMC/BRAM is the society college whose ST seats run below the qualifying gate
    (the 179-mark trap) — kept, labelled Private, never mixed."""
    best = {}
    for r in csv.DictReader(open(EXTR / "tripura-tripura_2025_r1_allotments.csv")):
        try:
            air = int(r["air"])
        except ValueError:
            continue
        inst = r["institute"].strip()
        cat = r["category"].strip()
        canon = {"Gen": "Gen", "Gen-EWS": "Gen-EWS", "OBC": "OBC", "SC": "SC", "ST": "ST"}.get(cat)
        prog = "BDS" if "BDS" in r["program"].upper() else "MBBS"
        key = (inst, prog, cat)
        if key not in best or air > best[key][0]:
            best[key] = (air, canon, r.get("inst_state", "Tripura") or "Tripura")
    return [_row("Tripura", st, inst, prog, canon, cat, "",
                 air, "Govt" if "AGMC" in inst.upper() or "AGARTALA GOVERNMENT" in inst.upper() else "Private",
                 "tripura_2025_r1_ocr")
            for (inst, prog, cat), (air, canon, st) in best.items()]


def mizoram():
    """ZMCH's admitted register mixes three competitions at one college:
      Govt+ST            -> Mizoram's state quota (68 of 70 seats are ST)
      Govt+GENERAL/SC/OBC -> the 15% AIQ seats HOSTED at ZMCH -> track='All India'
      Nri                -> a fee pool, sub_pool='nri'
    Marks-native: AIR via the validated model, like the matrix does."""
    best = {}
    for r in csv.DictReader(open(EXTR / "mizoram-zmch_2025_admitted.csv")):
        try:
            marks = float(r["neet_marks"])
        except ValueError:
            continue
        if r["pwd"].strip() == "Y":
            continue                        # one PwBD admit; separate pool
        fund, sub_cat = r["category"].strip(), r["sub_category"].strip()
        if fund == "Nri":
            key = ("Mizoram", "nri", "NRI")
        elif sub_cat == "ST":
            key = ("Mizoram", "", "ST")
        elif sub_cat in ("GENERAL", "SC", "OBC"):
            key = ("All India", "", sub_cat)
        else:
            continue
        if key not in best or marks < best[key]:
            best[key] = marks               # closing = LOWEST admitted marks
    CANON = {"ST": "ST", "GENERAL": "Gen", "SC": "SC", "OBC": "OBC", "NRI": None}
    return [_row(track, "Mizoram", "Zoram Medical College (ZMCH), Falkawn", "MBBS",
                 CANON[cat], cat if cat != "NRI" else "NRI", sub, _air_of(m),
                 "Govt", "mizoram_zmch_2025_register",
                 seat_type="All India" if track == "All India" else "State Quota")
            for (track, sub, cat), m in best.items()]


def chandigarh():
    """GMCH-32's official admitted list, parsed with the same fixed-column logic as
    the matrix builder (c[1]=AIR, c[15]=marks, c[4]=PwD, c[6]=pool, c[7]=category):
      pool contains 'AIQ' -> the hosted 15% seats -> track='All India'
      pool 'NRI'          -> skipped (fee pool)
      PwD rows            -> skipped (separate deep pool)
    One builder rule carried over: within a category, admits below 60% of the
    cluster's closing marks are unlabeled special seats (sports/defence type) —
    two such rows would put the 'General' closing at AIR 826,700 / 194 marks,
    which is not the general-merit bar. Same rule, same reason, documented there."""
    import pdfplumber
    pdf_path = NEET / "raw/chandigarh-gmch32-2025-admitted-list.pdf"
    if not pdf_path.exists():
        from google.cloud import storage
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        storage.Client().bucket("avantifellows-external-data").blob(
            "neet/raw/chandigarh-gmch32-2025-admitted-list.pdf").download_to_filename(pdf_path)
    recs = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                for raw in table:
                    if not raw or len(raw) < 17:
                        continue
                    c = [" ".join(str(x or "").split()) for x in raw]
                    if not c[0].isdigit():
                        continue
                    air, mk = c[1].replace(",", ""), c[15].replace(",", "")
                    if not (air.isdigit() and mk.isdigit()):
                        continue
                    recs.append(dict(air=int(air), marks=int(mk), ph=c[4],
                                     pool=c[6], sub=c[7]))
    CANON = {"General": "Gen", "Gen-EWS": "Gen-EWS", "OBC- NCL (Central List)": "OBC",
             "OBC": "OBC", "SC": "SC", "ST": "ST"}
    groups = defaultdict(list)
    for r in recs:
        if "PH" in r["ph"].upper() or "PWD" in r["ph"].upper():
            continue
        if "NRI" in r["pool"].upper():
            continue
        aiq = "AIQ" in r["pool"].upper()
        base = re.sub(r"\s*AIQ$", "", (r["pool"] if aiq else r["sub"]), flags=re.I).strip()
        canon = CANON.get(base)
        if not canon:
            continue
        groups[("All India" if aiq else "Chandigarh", base, canon)].append(r)
    out = []
    for (track, base, canon), rs in groups.items():
        top = max(x["marks"] for x in rs)
        kept = [x for x in rs if x["marks"] >= 0.6 * top]   # the unlabeled-special-seat rule
        closing = max(x["air"] for x in kept)
        out.append(_row(track, "Chandigarh",
                        "Government Medical College & Hospital, Sector 32, Chandigarh",
                        "MBBS", canon, base, "", closing, "Govt",
                        "chandigarh_gmch32_2025_register",
                        seat_type="All India" if track == "All India" else "State Quota"))
    return out


def all_extension_rows():
    rows = []
    for fn in (himachal, jk, assam, manipur, tripura, mizoram, chandigarh):
        got = fn()
        print(f"  +{len(got):4} rows  {fn.__name__}")
        rows.extend(got)
    return rows
