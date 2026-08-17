#!/usr/bin/env python3
"""
Maharashtra NEET-UG (MH-CET Cell) 2025 CAP Round-3 parser -> closing-rank cutoffs.

The PDF is a space-aligned text report (NOT a ruled table, so pdfplumber's
table extraction finds nothing — we parse text lines with a regex instead).
Each data line is one allotted candidate:

  Sr  AIR  NEETRoll  FormNo  Name...  G  Cat [subflags...]  CODE:College(status)

  1 629 3110416106 256021396 SARTHAK SATISH VALEKAR M OPEN 1103:GSMC MUMBAI(Ret.)
  6 1115 3110201398 256029299 REYA MEHENDALE F D1 DEF1 W 1103:GSMC MUMBAI(No Pref)
  8 1127 3110116136 256023054 HAZEL PUNMIYA F OPEN (W) 1103:GSMC MUMBAI(No Pref)

Anchors used to parse the variable-width line:
  - leading  "<Sr> <AIR> <10-digit roll> <form>"  (AIR = NEET All India Rank)
  - Gender token  M|F  separates the Name from the Category
  - college token "<3-4 digits>:<name>(<status>)" ends the line; everything
    between Gender and the college token is Category + optional sub-flags.

Rows with no college (e.g. "... Disqualified-Allotted by MCC") are skipped.
Cutoff = MAX AIR per (college, category). rank_space = 'NEET AIR'.
"""
from __future__ import annotations
import argparse, csv, re, sys, warnings
from collections import Counter
from pathlib import Path
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _institute import program_from_name

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "source" / "maharashtra.pdf"
DEFAULT_OUT = ROOT / "extracted_data" / "neet_maharashtra_2025_r3_cutoffs.csv"

# A data line: Sr AIR Roll(10) Form ... then the rest.
LINE_RE = re.compile(r"^(\d+)\s+(\d+)\s+(\d{10})\s+(\d+)\s+(.*)$")
# The allotted college is 'NNNN:College Name[(status)]' running to end of line.
# The trailing status (Ret.)/(No Pref) is OPTIONAL and sometimes wraps mid-token
# ("...(No"), so we grab from the code to end-of-line and strip any trailing
# parenthetical (or dangling "(word") afterwards. Requiring the '()' here was a
# bug that silently dropped ~75% of rows.
COLLEGE_RE = re.compile(r"(\d{3,4}):(.+)$")
STATUS_TAIL_RE = re.compile(r"\s*\([^()]*\)?\s*$")  # trailing (status) or dangling "(No"
# Gender token that separates Name from Category.
GENDER_RE = re.compile(r"\b([MF])\b")

# The Maharashtra allotment segment (between the gender token and the college) is
#     <eligibility_category> <ALLOTTED_SEAT_CODE> [Against <x>] [(EMR|EMD)]
# and it is the ALLOTTED seat that determines the cutoff, e.g.:
#     'OPEN'                      -> allotted OPEN                 (clean)
#     'D1 DEF1 W'                 -> allotted DEF1, female
#     'SC EMSC (EMR)'             -> allotted EarMarked-SC, EMR=Receiver
#     'OBC OPEN (EMD)'            -> an OBC student took an OPEN seat, EMD=Donor
#     'NTC PWD-NTC Against PH-NT2'-> allotted PWD-NTC  (PWD sub-pool)
#     'NTD ORP-C ORPHANC OrphanC' -> allotted ORPHANC  (orphan sub-pool)
# The OLD parser scanned right-to-left for ANY base category, so it:
#   (a) folded the PWD / Orphan / EarMark sub-pools (which are DISTINCT, much
#       deeper seat pools) into the plain base category and let MAX inflate it to
#       300k-1.3M (GSMC Mumbai VJA=622131 was a 'PWD-VJA' seat), and
#   (b) mislabeled the EM/EarMarking prefix as "EWS-Minority" (it is NOT EWS).
# We now decode the ALLOTTED seat into a base category + flags for the real sub-
# pools, so each pool is its own bucket at its true rank. EMR/EMD (EarMarking
# Receiver/Donor) is captured as its own field.
BASE_CATEGORIES = {
    "OPEN", "OBC", "SEBC", "EWS", "SC", "ST",
    "NTB", "NTC", "NTD", "VJA", "MINO", "MKB",
    "DEF1", "DEF2", "DEF3", "ORPHAN", "ORPHANC",
}
# 'I.Q.' (Institute Quota) is a SEAT TYPE, not a social category — handled apart.
IQ_TOKEN = "I.Q."


