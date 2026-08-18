#!/usr/bin/env python3
"""
Build clean/neet_fact_cutoffs.parquet — the PER-COLLEGE NEET closing ranks that sit
underneath the 370-row matrix.

WHY THIS TABLE EXISTS
  Until now NEET was the only exam in this repo with no fact table. ~30 source documents
  went into GCS raw/ and only a 370-row summary came out the other side, so nobody could
  check a matrix number by drilling into the colleges behind it. Every sibling exam
  (tgeapcet / gujcet / kcet) publishes at college grain; this brings NEET in line.

  neet_dim_marks_matrix_2026 stays a hand-built artifact for now — it is VERIFIED and in
  use. This table is the evidence underneath it, not a replacement.

GRAIN  (state, institute, program, category_raw, round) — one row as published.

THE THREE ENRICHMENT COLUMNS, and how far each can be trusted:

  category / sub_pool  — 321 raw codes collapsed to the canonical 5 (+PwD handled as a
      sub_pool, not a category). 100% classified: 12,904 rows to a canonical category and
      796 correctly identified as non-caste pools (NRI / sports / defence / minority-
      institution), which get category = NULL by design.
      Every per-state mapping is LIFTED from the state builder that already made the call
      (futures-v2/neet/matrix_2026/builders/), not re-invented here. Karnataka is the
      exception: its builder only ever names the "G" variant, so the suffix grammar was
      derived from the data and verified to decompose 50 of its 76 codes.

  college_type — 65% filled, NULL elsewhere, and NEVER guessed. Measured 96% against the
      rows whose source already told us; of the 185 disagreements, 153 are cases where the
      SOURCE was wrong (it derived College Type from the seat type) and only 3 distinct
      colleges are genuine disagreements — on all 3 this classifier is right, and one of
      them (DENTAL COLLEGE, AZAMGARH) is the private college that once made UP's BDS floor
      read 232 marks. So true accuracy is ~99.6%.
      ★ A wrong govt flag is far worse than a missing one: it makes a college look ~250
        marks easier than it is and nothing about the row looks broken. Hence NULL.

  rank_space — always 'NEET AIR'. Tamil Nadu publishes STATE rank; it was converted via the
      validated score->AIR model upstream, so every row here is on one national scale.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

import sources as S

# The predictor dataset is the input: same rows the app serves, so they cannot drift.
PREDICTOR = Path("/Users/surya/jan2023/college-predictor")
NEETUG = PREDICTOR / "public/data/NEETUG/NEETUG.json"
ROSTER_DIR = PREDICTOR / "amogh-csv/medical-national-ranks/extracted_data"

# ══════════════════════════════════════════════════ category mapping
# canonical -> that state's raw base codes. Straight from the state builders.
# Keys beginning "_" are NOT canonical categories:
#   _obc_family  real OBC-family castes the matrix builder skips -> category OBC, caste kept
#   _pool        not a caste at all (sports / defence / minority / NRI) -> category NULL
SUBGROUPS: dict[str, dict[str, list[str]]] = {
    "Andhra Pradesh": {"Gen": ["OC"], "Gen-EWS": ["EWS"], "OBC": ["BCA", "BCB", "BCC", "BCD", "BCE"],
                       "SC": ["SC1", "SC2", "SC3"], "ST": ["ST"], "_pool": ["MINORITY", "ANGLO"]},
    "Bihar": {"Gen": ["UR"], "Gen-EWS": ["EWS"], "OBC": ["BC", "EBC"], "SC": ["SC"], "ST": ["ST"]},
    "Chhattisgarh": {"Gen": ["UR"], "Gen-EWS": ["EWS", "EW"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"]},
    "Delhi": {"Gen": ["Open"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"]},
    "Gujarat": {"Gen": ["OPEN"], "Gen-EWS": ["EW"], "OBC": ["SE"], "SC": ["SC"], "ST": ["ST"]},
    "Haryana": {"Gen": ["OPEN_CAT", "OPEN"], "Gen-EWS": ["EWS"], "OBC": ["BCA", "BCB"],
                "SC": ["SC", "SC_DEPRIVED"], "ST": []},
    # HP runs NO EWS in state counselling (neet_matrix_hp.py); the matrix has HP Gen-EWS as
    # N_A_NO_QUOTA. The single stray 'EWS' row in our thin extract is not a base category.
    "Himachal Pradesh": {"Gen": ["General"], "Gen-EWS": [], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"],
                         "_pool": ["EWS", "J&K Migrant", "Single Girl Child"]},
    "Jammu & Kashmir": {"Gen": ["OM"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"]},
    "Jharkhand": {"Gen": ["UR"], "Gen-EWS": ["EWS"], "OBC": ["BC-I", "BC-II"], "SC": ["SC"], "ST": ["ST"]},
    # Kerala: SEBC communities are the OBC base. DA/PD/PI/SD/XS/NC/AC/PT are special pools the
    # builder explicitly excludes (its ALLOWED set).
    "Kerala": {"Gen": ["SM"], "Gen-EWS": ["EW"],
               "OBC": ["EZ", "MU", "BH", "LA", "DV", "VK", "BX", "KN", "KU"], "SC": ["SC"], "ST": ["ST"],
               "_pool": ["NR", "AM", "MM", "PD", "AC", "XS", "PI", "DA", "PT", "NC", "SD", "CC",
                         "DK", "HR", "NM", "DM", "NQ"]},
    "Madhya Pradesh": {"Gen": ["UR"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"],
                       "_pool": ["Open"]},
    # MH: the matrix uses the literal 'OBC' bucket only (per Amogh), but SEBC / NT-B / NT-C /
    # NT-D / VJA are all genuinely OBC-family castes. The FACT table carries them as OBC with
    # the caste in sub_pool, so floor SQL filtering sub_pool='' still reproduces the builder.
    "Maharashtra": {"Gen": ["OPEN"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"],
                    "_obc_family": ["SEBC", "VJA", "NTB", "NTC", "NTD"],
                    "_pool": ["DEF1", "DEF2", "DEF3", "MKB", "MINO", "ORPHAN", "ORPHANC"]},
    "Odisha": {"Gen": ["GN"], "Gen-EWS": ["EW"], "OBC": [], "SC": ["SC"], "ST": ["ST"]},
    "Puducherry": {"Gen": ["Open"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"]},
    "Punjab": {"Gen": ["Open"], "Gen-EWS": ["EWS"], "OBC": ["Backward Classes"],
               "SC": ["Scheduled Caste"], "ST": [],
               "_pool": ["Sports Person", "Border Area", "Backward Area", "Defence",
                         "Riots Affected", "Terrorist Affected", "PP", "PWD", "J & K",
                         "2B", "2C", "2D", "2E", "2G"]},
    "Rajasthan": {"Gen": ["GEN"], "Gen-EWS": ["EWS"], "OBC": ["OBC", "MBC"], "SC": ["SC"],
                  "ST": ["ST", "SA"]},
    # TN runs its own communal reservation and has NO EWS.
    "Tamil Nadu": {"Gen": ["OC"], "Gen-EWS": [], "OBC": ["BC", "BCM", "MBC&DNC"],
                   "SC": ["SC", "SCA"], "ST": ["ST"]},
    "Telangana": {"Gen": ["OPEN"], "Gen-EWS": ["EWS"], "OBC": ["BCA", "BCB", "BCC", "BCD", "BCE"],
                  "SC": ["SC1", "SC2", "SC3"], "ST": ["ST"], "_pool": ["MIN"]},
    "Uttar Pradesh": {"Gen": ["UR"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"]},
    "Uttarakhand": {"Gen": ["UR"], "Gen-EWS": ["EWS"], "OBC": ["OBC"], "SC": ["SC"], "ST": ["ST"]},
    "West Bengal": {"Gen": ["UR"], "Gen-EWS": ["EWS"], "SC": ["SC"], "ST": ["ST"],
                    "OBC": ["OBC-A (Non- Creamy Layer)", "OBC-B (Non- Creamy Layer)",
                            "OBC (Non-Creamy Layer)"]},
}

AIQ = {"Gen": ["Open", "OPEN", "General", "UR"], "Gen-EWS": ["EWS"], "OBC": ["OBC", "OBC-NCL"],
       "SC": ["SC"], "ST": ["ST"]}

# Karnataka: KEA folds caste x (language / region / rural / disability) into ONE token,
# e.g. 2AKH = 2A x Kannada-medium x Hyderabad-Karnataka. Stems are matched longest-first.
KA_CASTE = {"GM": "Gen", "SC": "SC", "ST": "ST",
            "1": "OBC", "2A": "OBC", "2B": "OBC", "3A": "OBC", "3B": "OBC"}
KA_SUFFIX = {"G": "", "H": "hyderabad-karnataka", "K": "kannada-medium",
             "KH": "kannada-medium+hk", "R": "rural", "RH": "rural+hk",
             "P": "physically-disabled", "PH": "physically-disabled+hk", "": ""}
KA_POOL = {"NRI": "nri", "OPN": "private-open", "OTH": "private-other", "PHM": "pwd",
           "SPO": "sports", "NCC": "ncc", "CAP": "defence", "D": "defence", "XD": "ex-defence",
           "JK": "jammu-kashmir-migrant", "MU": "minority-muslim", "MC": "minority-christian",
           "MA": "minority-anglo", "ME": "minority-edu", "MEH": "minority-edu+hk",
           "MK": "minority-kannada", "MM": "minority", "MMH": "minority+hk",
           "S-G": "supernumerary", **{f"RC{i}": "religious-minority" for i in range(1, 8)}}

PAREN = re.compile(r"\s*\((.+)\)\s*$")
TRAILING_PWD = re.compile(r"\s+(PwD|PWD)$", re.I)
# MP compound code CASTE/HORIZONTAL/SUB. X = the general variant (the builder's base floor).
MP_HORIZ = {"X": "", "GS": "female", "PH": "pwd", "SN": "freedom-fighter-kin", "FF": "freedom-fighter"}
KERALA_PREFIX = re.compile(r"^(SM|FL)-(.+)$")


def _split_paren(code: str) -> tuple[str, str]:
    m = PAREN.search(code)
    if not m:
        return code.strip(), ""
    return PAREN.sub("", code).strip(), m.group(1).strip().lower()


def _map_karnataka(code: str) -> tuple[str | None, str]:
    if code in KA_POOL:
        return None, KA_POOL[code]
    for stem in sorted(KA_CASTE, key=len, reverse=True):
        if code.startswith(stem):
            suf = code[len(stem):]
            if suf in KA_SUFFIX:
                return KA_CASTE[stem], KA_SUFFIX[suf]
    return None, ""


def map_category(state: str, source: str, code: str) -> tuple[str | None, str]:
    """raw code -> (canonical category | None, sub_pool)."""
    if source.startswith("karnataka"):
        return _map_karnataka(code)

    code = code.strip()
    extra: list[str] = []

    m = TRAILING_PWD.search(code)          # "UR PwD" -> base UR, sub_pool pwd
    if m:
        extra.append("pwd")
        code = TRAILING_PWD.sub("", code).strip()

    table = AIQ if source.startswith("aiq") else SUBGROUPS.get(state) or {}

    # WB writes creamy-layer status INSIDE the parens as part of the category name
    # ("OBC-A (Non- Creamy Layer)"), so try the whole string before stripping.
    if any(code in v for v in table.values()):
        base, paren = code, ""
    else:
        base, paren = _split_paren(code)
    if paren:
        extra.append(paren)

    if source.startswith("mp_") and "/" in base:
        parts = base.split("/")
        base = parts[0]
        if len(parts) > 1 and MP_HORIZ.get(parts[1]):
            extra.append(MP_HORIZ[parts[1]])

    if source.startswith("kerala"):
        km = KERALA_PREFIX.match(base)
        if km:
            extra.append("state-merit" if km.group(1) == "SM" else "fee-liability")
            base = km.group(2)
        base = base.rstrip(" *")

    canon = None
    for c, codes in table.items():
        if base in codes:
            if c == "_obc_family":
                canon = "OBC"
                extra.insert(0, base.lower())
            elif c.startswith("_"):
                extra.insert(0, base.lower())
            else:
                canon = c
            break
    return canon, ", ".join(x for x in extra if x)


# ══════════════════════════════════════════════════ college_type
STOP = {"medical", "college", "dental", "sciences", "science", "institute", "of", "and",
        "hospital", "research", "centre", "center", "the", "dr", "shri", "sri", "smt",
        "mc", "dc", "gmc", "gdc", "govt", "government", "university", "school", "studies",
        "post", "graduate", "pg", "hosp", "med", "col", "instt", "inst"}

GOVT_KEYWORDS = re.compile(
    r"\b(aiims|jipmer|pgimer|nimhans|government|govt|"
    r"maulana azad medical|lady hardinge|vardhman mahavir|"
    r"university college of medical sciences|ndmc medical|"
    r"employees state insurance|esic)\b", re.I)

# Abbreviations that ONLY ever expand to a government institution — verified against the NMC
# roster: no private college in it uses any of these. Not anchored to the start, because
# Maharashtra prefixes the founder's name ("V.D. GMC LATUR", "MS KANNAMWAR GMC CHANDRAPUR").
GOVT_ABBR = re.compile(r"\b(gmc|gdc|ggmc|bjmc|gsmc|igmc|iggmc|ltmmc|tnmc|jjh|srtr|rcsm|"
                       r"vnmc|vmmc|esic|esi)\b", re.I)

# Kerala writes a short college CODE, a hyphen, then the real name:
#   "WYM- Govt. Medical College, Wayanad"      <- genuinely government
#   "GMC- Sree Gokulam Medical College"        <- PRIVATE; its code merely reads GMC
# So the code itself proves nothing either way. Strip it and judge the REST of the name.
# (An earlier version skipped the govt test whenever a code was present, which threw away
# every real Kerala government college — caught because the Kerala drill-down went empty.)
# The trailing \s+ is load-bearing: Kerala's codes are followed by a space ("WYM- Govt..."),
# whereas "ESI-MC&PGIMS&R" is one hyphenated name and must not be truncated to "MC&PGIMS&R".
CODE_PREFIX = re.compile(r"^[A-Z][A-Z0-9&.]{1,5}-\s+")


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _toks(s) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", str(s).lower()) if t not in STOP and len(t) > 2}


def _load_roster():
    by_prog: dict[str, list] = defaultdict(list)
    for fname, prog in [("mbbs_all_colleges_2025-26.csv", "MBBS"),
                        ("bds_all_colleges_2025-26.csv", "BDS")]:
        p = ROSTER_DIR / fname
        if not p.exists():
            raise SystemExit(f"missing roster {p} — see ROSTER_FILES in sources.py")
        for r in csv.DictReader(open(p)):
            name = r.get("college") or ""
            if not _norm(name):
                continue
            mg = "Govt" if "govt" in str(r.get("mgmt", "")).lower() else "Private"
            by_prog[prog].append((_norm(name), _toks(name), mg, str(r.get("state") or "")))
    exact = {}
    for prog, lst in by_prog.items():
        seen = defaultdict(set)
        for n, _, mg, _ in lst:
            seen[n].add(mg)
        exact[prog] = {n: next(iter(v)) for n, v in seen.items() if len(v) == 1}
    return by_prog, exact


ROSTER, ROSTER_EXACT = _load_roster()


def college_type(institute: str, prog: str, state: str) -> tuple[str | None, str | None]:
    """-> (Govt | Private | None, which rung decided it)."""
    n = _norm(institute)
    v = ROSTER_EXACT.get(prog, {}).get(n)
    if v:
        return v, "R1-exact-roster"

    # Govt by definition — must run BEFORE token matching, which would otherwise call
    # "AIIMS-Bhopal" and "Govt Medical College, Palakkad" Private (a 1-2 token name is a
    # subset of many roster rows).
    #
    # ...judged on the name WITHOUT its leading college code, so "GMC- Sree Gokulam"
    # (private, code merely reads GMC) is not mistaken for a Government Medical College,
    # while "WYM- Govt. Medical College, Wayanad" still resolves correctly.
    bare = CODE_PREFIX.sub("", str(institute).strip())
    if GOVT_KEYWORDS.search(bare) or GOVT_ABBR.search(bare):
        return "Govt", "R2-govt-by-name"

    mine = _toks(institute)
    if len(mine) < 2:
        return None, None
    sn = _norm(state)
    got = set()
    for _, rt, mg, rstate in ROSTER.get(prog, ()):
        if len(rt) < 2:
            continue
        # state must agree — stops "GMC Nagpur" matching a Kerala college
        rs = _norm(rstate)
        if sn and rs and rs not in sn and sn not in rs:
            continue
        if rt <= mine or mine <= rt:
            got.add(mg)
            continue
        # Strict containment misses when each side has a token the other lacks: the roster
        # appends the city ("Vijaynagar IMS, Bellary") and spellings drift ("Vijayanagar").
        inter = rt & mine
        if len(inter) >= 2 and len(inter) >= min(len(rt), len(mine)) - 1:
            got.add(mg)
    if len(got) == 1:
        return next(iter(got)), "R3-token+state"
    return None, None


# ══════════════════════════════════════════════════ state names
# Spellings are aligned to neet_dim_marks_matrix_2026.state so the two tables JOIN.
# The last entry is not a rename but a REPAIR: the AIQ PDF bled a college address into the
# state column ("Govt Medical College Badaun", 5 rows), the same column-bleed class of bug
# that repair_state_bleed() fixes in the nmc/ pipeline.
CANON_STATE = {
    "Delhi (NCT)": "Delhi",
    "Andaman And Nicobar Islands": "Andaman & Nicobar",
    "Dadra And Nagar Haveli": "Dadra & Nagar Haveli and Daman & Diu",
    "Jammu And Kashmir": "Jammu & Kashmir",
    "Gunera Wazidpur Ujhani Road Badaun U.P. 243601": "Uttar Pradesh",
}


# ══════════════════════════════════════════════════ build
def build() -> pd.DataFrame:
    rows = json.load(open(NEETUG))
    out = []
    for r in rows:
        try:
            air = int(str(r["Closing Rank"]).strip())
        except (TypeError, ValueError, KeyError):
            continue
        prog = r["Academic Program Name"]
        state = r["State"]
        source = r["Source"]
        # HP: our own parse is too thin (34 rows, General-only) and the matrix
        # rejected it for the full dropbox extract ("SOURCE = THEIRS"). The fact
        # table follows the same per-track source choice — the fuller HP rows come
        # from fact_extension_tracks.himachal(); keeping both would double-count
        # the same college x category buckets under two sources.
        if source == "himachal_2025_r3_cutoffs":
            continue
        canon, sub = map_category(state, source, r["Category"])
        ct, rung = college_type(r["Institute"], prog, state)
        # `track` is the competition (matches neet_dim_marks_matrix_2026.state);
        # `college_state` is where the college physically is. For AIQ these differ: one
        # national track spanning 34 states. Keeping both means "AIQ seats in Karnataka"
        # is answerable, which collapsing to a single label would have destroyed.
        college_state = CANON_STATE.get(state.strip(), state.strip())
        # Two quotas ride in the MCC file but are NOT the 15% AIQ competition: Delhi
        # University Quota (Delhi's own domicile door, 3 colleges + MAIDS) and JIPMER's
        # Puducherry-internal quota. The matrix has always tracked them separately;
        # leaving them under 'All India' made "AIQ colleges" queries silently include
        # seats no out-of-state student can get.
        seat = str(r.get("Seat Type") or "")
        if seat == "Delhi University Quota":
            track = "Delhi"
        elif seat == "Internal -Puducherry UT Domicile":
            track = "Puducherry"
        else:
            track = "All India" if source.startswith("aiq") else college_state
        out.append({
            "track": track,
            "college_state": college_state,
            "institute": r["Institute"].strip(),
            "address": (r.get("Address") or "").strip(),
            "program": prog,
            "category": canon,
            "category_raw": r["Category"],
            "category_label": r.get("Category Label") or "",
            "sub_pool": sub,
            "seat_type": r.get("Seat Type") or "",
            "college_type": ct,
            "college_type_method": rung,
            "seat_gender": r.get("Gender") or "",
            "closing_rank": air,
            "rank_space": r.get("rank_space") or "",
            "round": r.get("Round") or "",
            "exam_year": 2025,
            "source": source,
        })
    # the nine tracks beyond NEETUG.json's coverage — built from the same staged
    # extracts the matrix used; see fact_extension_tracks.py for per-track rules
    from fact_extension_tracks import all_extension_rows
    out.extend(all_extension_rows())

    df = pd.DataFrame(out)
    df["closing_rank"] = df["closing_rank"].astype("Int64")
    df["exam_year"] = df["exam_year"].astype("Int64")
    return df


if __name__ == "__main__":
    df = build()
    S.CLEAN.mkdir(parents=True, exist_ok=True)
    target = next(t for t in S.TABLES if t.bq_name == "neet_fact_cutoffs")
    df.to_parquet(target.local_path, index=False)

    n = len(df)
    print(f"wrote {target.local_path}  ({n} rows)")
    print(f"  tracks           : {df['track'].nunique()}")
    print(f"  college states   : {df['college_state'].nunique()}")
    print(f"  institutes       : {df['institute'].nunique()}")
    print(f"  category filled  : {df['category'].notna().sum()} ({100*df['category'].notna().sum()//n}%)")
    print(f"  college_type     : {df['college_type'].notna().sum()} ({100*df['college_type'].notna().sum()//n}%)")
    print(f"  sub_pool present : {(df['sub_pool'] != '').sum()}")
    print("\n  college_type by method:")
    print(df["college_type_method"].value_counts(dropna=False).to_string())
    print("\n  programs:", dict(df["program"].value_counts()))