def _decode_allotted(tok):
    """Decode one allotted-seat token into (base, is_home, is_earmark, is_pwd,
    is_orphan) or None. Handles H<cat>, EM<cat>, PWD-<cat>, ORPHAN[C], ORP-<x>."""
    t = tok.strip().upper().strip("-")
    if not t:
        return None
    is_pwd = t.startswith("PWD")
    if is_pwd:
        t = t[3:].strip("-")                      # PWD-NTC -> NTC
    is_orphan = t.startswith("ORPHAN") or t.startswith("ORP")
    if is_orphan:
        # ORPHAN / ORPHANC / ORPHANC-OB / ORP-C  -> keep as an ORPHAN pool
        base = "ORPHANC" if "ORPHANC" in t or t.startswith("ORP-C") else "ORPHAN"
        return base, False, False, is_pwd, True
    is_earmark = t.startswith("EM")
    if is_earmark:
        t = t[2:]                                 # EMSC -> SC
    is_home = t.startswith("H") and t[1:] in BASE_CATEGORIES
    if is_home:
        t = t[1:]                                 # HOBC -> OBC
    if t in BASE_CATEGORIES:
        return t, is_home, is_earmark, is_pwd, False
    return None


def classify_category(seg: str):
    """From the allotment segment return a dict describing the ALLOTTED seat, or
    None if it can't be resolved.

    keys: base, is_female, is_home, is_earmark, em_role ('Receiver'/'Donor'/''),
          is_pwd, is_orphan, is_iq
    """
    U = seg.upper()
    is_female = ("(W)" in U) or bool(re.search(r"\bW\b", U))
    # I.Q. (Institute Quota) is a seat-TYPE flag that rides alongside the social
    # category (e.g. 'I.Q. MINO' = an Institute-Quota MINORITY seat). Record it as
    # a flag, then strip it so the base category is still decoded from the rest.
    is_iq = (IQ_TOKEN in U) or bool(re.search(r"\bIQ\b", U))
    # EMR/EMD ride in a trailing parenthetical.
    em_role = ""
    if "(EMR" in U:
        em_role = "Receiver"
    elif "(EMD" in U:
        em_role = "Donor"
    # PwD and Orphan markers can appear as a SEPARATE token (e.g. 'SEBC PEM SEBC
    # PH (EMR)' — the PH sits apart from the allotted 'SEBC'), so detect them at
    # the whole-segment level too, not only as a prefix on the allotted token.
    seg_pwd = bool(re.search(r"\bPH\b|\bPWD", U)) or "PEM" in U
    seg_orphan = "ORP" in U
    # Strip parentheticals, standalone W, I.Q., and the "Against ..." trailer.
    s = re.sub(r"\([^)]*\)", " ", seg)
    s = re.sub(r"\bW\b", " ", s)
    s = re.sub(r"\bI\.?Q\.?\b", " ", s, flags=re.IGNORECASE)
    if " AGAINST" in s.upper():
        s = s[: s.upper().index(" AGAINST")]
    toks = s.split()
    # eligibility is toks[0]; the allotted seat is the next decodable token. Try
    # the later tokens first (the allotted seat), fall back to the first.
    order = toks[1:] + toks[:1] if len(toks) > 1 else toks
    for tok in order:
        d = _decode_allotted(tok)
        if d:
            base, is_home, is_earmark, is_pwd, is_orphan = d
            return {"base": base, "is_female": is_female, "is_home": is_home,
                    "is_earmark": is_earmark or bool(em_role), "em_role": em_role,
                    "is_pwd": is_pwd or seg_pwd, "is_orphan": is_orphan or seg_orphan,
                    "is_iq": is_iq}
    # I.Q. with no decodable social category -> treat as an open institute seat.
    if is_iq:
        return {"base": "OPEN", "is_female": is_female, "is_home": False,
                "is_earmark": False, "em_role": em_role, "is_pwd": False,
                "is_orphan": False, "is_iq": True}
    return None


def parse(src: Path):
    # key -> max AIR, where key = (code, name, base_cat, female, home, em)
    buckets = {}
    n = skip_nocollege = skip_other = skip_nocat = 0
    with pdfplumber.open(src) as pdf:
        for page in pdf.pages:
            for raw in (page.extract_text() or "").split("\n"):
                line = raw.strip()
                m = LINE_RE.match(line)
                if not m:
                    continue
                air = int(m.group(2))
                rest = m.group(5)  # "Name... G Cat [flags] CODE:College(status)"

                col = COLLEGE_RE.search(rest)
                if not col:
                    # e.g. "Choice Not Available" / "Disqualified" — no seat
                    skip_nocollege += 1
                    continue
                code = col.group(1)
                cname = STATUS_TAIL_RE.sub("", col.group(2)).strip()
                pre = rest[: col.start()].strip()  # "Name... G Cat [flags]"

                gmatches = list(GENDER_RE.finditer(pre))
                if not gmatches:
                    skip_other += 1
                    continue
                after_gender = pre[gmatches[-1].end():].strip()
                if not after_gender:
                    skip_other += 1
                    continue

                cls = classify_category(after_gender)
                if cls is None:
                    # no recognised category token — report, don't silently keep
                    skip_nocat += 1
                    continue

                n += 1
                # Key on the full seat identity so distinct pools (base + the
                # PWD/Orphan/EarMark/home sub-pools) never merge under MAX. The
                # sub-pool axis is what stops one PWD/Orphan seat (deep rank) from
                # poisoning the plain base-category cutoff.
                key = (code, cname, cls["base"], cls["is_female"], cls["is_home"],
                       cls["is_earmark"], cls["em_role"], cls["is_pwd"],
                       cls["is_orphan"], cls["is_iq"])
                if air > buckets.get(key, 0):
                    buckets[key] = air
    return buckets, n, skip_nocollege, skip_other, skip_nocat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    buckets, n, skip_nc, skip_o, skip_nocat = parse(args.src)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Institute", "State", "Institute Code", "Category",
                    "Is Female Seat", "Is Home University", "Is PwD Seat",
                    "Is Orphan Seat", "Is EarMark Seat", "EarMark Role",
                    "Academic Program Name", "Seat Type", "Round",
                    "Closing Rank", "rank_space"])
        review = set()
        for (code, cname, base, female, home, earmark, em_role, pwd, orphan,
             iq), air in sorted(buckets.items(), key=lambda x: x[1]):
            program = program_from_name(cname)
            if program == "REVIEW":
                review.add(cname)
            # Compose a readable category: base + the sub-pool tags that make this
            # a DISTINCT seat (PwD / Orphan / EarMark). Home-University and Female
            # are separate flag columns the assembler already folds in.
            tags = []
            if pwd:
                tags.append("PwD")
            if orphan:
                tags.append("Orphan")
            if earmark:
                tags.append("EarMark")
            category = f"{base} ({', '.join(tags)})" if tags else base
            # I.Q. (Institute Quota) is a seat TYPE, not a social category.
            seat_type = "Institute Quota" if iq else "State Quota"
            w.writerow([cname, "Maharashtra", code, category,
                        "Yes" if female else "No", "Yes" if home else "No",
                        "Yes" if pwd else "No", "Yes" if orphan else "No",
                        "Yes" if earmark else "No", em_role,
                        program, seat_type, "R3", air, "NEET AIR"])

    # miss rate: rows with a college but no recognisable category (the floor)
    allotted = n + skip_nocat
    miss_pct = 100 * skip_nocat / allotted if allotted else 0
    print(f"wrote {args.out}: {len(buckets)} buckets from {n} allotted rows")
    print(f"  skipped: {skip_nc} no-college (Choice Not Available/DQ), "
          f"{skip_o} no-gender, {skip_nocat} no-recognised-category")
    print(f"  category miss rate (of rows WITH a college): "
          f"{skip_nocat}/{allotted} = {miss_pct:.2f}%")
    print("  colleges:", len({(c, nm) for c, nm, *_ in buckets}))
    print("  base categories:", dict(Counter(k[2] for k in buckets)))
    print("  PwD buckets:", sum(1 for k in buckets if k[7]),
          "| Orphan:", sum(1 for k in buckets if k[8]),
          "| EarMark:", sum(1 for k in buckets if k[5]),
          "| I.Q.:", sum(1 for k in buckets if k[9]))
    print("  female-seat buckets:", sum(1 for k in buckets if k[3]))
    if review:
        print(f"  ⚠ program REVIEW (name matched both/neither MC/DC) — {len(review)} colleges:")
        for nm in sorted(review):
            print(f"      {nm}")
    else:
        print("  program (MBBS/BDS from college name): 0 colleges need review")


if __name__ == "__main__":
    main()
