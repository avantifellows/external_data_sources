#!/usr/bin/env python3
"""
Build jnv_student_journey_mapping_v2 — a CLEAN-SLATE rewrite of the JNV
cross-table student journey/identity mapping.

This is a fresh design. Instead of v1's bespoke anchored spines
(build_student_journey_mapping.py → jnv_student_outcome_mapping), v2 treats
identity resolution as a GRAPH problem:

    every source record is a NODE  →  trusted links between records are EDGES
    →  each connected component is ONE STUDENT  →  explode to one row per
       (student, attempt_year).

That single idea removes all the "which stage anchors whom" special-casing:
a student who only has NCST is just a size-1 component; a full-journey student
is a component spanning all five stages. Same machinery either way.

Journey stages, in order:  NCST → 10th → 12th → JEE → NEET.

Scope: ALL JNV students across the five source tables (no Avanti filter).

Grain: one row per (student, attempt_year) where
  • attempt_year = the year of an ENTRANCE sitting (JEE/NEET test_year). JEE and
    NEET in the same year share one row; a retake in a new year is a new row; a
    student with no entrance record gets one row with attempt_year = NULL.
  • cohort_year = expected graduation, CONSTANT per student:
        COALESCE(12th_year, 10th_year+2, NCST_year+2, earliest entrance year)
  • the pre-entrance stages (NCST/10th/12th) REPEAT on every one of the
    student's rows, so each row is self-contained.

Linkage posture: OVER-SPLIT (precision-first). An identity edge is drawn only
when it is UNAMBIGUOUS (maps 1:1 at the component level) and journey-consistent
(the two records' years are the right distance apart). When in doubt we leave
two records as separate single-stage students rather than risk fusing two real
people — union-find is transitive, so one bad edge would chain whole clusters.

SCOPE OF THIS FILE: steps 1–8 (identity map + Avanti fk + outcome marks + load).
The output is the identity MAP
(student_key + cohort/attempt years + each stage's natural join key) plus the
Avanti fk (step 6). fk_avanti_student_id / match_confidence / match_count are
computed by this file's OWN tiered name+DOB(+father) matcher against dim_student
(see _read_avanti_reference / _build_sid / _match_fk_v2) — ported from v1's
_read_avanti / _match_fk, so v2 no longer depends on v1 having already run.
Covers ALL five stages including NCST through the SAME pipeline: v2's union-find
already attaches an NCST record to a b10/b12/jee/neet-anchored student by
identity where one exists (IDENTITY_RULES), so the only remaining gap was an
NCST-only student never entering `sid` at all — closed by folding ncst into
_build_sid's coalesce + a name+father tier (v1 kept NCST matching in a fully
separate function, _resolve_ncst; this build deliberately does not — one unified
matcher for every stage). Marks / outcome columns (step 7) are ALSO included —
ported verbatim from v1's _read_marks + _enrich (see _read_marks / _build_rows),
so the output is column-identical to v1 (47 cols, same order).

Output table: this build IS the production mapping — it writes the CANONICAL
`jnv_student_outcome_mapping`, REPLACING v1 (build_student_journey_mapping.py,
retired 2026-07-22; pre-cutover v1 content preserved in
`jnv_student_outcome_mapping_v1_backup`):
    avantifellows.external_data_sources.jnv_student_outcome_mapping

Usage:
    python3 scripts/build_student_journey_mapping_v2.py
"""

import difflib
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (BQ_PROJECT, BQ_DATASET, BQ_LOCATION,
                     POOJITA, TENTH_SCORE, JEE_2024_RAW, JEE_2025_RAW, NEET_2024_RAW,
                     NCST_2024_RAW_CANDIDATES, NCST_2024_RAW_SHEET)

# This build IS the production JNV student outcome mapping — it writes the
# canonical `jnv_student_outcome_mapping` table, REPLACING v1
# (build_student_journey_mapping.py, retired 2026-07-22). Pre-cutover v1 content
# is preserved in `jnv_student_outcome_mapping_v1_backup`.
OUT_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.jnv_student_outcome_mapping"

# Output columns — pure identity map + Avanti fk (step 6). The per-stage
# name/father/mother/dob comparison columns served their purpose (9 rounds of QA,
# see data-assistant-pr44.md findings #1-9) and are dropped here; each stage's
# natural join key (roll/app/test_year) is kept so a consumer can still reach the
# source row directly. Marks / outcome columns (step 7) remain deferred.
# Column-identical to v1 (jnv_student_outcome_mapping): same 47 columns in the same
# order, so v2 is a drop-in replacement. v2's own `attempt_year` column is dropped
# from the OUTPUT to match v1 exactly (v1 encodes the same grain via jee/neet
# _test_year); it is still used internally for sorting. STEP 7 (the outcome/marks
# payload below the join keys) is ported from v1's _read_marks + _enrich.
FINAL_COLS = [
    "student_key", "cohort_year", "fk_avanti_student_id",
    "match_confidence", "match_count",
    "student_program", "student_product",
    # stage-availability flags — STUDENT-LEVEL (true if the student has that stage
    # in ANY of their rows, broadcast onto every row so one row is enough to filter).
    "has_ncst_data", "has_10th_data", "has_12th_data", "has_jee_mains_data", "has_jee_adv_data", "has_neet_data",
    # NCST (selection test — Stage 1, upstream of 10th board)
    "ncst_source", "ncst_test_year", "ncst_roll_no",
    # 10th
    "board_10th_exam_year", "board_10th_roll_number",
    "marks_10_obtained", "result_10",
    "marks_10_math", "marks_10_science", "marks_10_english",
    # 12th
    "board_12th_exam_year", "board_12th_roll_number",
    "marks_12_obtained", "result_12",
    "marks_12_physics", "marks_12_chemistry", "marks_12_maths", "marks_12_biology",
    # JEE (incl. advanced)
    "jee_test_year", "jee_application_no",
    "jee_total_percentile", "jee_air", "jee_category_rank",
    "jee_mains_qualified", "jee_advanced_qualified",
    "jee_adv_all_india_rank", "jee_adv_category_rank", "jee_adv_prep_category_rank",
    # NEET
    "neet_test_year", "neet_application_no",
    "neet_total_score", "neet_air", "neet_category_rank", "neet_qualified",
]

STAGES = ["ncst", "b10", "b12", "jee", "neet"]

# Board-result files we hold (10th & 12th), by exam_year. A roll number is unique
# only WITHIN a year, so a 12th/10th roll named in a crosswalk must be resolved
# per-year (see _roll_cols) — the right year is chosen by the name gate. Searching
# every year (not just the on-time one) is what links DROPPERS, whose 12th board
# record sits an earlier year than their entrance sitting.
BOARD_YEARS = ["2022", "2023", "2024", "2025"]


# ─────────────────────────────────────────────────────────────────────────────
# small helpers
# ─────────────────────────────────────────────────────────────────────────────
def _S(s: pd.Series) -> pd.Series:
    """Trimmed pandas-string; NA stays NA."""
    return s.astype("string").str.strip()


def _present(s: pd.Series) -> pd.Series:
    """Mask: value is non-NA and non-empty."""
    v = s.astype("string")
    return v.notna() & (v.str.len() > 0)


def _blank_to_na(s: pd.Series) -> pd.Series:
    return s.where(_present(s))


# Name-agreement gate for the DETERMINISTIC crosswalk bridges. A roll/app/id
# crosswalk links records by key regardless of name, so a misaligned crosswalk
# row silently fuses two different people (measured worst on the NEET-2024 file:
# ~12% of its roll edges join disagreeing names). We therefore accept a crosswalk
# edge only when the two records' names AGREE. Agreement tolerates the variant
# patterns real in this data, so a genuine crosswalk match is not thrown away:
#   • spacing / dots         'KALYANI.S.H'      ≈ 'KALYANI S H'
#   • concatenation          'VIPUL KUMAR'      ≈ 'VIPULKUMAR'
#   • honorific-suffix/prefix 'JINAL VAGHELA'   ≈ 'JINALBEN VAGHELA'  (Gujarati -ben,
#                             'RAVI PATEL' ≈ 'RAVIKUMAR PATEL'         -kumar, -bhai …)
# It still rejects genuinely different names, so the misaligned-crosswalk fusions
# stay blocked ('SUNITA KUDIYAM' vs 'S R ALOK DAS'; 'LAXMI KUMARI' vs 'PREMKISHAN
# KUMAR' — sharing only the ubiquitous '-kumar' token). (Same lesson v1 encoded in
# _corroborate_roll10x.)
#
# Rule: agree iff the names are equal ignoring spaces/dots, OR ≥ 2 tokens agree —
# where two tokens agree if equal or one is a ≥4-char prefix of the other (the
# honorific-suffix variant). Requiring TWO agreeing tokens is what separates a real
# variant ('JINAL VAGHELA' ≈ 'JINALBEN VAGHELA': given name + surname both agree)
# from a coincidental single common token ('… KUMARI' ≈ '… KUMAR': surname only).
_TOK_PREFIX_MIN = 4
_MIN_SHARED_TOKENS = 2


def _tok_match(x, y) -> bool:
    if x == y:
        return True
    lo, hi = (x, y) if len(x) <= len(y) else (y, x)
    return len(lo) >= _TOK_PREFIX_MIN and hi.startswith(lo)   # 'JINAL' ⊂ 'JINALBEN'


def _bipartite_match_count(small: list, big: list) -> int:
    """Max 1-to-1 matching size between two token lists under _tok_match (Kuhn's
    augmenting-path algorithm; lists are always short — a handful of name tokens —
    so no need for anything fancier). ONE-TO-ONE matters: a naive per-token "does
    this token match something in the other list" count lets a REPEATED initial
    double-count against a single occurrence on the other side — 'SUMANTH M M' vs
    'PRATHIBHA B M' scores 2 ('M' matches the other's lone 'M' twice) and wrongly
    passes the ≥2-shared-tokens gate, fusing two different people (caught via a
    reused board roll bridging their records across years). A true matching caps
    each 'M' at one partner, scoring 1 — correctly below the threshold."""
    match_big = [-1] * len(big)

    def try_assign(i, visited):
        for j in range(len(big)):
            if _tok_match(small[i], big[j]) and not visited[j]:
                visited[j] = True
                if match_big[j] == -1 or try_assign(match_big[j], visited):
                    match_big[j] = i
                    return True
        return False

    return sum(try_assign(i, [False] * len(big)) for i in range(len(small)))


def _name_agree(a, b) -> bool:
    if not a or not b:
        return False
    a, b = str(a), str(b)
    if a.replace(" ", "").replace(".", "") == b.replace(" ", "").replace(".", ""):
        return True
    ta = [t for t in a.replace(".", " ").split() if t]
    tb = [t for t in b.replace(".", " ").split() if t]
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return _bipartite_match_count(small, big) >= _MIN_SHARED_TOKENS


def _name_subset(a, b) -> bool:
    """True if the shorter name's tokens are ALL matched (equal or ≥4-char prefix), ONE
    -TO-ONE, into the longer one — i.e. one name is the other with tokens dropped,
    reordered, or a middle name added (`SAMEER PAZARE` ⊆ `SAMEER ANIL PAZARE`;
    `KALYANI VIJAY KAMBLE` = `KAMBLE KALYANI VIJAY`). STRICTER than _name_agree (which
    needs only 2 shared tokens): it rejects sibling/twin pairs that share a surname but
    each carry a DISTINCT given name (`SUMIT RANJAN SINGH` vs `MOHIT RANJAN SINGH` —
    neither is a subset). 1-to-1 matching (not "each small token matches something")
    matters here too: `['M','M']` must NOT be judged a subset of `['M']`. Used to gate
    the DOB-anchored merge so identical-DOB twins don't fuse."""
    ta = [t for t in str(a).replace(".", " ").split() if t]
    tb = [t for t in str(b).replace(".", " ").split() if t]
    if not ta or not tb:
        return False
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return _bipartite_match_count(small, big) == len(small)


_NAME_SIMILAR_MIN = 0.85


def _name_similar(a, b) -> bool:
    """True if two names are close SPELLING variants — char-level similarity ≥ 0.85
    on the space/dot-stripped strings (`AMLAN PRIYADARSHI` ≈ `AMLAN PRIYADARSHEE`;
    `SANDEEP`/`SANDIP RATHORE`; `NANDANI`/`NANDINI`). Catches variants the token gate
    misses (differing token, not a prefix), while the 0.85 floor still separates
    same-DOB twins, whose given names diverge too far (`SUMIT…`/`MOHIT…` ≈ 0.73)."""
    x = str(a).replace(" ", "").replace(".", "")
    y = str(b).replace(" ", "").replace(".", "")
    if not x or not y:
        return False
    return difflib.SequenceMatcher(None, x, y).ratio() >= _NAME_SIMILAR_MIN


def _despace(s) -> str:
    """UPPER string with spaces and dots removed — for space-insensitive name/father
    comparison ('RAJ KUMAR' → 'RAJKUMAR', 'SAI SWARUP' → 'SAISWARUP'). The board and
    NTA files split/join name tokens inconsistently, so the same person's father (or
    name) differs only by a space."""
    return "".join(ch for ch in str(s) if ch not in " .")


def _father_ok(fa, fb) -> bool:
    """Father-name agreement for the name+father IDENTITY rules. Two format frictions,
    both from the same person written differently across files:
      • surname dropped — board stores first+surname ('KALUBHAI ANJARA'), NTA stores
        first only ('KALUBHAI'); accept when one token set is a SUBSET of the other.
      • space dropped   — 'RAJ KUMAR' vs 'RAJKUMAR'; accept when the space/dot-stripped
        strings are equal.
    Still rejects genuinely different fathers ('SURESH KUMAR' vs 'SURESH SINGH': not a
    subset and not stripped-equal). The STUDENT name is matched separately, so this
    only loosens corroboration."""
    if not fa or not fb:
        return False
    if _despace(fa) == _despace(fb):
        return True
    ta, tb = set(str(fa).split()), set(str(fb).split())
    return bool(ta) and bool(tb) and (ta <= tb or tb <= ta)


_HONORIFICS = {"MR", "MRS", "SHRI", "SMT", "LATE", "DR", "MISS", "SH"}


def _father_related(fa, fb) -> bool:
    """True if two father names are plausibly the SAME person (spelling variant):
    space/dot/concat-equal, or sharing a token where one is a ≥4-char prefix of the
    other (after dropping honorifics). Lenient on purpose — it only decides whether
    two fathers are similar enough NOT to veto a name+DOB merge."""
    a = "".join(ch for ch in str(fa) if ch.isalnum())
    b = "".join(ch for ch in str(fb) if ch.isalnum())
    if a and a == b:
        return True
    ta = [t for t in str(fa).replace(".", " ").split() if t not in _HONORIFICS and len(t) >= 4]
    tb = [t for t in str(fb).replace(".", " ").split() if t not in _HONORIFICS and len(t) >= 4]
    for x in ta:
        for y in tb:
            lo, hi = (x, y) if len(x) <= len(y) else (y, x)
            if hi.startswith(lo):
                return True
    return False


def _father_conflict(fa, fb) -> bool:
    """Veto a name+DOB merge only when BOTH fathers are present and clearly different
    — the signal of a same-name+same-DOB collision between two different people
    ('ANKIT YADAV' with fathers 'JAGDEESH SINGH' vs 'SANGAM LAL YADAV'). A missing
    father never blocks (keeps recall); DOB stays the primary corroborator."""
    if pd.isna(fa) or pd.isna(fb):
        return False
    fa, fb = str(fa), str(fb)
    if not fa or not fb:
        return False
    return not _father_related(fa, fb)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — read every source record as a node
# ─────────────────────────────────────────────────────────────────────────────
# Each node frame carries: node_id, stage, yr (Int64), yr_s (str), norm_name,
# dob, norm_father, plus the stage's natural key(s). Names/DOB are normalised in
# SQL (upper, space-collapsed, DOB → 'YYYY-MM-DD') so pandas only does assembly.
_NAME = r"UPPER(TRIM(REGEXP_REPLACE({c}, r'\s+', ' ')))"
_NN  = lambda c: _NAME.format(c=c)
_NNC = lambda c: _NAME.format(c=f"COALESCE({c},'')")
# dob arrives in several shapes across the JEE/NEET files: 'DD-MM-YYYY', 'YYYY-MM-DD',
# 'DDMMYYYY', and — for ~40% of rows — a 'YYYY-MM-DD HH:MM:SS' timestamp string. The
# last SUBSTR branch grabs the leading date of that timestamp (also a no-op for a plain
# 'YYYY-MM-DD'); without it those ~40% silently dropped out of name+DOB matching.
_DOB = ("COALESCE(SAFE.PARSE_DATE('%d-%m-%Y', dob),"
        " SAFE.PARSE_DATE('%Y-%m-%d', dob),"
        " SAFE.PARSE_DATE('%d%m%Y', dob),"
        " SAFE.PARSE_DATE('%Y-%m-%d', SUBSTR(dob, 1, 10)))")


def _finish_nodes(df: pd.DataFrame, stage: str, id_parts: list[str]) -> pd.DataFrame:
    """Common post-processing: stringify, blank→NA on identity cols, build node_id."""
    for c in df.columns:
        df[c] = _S(df[c])
    for c in ("dob", "norm_father", "norm_mother", "norm_name", "fk_avanti_id"):
        if c in df:
            df[c] = _blank_to_na(df[c])
    df["stage"] = stage
    df["yr"] = pd.to_numeric(df["yr_s"], errors="coerce").astype("Int64")
    df["node_id"] = stage + ":" + df[id_parts].agg(":".join, axis=1)
    return df


def _read_nodes(client) -> dict:
    """Pull the five stage node frames from BigQuery."""
    ext = "avantifellows.external_data_sources"
    queries = {
        "b12": f"""
            SELECT CAST(exam_year AS STRING) AS yr_s, roll_number AS roll,
                ANY_VALUE({_NN('student_name')}) AS norm_name,
                ANY_VALUE({_NNC('father_name')}) AS norm_father,
                ANY_VALUE({_NNC('mother_name')}) AS norm_mother,
                FORMAT_DATE('%Y-%m-%d',
                    ANY_VALUE(SAFE.PARSE_DATE('%d%m%Y', LPAD(date_of_birth, 8, '0')))) AS dob,
                ANY_VALUE(roll_number_10th)      AS roll_number_10th,
                ANY_VALUE(fk_avanti_student_id)  AS fk_avanti_id
            FROM `{ext}.jnv_fact_board_results_12th`
            WHERE roll_number IS NOT NULL AND student_name IS NOT NULL
            GROUP BY 1, 2""",
        "b10": f"""
            SELECT CAST(exam_year AS STRING) AS yr_s, roll_number AS roll,
                ANY_VALUE({_NN('student_name')}) AS norm_name,
                FORMAT_DATE('%Y-%m-%d',
                    ANY_VALUE(SAFE.PARSE_DATE('%d%m%Y', LPAD(date_of_birth, 8, '0')))) AS dob,
                ANY_VALUE({_NNC('father_name')}) AS norm_father,
                ANY_VALUE({_NNC('mother_name')}) AS norm_mother,
                ANY_VALUE(fk_avanti_student_id)  AS fk_avanti_id
            FROM `{ext}.jnv_fact_board_results_10th`
            WHERE roll_number IS NOT NULL AND student_name IS NOT NULL
            GROUP BY 1, 2""",
        "jee": f"""
            SELECT CAST(test_year AS STRING) AS yr_s, application_no AS app,
                ANY_VALUE({_NNC('student_full_name')}) AS norm_name,
                FORMAT_DATE('%Y-%m-%d', ANY_VALUE({_DOB})) AS dob,
                ANY_VALUE({_NNC('father_name')}) AS norm_father,
                ANY_VALUE({_NNC('mother_name')}) AS norm_mother,
                ANY_VALUE(fk_avanti_student_id)  AS fk_avanti_id
            FROM `{ext}.jnv_fact_jee_results`
            WHERE application_no IS NOT NULL
            GROUP BY 1, 2""",
        "neet": f"""
            SELECT CAST(test_year AS STRING) AS yr_s, application_no AS app,
                ANY_VALUE({_NNC('student_full_name')}) AS norm_name,
                FORMAT_DATE('%Y-%m-%d', ANY_VALUE({_DOB})) AS dob,
                ANY_VALUE({_NNC('father_name')}) AS norm_father,
                ANY_VALUE({_NNC('mother_name')}) AS norm_mother,
                ANY_VALUE(fk_avanti_student_id)  AS fk_avanti_id
            FROM `{ext}.jnv_fact_neet_results`
            WHERE application_no IS NOT NULL
            GROUP BY 1, 2""",
        "ncst": f"""
            SELECT 'dakshana' AS ncst_source, CAST(test_year AS STRING) AS yr_s,
                roll_no AS roll, {_NNC('student_full_name')} AS norm_name,
                {_NNC('father_name')} AS norm_father, {_NNC('mother_name')} AS norm_mother,
                FORMAT_DATE('%Y-%m-%d', SAFE.PARSE_DATE('%Y-%m-%d', SUBSTR(dob, 1, 10))) AS dob,
                fk_avanti_student_id AS fk_avanti_id
            FROM `{ext}.dakshana_fact_ncst_results` WHERE roll_no IS NOT NULL
            UNION ALL
            SELECT 'nvs', CAST(test_year AS STRING), roll_no,
                {_NNC('student_full_name')}, {_NNC('father_name')}, {_NNC('mother_name')},
                FORMAT_DATE('%Y-%m-%d', SAFE.PARSE_DATE('%Y-%m-%d', SUBSTR(dob, 1, 10))),
                fk_avanti_student_id
            FROM `{ext}.nvs_fact_ncst_results` WHERE roll_no IS NOT NULL""",
    }
    id_parts = {"b12": ["yr_s", "roll"], "b10": ["yr_s", "roll"],
                "jee": ["yr_s", "app"], "neet": ["yr_s", "app"],
                "ncst": ["ncst_source", "yr_s", "roll"]}
    nodes = {}
    for stage, sql in queries.items():
        df = _finish_nodes(client.query(sql).to_dataframe(), stage, id_parts[stage])
        nodes[stage] = df
        print(f"  nodes {stage:<4} {len(df):>8,}")
    return nodes


def _read_crosswalks() -> dict:
    """Local Excel crosswalks used to draw DETERMINISTIC edges (roll ↔ app ↔ id)."""
    p24 = pd.read_excel(POOJITA, sheet_name="Mapped Data (2024 Students)", dtype=str).rename(
        columns={"JEE application No": "jee_app", "NEET Application No": "neet_app",
                 "10th Roll No": "roll_10th", "12th Roll No": "roll_12th"})
    p24 = p24[["jee_app", "neet_app", "roll_10th", "roll_12th"]]

    j25 = pd.read_excel(JEE_2025_RAW.local_path, sheet_name=JEE_2025_RAW.sheet,
                        usecols=["JEEApplicationNumber", "avanti_studentid"], dtype=str).rename(
        columns={"JEEApplicationNumber": "app", "avanti_studentid": "avanti_id"})

    j24 = pd.read_excel(JEE_2024_RAW.local_path, sheet_name=JEE_2024_RAW.sheet,
                        usecols=["Application Number", "10th Roll Number", "12th Roll Number", "Student ID"],
                        dtype=str).rename(columns={"Application Number": "app", "10th Roll Number": "roll_10th",
                                                   "12th Roll Number": "roll_12th", "Student ID": "avanti_id"})

    n24 = pd.read_excel(NEET_2024_RAW.local_path, sheet_name=NEET_2024_RAW.sheet,
                        usecols=["Application Number", "10th Roll Number", "12th Roll Number", "Student ID"],
                        dtype=str).rename(columns={"Application Number": "app", "10th Roll Number": "roll_10th",
                                                   "12th Roll Number": "roll_12th", "Student ID": "avanti_id"})

    r10 = pd.read_excel(TENTH_SCORE, sheet_name="Physical Mapping", dtype=str).rename(
        columns={"10th Year": "yr_s", "10th Roll No": "roll", "Avanti Student ID": "avanti_id"})
    r10 = r10[["yr_s", "roll", "avanti_id"]]

    # Poojita "Mapped Data (2025 Students)" — a DIRECT b10-anchored Avanti id crosswalk
    # (10th Roll Number -> Avanti Student ID), used by v1's fk-matcher's b10 direct-id
    # tier (build_student_journey_mapping.py's `p25`). No year column in the sheet, so
    # unlike v1 (which merges on roll alone — a real cross-year collision risk given
    # this session's findings) we resolve it across ALL board years + a name-agreement
    # gate in _build_sid, same as every other roll bridge in this file.
    p25b10 = pd.read_excel(POOJITA, sheet_name="Mapped Data (2025 Students)", dtype=str).rename(
        columns={"Avanti Student ID": "avanti_id", "Student Name": "name", "10th Roll Number": "roll"})
    p25b10 = p25b10[["avanti_id", "name", "roll"]]

    refs = {"p24": p24, "jee25": j25, "jee24": j24, "neet24": n24, "roll10x": r10, "p25b10": p25b10}
    for name, df in refs.items():
        for c in df.columns:
            df[c] = _S(df[c]).replace("nan", pd.NA)
        print(f"  crosswalk {name:<8} {len(df):>7,}")

    # roll10x: keep only (yr, roll) pairs that map to exactly one Avanti id — a roll
    # is unique only WITHIN a year, and the sheet has known row-alignment errors, so
    # an ambiguous pair must not multiply into false links. (See jnv_10th_score memory.)
    rx = refs["roll10x"].dropna(subset=["yr_s", "roll", "avanti_id"])
    one = rx.groupby(["yr_s", "roll"])["avanti_id"].transform("nunique") == 1
    refs["roll10x"] = rx[one].drop_duplicates(["yr_s", "roll"]).reset_index(drop=True)
    print(f"  crosswalk roll10x → {len(refs['roll10x']):>7,} unambiguous (yr, roll)→id")
    return refs


def _read_ncst_avanti_id() -> pd.DataFrame:
    """NCST-2024 raw carries a direct Avanti ID keyed on Dakshana Roll Number.
    Returns (yr_s='2024', roll, avanti_id); empty if the raw file is absent."""
    for path in NCST_2024_RAW_CANDIDATES:
        if not path.exists():
            continue
        d = pd.read_excel(path, sheet_name=NCST_2024_RAW_SHEET, dtype=str)
        out = pd.DataFrame({"yr_s": "2024", "roll": _S(d["Dakshana Roll Number"]),
                            "avanti_id": _S(d["Avanti ID"])})
        out = out[_present(out.avanti_id) & _present(out.roll)]
        print(f"  crosswalk ncst24   {len(out):>7,}  ({path.name})")
        return out
    print("  crosswalk ncst24         0  (raw not found — skipped)")
    return pd.DataFrame(columns=["yr_s", "roll", "avanti_id"])


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — edges
# ─────────────────────────────────────────────────────────────────────────────
# Identity edges are declared here so every journey-year assumption is visible in
# one place. gap = right_stage.yr − left_stage.yr must fall in [gap_lo, gap_hi]:
#   b10→b12  +2      (10th board is exactly two years before 12th)
#   b12→JEE  0..2    (sit JEE the year of / up to 2 years after 12th — droppers)
#   b10→JEE  2..4    (= b10→b12 +2 then b12→JEE 0..2)
#   NCST→b10  0      (NCST is sat the same year as 10th board)
#   NCST→b12 +2      NCST→JEE/NEET 2..4
# Each rule links only on the given keys, only where BOTH sides have them, only
# when the match is unambiguous at component level (see _identity_edges).
IDENTITY_RULES = [
    # (left, right, keys,                         gap_lo, gap_hi)
    ("b10",  "b12",  ["norm_name", "norm_father"],   2, 2),
    ("b12",  "jee",  ["norm_name", "norm_father"],   0, 2),
    ("b12",  "neet", ["norm_name", "norm_father"],   0, 2),
    ("b10",  "jee",  ["norm_name", "dob"],           2, 4),
    ("b10",  "neet", ["norm_name", "dob"],           2, 4),
    ("b10",  "jee",  ["norm_name", "norm_father"],   2, 4),
    ("b10",  "neet", ["norm_name", "norm_father"],   2, 4),
    ("ncst", "b10",  ["norm_name", "dob"],           0, 0),
    ("ncst", "b10",  ["norm_name", "norm_father"],   0, 0),
    ("ncst", "b12",  ["norm_name", "norm_father"],   2, 2),
    ("ncst", "jee",  ["norm_name", "dob"],           2, 4),
    ("ncst", "neet", ["norm_name", "dob"],           2, 4),
    ("ncst", "jee",  ["norm_name", "norm_father"],   2, 4),
    ("ncst", "neet", ["norm_name", "norm_father"],   2, 4),
]

# Entrance records of the SAME person merge across exams/years on an exact
# identity key (this is what recognises a dropper's two JEE sittings, and a
# JEE+NEET dual-taker, as one student). Strongest key first.
ENTRANCE_KEYS = [["norm_name", "dob", "norm_father"], ["norm_name", "dob"]]


def _star_edges(node_id_cols: pd.DataFrame, name: dict) -> list[tuple]:
    """Given a frame whose columns each hold a node_id (or NA), connect the
    present node_ids in each row — but only PAIRS whose names agree (see
    _name_agree). Gating pairwise (not to a fixed anchor) means a single
    misaligned crosswalk column is simply excluded while the rest still link."""
    edges = []
    for row in node_id_cols.itertuples(index=False, name=None):
        ids = [x for x in row if isinstance(x, str) and x]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if _name_agree(name.get(ids[i]), name.get(ids[j])):
                    edges.append((ids[i], ids[j]))
    return edges


def _resolve_node(cross: pd.DataFrame, key_map: dict, node: pd.DataFrame,
                  node_keys: list[str], fixed: dict = None) -> pd.Series:
    """Map a crosswalk column to a node_id via the node's natural key, keeping
    only UNAMBIGUOUS matches (a crosswalk value hitting >1 node → NA). `key_map`
    maps node_key → crosswalk column; `fixed` pins node columns to a constant."""
    n = node.copy()
    left_on, right_on = [], []
    for nk in node_keys:
        if fixed and nk in fixed:
            n = n[n[nk] == fixed[nk]]
        else:
            left_on.append(key_map[nk]); right_on.append(nk)
    keep = n[right_on + ["node_id"]].dropna()
    uniq = keep.groupby(right_on)["node_id"].transform("nunique")
    keep = keep[uniq == 1].drop_duplicates(right_on)
    merged = cross.merge(keep, left_on=left_on, right_on=right_on, how="left")
    return merged["node_id"].where(_present(merged["node_id"])).values


def _roll_cols(cross: pd.DataFrame, roll_key: str, node: pd.DataFrame, prefix: str) -> dict:
    """Resolve a crosswalk 10th/12th-roll column to board node_ids in EVERY board
    year, returning one star-column per year ({f'{prefix}_{yr}': node_id array}).

    A roll is unique only WITHIN a year (the same roll recurs for different people
    across years), so we cannot search all years at once — instead we resolve each
    year on its own (each safe) and feed every candidate to _star_edges, whose name
    gate keeps only the year whose board name agrees with the entrance record. This
    is what lets a dropper's earlier-year 12th roll link to their entrance sitting;
    the old 2024-only lookup silently missed ~1,600 such droppers."""
    return {f"{prefix}_{yr}": _resolve_node(cross, {"roll": roll_key}, node,
                                            ["yr_s", "roll"], fixed={"yr_s": yr})
            for yr in BOARD_YEARS}


def _deterministic_edges(nodes: dict, refs: dict, ncst24: pd.DataFrame) -> list[tuple]:
    """Roll/app/id crosswalk edges — name-gated (see _name_agree): the key ties
    records, but the edge is kept only if the two records' names also agree, so a
    misaligned crosswalk row can't fuse two different people."""
    b10, b12, jee, neet, ncst = (nodes[s] for s in ("b10", "b12", "jee", "neet", "ncst"))
    name = {nid: (str(nm) if pd.notna(nm) else None)
            for df in nodes.values() for nid, nm in zip(df.node_id, df.norm_name)}
    edges = []

    # (a) 12th's own roll_number_10th → 10th board, two years earlier.
    link = b12[_present(b12.roll_number_10th)][["node_id", "yr", "roll_number_10th"]].copy()
    link["yr10"] = (link.yr - 2).astype("string")
    b10k = b10[["yr_s", "roll", "node_id"]].rename(columns={"node_id": "b10_node"})
    uniq = b10k.groupby(["yr_s", "roll"])["b10_node"].transform("nunique")
    b10k = b10k[uniq == 1]
    m = link.merge(b10k, left_on=["yr10", "roll_number_10th"], right_on=["yr_s", "roll"])
    edges += [(a, b) for a, b in zip(m.node_id, m.b10_node)
              if _name_agree(name.get(a), name.get(b))]

    # (b) Poojita-2024: one row names a student's 10th/12th roll + JEE/NEET app.
    #     Roll columns are resolved across ALL board years (name gate picks the one).
    p24 = refs["p24"]
    star = pd.DataFrame({
        "jee": _resolve_node(p24, {"app": "jee_app"},   jee,  ["app"]),
        "neet": _resolve_node(p24, {"app": "neet_app"}, neet, ["app"]),
        **_roll_cols(p24, "roll_12th", b12, "b12"),
        **_roll_cols(p24, "roll_10th", b10, "b10"),
    })
    edges += _star_edges(star, name)

    # (c) JEE-2024 / NEET-2024 files: app → 10th roll + 12th roll. Both rolls are
    #     resolved across ALL board years (not just the on-time 2024/2022), so a
    #     dropper's earlier-year board record links too; the name gate in
    #     _star_edges keeps only the year whose board name agrees.
    for ref, ent, appkey in (("jee24", jee, "jee"), ("neet24", neet, "neet")):
        x = refs[ref]
        star = pd.DataFrame({
            appkey: _resolve_node(x, {"app": "app"}, ent, ["app"]),
            **_roll_cols(x, "roll_12th", b12, "b12"),
            **_roll_cols(x, "roll_10th", b10, "b10"),
        })
        edges += _star_edges(star, name)

    # (d) shared Avanti/Student id → same person. Tag nodes with an id from the
    #     crosswalks, then connect nodes that share one (guarded like identity:
    #     an id landing on 2+ nodes in the SAME stage-year is a bad/placeholder id).
    tag = []
    jee_ids = pd.concat([refs["jee25"], refs["jee24"][["app", "avanti_id"]]], ignore_index=True)
    jt = jee.merge(jee_ids.dropna(), left_on="app", right_on="app", how="inner")
    tag.append(jt[["node_id", "stage", "yr", "avanti_id"]])
    nt = neet.merge(refs["neet24"][["app", "avanti_id"]].dropna(), on="app", how="inner")
    tag.append(nt[["node_id", "stage", "yr", "avanti_id"]])
    bt = b10.merge(refs["roll10x"].dropna(), left_on=["yr_s", "roll"], right_on=["yr_s", "roll"], how="inner")
    tag.append(bt[["node_id", "stage", "yr", "avanti_id"]])
    ct = ncst.merge(ncst24, left_on=["yr_s", "roll"], right_on=["yr_s", "roll"], how="inner")
    tag.append(ct[["node_id", "stage", "yr", "avanti_id"]])
    idtag = pd.concat(tag, ignore_index=True)
    idtag = idtag[_present(idtag.avanti_id)]
    edges += _key_group_edges(idtag, "avanti_id", name)

    return edges


def _key_group_edges(frame: pd.DataFrame, key: str, name: dict = None,
                     father_veto: bool = False) -> list[tuple]:
    """Connect all nodes sharing `key`, dropping a key value that is ambiguous
    within one stage-year (≥2 nodes in the same (stage, yr) → likely a collision
    or placeholder). If `name` is given (crosswalk id bridge), connect only PAIRS
    whose names agree. If `father_veto` (entrance name+DOB), drop a pair whose
    fathers clearly conflict. With neither, emit a star per key value."""
    f = frame.dropna(subset=[key]).drop_duplicates(["node_id", key])
    dup = f.groupby([key, "stage", "yr"])["node_id"].transform("size")
    bad_keys = set(f.loc[dup > 1, key])
    good = f[(dup == 1) & (~f[key].isin(bad_keys))]
    edges = []
    for _, grp in good.groupby(key):
        ids = grp.node_id.tolist()
        if name is None and not father_veto:
            edges.extend((ids[0], other) for other in ids[1:])
            continue
        fas = grp.norm_father.tolist() if father_veto else None
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if name is not None and not _name_agree(name.get(ids[i]), name.get(ids[j])):
                    continue
                if father_veto and _father_conflict(fas[i], fas[j]):
                    continue
                edges.append((ids[i], ids[j]))
    return edges


def _identity_edges(nodes: dict, comp: dict) -> list[tuple]:
    """Draw the IDENTITY_RULES edges. Unambiguity is checked at the CURRENT
    component level (comp) so a dropper matching several already-merged entrance
    records still links, while a name+DOB that hits two DIFFERENT students does
    not. Precision-first: any ambiguous match is dropped, not guessed."""
    edges = []
    for left, right, keys, lo, hi in IDENTITY_RULES:
        # Father handling depends on the rule:
        #   • name+father rule  → father is a KEY: first-token block + _father_ok subset
        #     corroboration ('KALUBHAI' matches 'KALUBHAI ANJARA').
        #   • name+DOB rule     → father is a VETO: drop a pair whose fathers clearly
        #     conflict (blocks same-name+DOB collisions between different people).
        # Either way norm_father is carried alongside; all non-father keys stay exact.
        father_key = "norm_father" in keys
        exact_keys = [k for k in keys if k != "norm_father"]
        L, R = nodes[left], nodes[right]
        cols = ["node_id", "yr"] + exact_keys + ["norm_father"]
        lsub = L.dropna(subset=exact_keys + ["yr"])[cols].copy()
        rsub = R.dropna(subset=exact_keys + ["yr"])[cols].copy()
        for k in exact_keys:
            lsub = lsub[lsub[k].str.len() > 0]
            rsub = rsub[rsub[k].str.len() > 0]
        # Space-insensitive name join: match on the space/dot-stripped name so
        # 'SAI SWARUP RATH' == 'SAISWARUP RATH' (the board vs NTA files split name
        # tokens inconsistently). Other exact keys (dob) stay verbatim.
        merge_on = []
        for k in exact_keys:
            if k == "norm_name":
                lsub["nk"] = lsub.norm_name.map(_despace)
                rsub["nk"] = rsub.norm_name.map(_despace)
                merge_on.append("nk")
            else:
                merge_on.append(k)
        if father_key:
            lsub = lsub[_present(lsub.norm_father)]
            rsub = rsub[_present(rsub.norm_father)]
            # Block on the space/dot-stripped father PREFIX so 'RAJ KUMAR' and
            # 'RAJKUMAR' (and 'KALUBHAI'/'KALUBHAI ANJARA') land in the same block;
            # _father_ok then confirms (stripped-equal or token-subset).
            lsub["ff"] = lsub.norm_father.map(lambda s: _despace(s)[:4])
            rsub["ff"] = rsub.norm_father.map(lambda s: _despace(s)[:4])
            merge_on = merge_on + ["ff"]
        m = lsub.merge(rsub, on=merge_on, suffixes=("_l", "_r"))
        gap = m.yr_r - m.yr_l
        m = m[(gap >= lo) & (gap <= hi)]
        if father_key:
            m = m[[_father_ok(a, b) for a, b in zip(m.norm_father_l, m.norm_father_r)]]
        else:
            m = m[[not _father_conflict(a, b) for a, b in zip(m.norm_father_l, m.norm_father_r)]]
        m = m.drop_duplicates(["node_id_l", "node_id_r"])
        if m.empty:
            continue
        m["comp_l"] = m.node_id_l.map(comp)
        m["comp_r"] = m.node_id_r.map(comp)
        m = m[m.comp_l != m.comp_r]
        # unambiguous at component granularity, both directions
        lc = m.groupby("comp_l")["comp_r"].transform("nunique")
        rc = m.groupby("comp_r")["comp_l"].transform("nunique")
        m = m[(lc == 1) & (rc == 1)]
        edges += list(zip(m.node_id_l, m.node_id_r))
    return edges


def _entrance_edges(nodes: dict) -> list[tuple]:
    """Merge a person's entrance records (JEE/NEET, any year) on an exact identity
    key — the dropper / dual-exam signal."""
    ent = pd.concat([nodes["jee"], nodes["neet"]], ignore_index=True)
    edges = []
    for keys in ENTRANCE_KEYS:
        sub = ent.dropna(subset=keys)[["node_id", "stage", "yr", "norm_father"]
                                       + [k for k in keys if k != "norm_father"]].copy()
        for k in keys:
            sub = sub[sub[k].str.len() > 0]
        # Space-insensitive dedup key: despace each component so one person's two
        # entrance records merge despite a spacing variant in the name/father
        # ('SAI SWARUP' == 'SAISWARUP'); dob (no spaces/dots) is unchanged.
        sub["_k"] = sub[keys].apply(lambda r: "".join(_despace(v) for v in r), axis=1)
        # name+DOB tier (no father in key) → veto pairs whose fathers clearly conflict
        edges += _key_group_edges(sub.rename(columns={"_k": "key"}), "key",
                                  father_veto=("norm_father" not in keys))
    return edges


# Parent first-name placeholders that must NOT anchor a merge block.
_PARENT_STOP = {"NA", "N/A", "NULL", "NONE", "FATHER", "MOTHER", "NAME", "XXX", "XX", "ABC", "TEST"}
_PARENT_DOB_BLOCK_MAX = 12   # (dob, father, mother) block bigger than this => placeholder, skip


def _parent_dob_edges(nodes: dict) -> list[tuple]:
    """MOTHER-augmented, DOB-anchored same-person edges across ALL stages — the two
    merge levers the standalone v2 mining surfaced. Block on
    `(dob, father_first_token, mother_first_token)` (records that share an exact
    birthdate AND both parents' first names), then connect a pair when the names are:
      • token-subset compatible          -> Rule A (dropped/reordered/added tokens),
      • OR close spelling variants (>=.85) -> Rule C (`AMLAN PRIYADARSHI` ~ `…DARSHEE`).

    DOB + both parents is what makes this TWIN-SAFE: identical-DOB siblings carry
    different given names, so neither _name_subset nor _name_similar links them (they
    fall out, exactly as the mining's excluded 'twin' cluster showed). This adds the
    mother signal (unused elsewhere) and a spelling-variant path the token gate can't
    reach — without the recall-killing 1:1 guard, because the block key is already
    highly specific. Skips placeholder parent tokens and oversized (garbage) blocks."""
    cols = ["node_id", "norm_name", "norm_father", "norm_mother", "dob"]
    alln = pd.concat([nodes[s][cols] for s in STAGES], ignore_index=True)
    sub = alln[_present(alln.dob) & _present(alln.norm_name)
               & _present(alln.norm_father) & _present(alln.norm_mother)].copy()
    sub["ff"] = sub.norm_father.str.split().str[0]
    sub["mf"] = sub.norm_mother.str.split().str[0]
    sub = sub[(sub.ff.str.len() >= 3) & (sub.mf.str.len() >= 3)
              & ~sub.ff.isin(_PARENT_STOP) & ~sub.mf.isin(_PARENT_STOP)]
    edges = []
    for _, grp in sub.groupby(["dob", "ff", "mf"], sort=False):
        recs = list(zip(grp.node_id, grp.norm_name))
        if len(recs) < 2 or len(recs) > _PARENT_DOB_BLOCK_MAX:
            continue
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                na, nb = recs[i][1], recs[j][1]
                if _name_subset(na, nb) or _name_similar(na, nb):
                    edges.append((recs[i][0], recs[j][0]))
    return edges


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — union-find → clusters → student_key
# ─────────────────────────────────────────────────────────────────────────────
class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:      # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)   # keep the smaller id as root


def _cluster(nodes: dict, refs: dict, ncst24: pd.DataFrame) -> pd.DataFrame:
    """Run the two-round union-find and return node_id → student_key."""
    all_nodes = pd.concat([nodes[s][["node_id"]] for s in STAGES], ignore_index=True)
    uf = _UnionFind(all_nodes.node_id.tolist())

    # Round 0 — hard edges (deterministic + entrance same-person + DOB/parent).
    hard = (_deterministic_edges(nodes, refs, ncst24) + _entrance_edges(nodes)
            + _parent_dob_edges(nodes))
    hard = [(a, b) for a, b in hard if a in uf.parent and b in uf.parent]
    for a, b in hard:
        uf.union(a, b)
    print(f"  round-0 hard edges:     {len(hard):>8,}")

    # Round 1 — identity edges, ambiguity judged against round-0 components.
    comp = {n: uf.find(n) for n in uf.parent}
    soft = _identity_edges(nodes, comp)
    soft = [(a, b) for a, b in soft if a in uf.parent and b in uf.parent]
    for a, b in soft:
        uf.union(a, b)
    print(f"  round-1 identity edges: {len(soft):>8,}")

    key = pd.DataFrame({"node_id": list(uf.parent)})
    key["student_key"] = key.node_id.map(uf.find)   # root = min node_id in component
    print(f"  {len(key):,} nodes → {key.student_key.nunique():,} students")
    return key


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6 — attach the Avanti fk
# ─────────────────────────────────────────────────────────────────────────────
def _avanti_fk_passthrough(nodes: dict, n2k: pd.Series) -> pd.DataFrame:
    """DIAGNOSTIC ONLY — not called by the main build. Each of the 5 source tables
    carries a row-level fk_avanti_student_id written by add_avanti_fk.py FROM v1
    (jnv_student_outcome_mapping) — take it as given per row, reconciled to ONE
    value per student (ambiguous = >1 distinct non-null fk in the cluster, dropped
    rather than guessed). This was v2's original step-6: it depends on v1 having
    already run, which _match_fk_v2 below removes. Kept here so a comparison
    script can still measure agreement between the two mechanisms."""
    fk = pd.concat([nodes[s][["node_id", "fk_avanti_id"]] for s in STAGES], ignore_index=True)
    fk = fk[_present(fk.fk_avanti_id)].copy()
    fk["student_key"] = fk.node_id.map(n2k)
    fk = fk.dropna(subset=["student_key"])
    n_distinct = fk.groupby("student_key")["fk_avanti_id"].nunique()
    unambiguous = n_distinct[n_distinct == 1].index
    out = (fk[fk.student_key.isin(unambiguous)]
           .drop_duplicates("student_key")[["student_key", "fk_avanti_id"]]
           .rename(columns={"fk_avanti_id": "fk_avanti_student_id"}))
    return out


def _read_avanti_reference(client) -> tuple:
    """The JNV Avanti population (+ DOB-swapped variant + father) used as the
    match target, plus the full pk/apaar id universe (for direct-id validation —
    a crosswalk-supplied id can sit under a non-JNV dim_student label).

    Ported from v1's _read_avanti. Returns grade-12-only AND all-grade frames.
    all-grade is needed because NCST is sat at grade 9-11 (folded into the SAME
    sid / _match_fk_v2 pipeline, not a separate resolver like v1's _resolve_ncst)
    — a grade-12-only frame would miss nearly all of it. BUT widening the
    reference for the existing b10/b12/jee/neet population turned out NOT safe:
    verified against rebuild9 that ~15k JNV (name, dob) pairs resolve to TWO
    DIFFERENT pk_student_id — 69% of those are the SAME real student re-enrolled
    from Foundation (grade 9-10) into TP (grade 11-12) under a NEW id (mostly
    both rows live in dim_student itself, not a dim_student_historical
    artifact), which the cnt==1 ambiguity guard in _match_fk_v2 then correctly
    refuses to pick between — net loss for that population (resolved -1,275,
    ambiguous +11,128 in that rebuild). So: avanti_g12 stays the match target
    for everyone EXCEPT students whose only source is NCST (see sid.ncst_only
    in _build_sid) — those alone get avanti_all, since a grade-12 frame gives
    them nothing to match at all."""
    name = r"UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\s+', ' ')))"
    fname = r"UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\s+', ' ')))"
    swap = ("SAFE.DATE(EXTRACT(YEAR FROM date_of_birth),"
            " EXTRACT(DAY FROM date_of_birth), EXTRACT(MONTH FROM date_of_birth))")
    years = "'2020-2021','2021-2022','2022-2023','2023-2024','2024-2025','2025-2026','2026-2027'"
    filt = (f"(LOWER(COALESCE(student_school,'')) LIKE '%jnv%'"
            f" OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')"
            f" AND academic_year IN ({years})"
            f" AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL")
    sql = f"""
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk_student_id,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS dob,
            {name} AS norm_name, {fname} AS norm_father,
            FORMAT_DATE('%Y-%m-%d', {swap}) AS dob_swapped,
            CAST(student_grade AS STRING) AS student_grade
        FROM `avantifellows.production_dbt_final.dim_student`  WHERE {filt}
        UNION ALL
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk_student_id,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS dob,
            {name} AS norm_name, {fname} AS norm_father,
            FORMAT_DATE('%Y-%m-%d', {swap}) AS dob_swapped,
            CAST(student_grade AS STRING) AS student_grade
        FROM `avantifellows.production_dbt_final.dim_student_historical` WHERE {filt}
    """
    avanti = client.query(sql).to_dataframe().drop_duplicates()
    avanti["norm_father"] = avanti["norm_father"].where(_present(avanti["norm_father"]))
    for c in avanti.columns:
        avanti[c] = _S(avanti[c])

    avanti_all = avanti.drop(columns=["student_grade"])
    avanti_g12 = (avanti[avanti.student_grade == "12"]
                  .drop(columns=["student_grade"]).drop_duplicates())

    all_ids = {r.id for r in client.query(
        "SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS id "
        "FROM `avantifellows.production_dbt_final.dim_student` "
        "WHERE COALESCE(pk_student_id, apaar_id) IS NOT NULL "
        "UNION DISTINCT "
        "SELECT DISTINCT COALESCE(pk_student_id, apaar_id) "
        "FROM `avantifellows.production_dbt_final.dim_student_historical` "
        "WHERE COALESCE(pk_student_id, apaar_id) IS NOT NULL"
    ).result()}
    print(f"  avanti reference: {len(avanti_g12):,} grade-12 JNV rows, "
          f"{len(avanti_all):,} all-grade JNV rows "
          f"({avanti_all.norm_father.notna().sum():,} with father), {len(all_ids):,} total pk/apaar ids")
    return avanti_g12, avanti_all, all_ids


_COALESCE_NAME_ORDER = ["b12", "b10", "jee", "neet", "ncst"]
_COALESCE_DOB_ORDER = ["b10", "jee", "neet", "ncst"]   # 12th board carries no usable DOB (verified empty)
_COALESCE_FATHER_ORDER = ["b12", "b10", "jee", "neet", "ncst"]


def _coalesce_by_source(contrib: pd.DataFrame, col: str, order: list) -> pd.Series:
    """Per student_key, take `col` from the first source in `order` that has a
    present value. Ported from v1's identically-named helper (secondary sort on
    node_id added for determinism when a student has >1 node in the same stage)."""
    rank = {s: i for i, s in enumerate(order)}
    d = contrib[contrib.src.isin(order) & _present(contrib[col])].copy()
    d["r"] = d.src.map(rank)
    d = d.sort_values(["student_key", "r", "node_id"]).drop_duplicates("student_key", keep="first")
    return d.set_index("student_key")[col]


def _build_sid(nodes: dict, n2k: pd.Series, refs: dict, ncst24: pd.DataFrame) -> pd.DataFrame:
    """Per-student name/DOB/father/direct-avanti-id frame for the STEP-6 matcher —
    coalesced across the student's own linked records at the SAME source priority
    v1 used (name b12>b10>jee>neet, dob b10>jee>neet), PLUS ncst as the lowest-
    priority fallback in both. NCST is folded into this SAME frame/pipeline
    (rather than v1's separate _resolve_ncst) because v2's union-find already
    handles the identity-attach half (IDENTITY_RULES links ncst->b10/b12/jee/neet
    by name+dob / name+father before this function ever runs) — the only gap is
    that an NCST-ONLY student (no board/entrance record in their cluster) never
    contributed a row here at all, so never got a chance to match. Adding "ncst"
    to the coalesce fixes that with no separate code path. Direct ids reuse the
    SAME crosswalks (jee25/jee24/neet24/roll10x/ncst24) v2 already loads."""
    def assign(stage):
        df = nodes[stage][["node_id", "norm_name", "norm_father", "dob"]].copy()
        df["student_key"] = df.node_id.map(n2k)
        df["src"] = stage
        return df.dropna(subset=["student_key"])

    contrib = pd.concat([assign(s) for s in ("b12", "b10", "jee", "neet", "ncst")], ignore_index=True)
    keys = pd.Index(contrib.student_key.unique(), name="student_key")
    sid = pd.DataFrame(index=keys)
    sid["norm_name"] = _coalesce_by_source(contrib, "norm_name", _COALESCE_NAME_ORDER)
    sid["dob"] = _coalesce_by_source(contrib, "dob", _COALESCE_DOB_ORDER)
    sid["norm_father"] = _coalesce_by_source(contrib, "norm_father", _COALESCE_FATHER_ORDER)
    sid = sid.reset_index()

    # direct avanti id — jee (jee25+jee24) then neet (neet24) then b10 then ncst;
    # same tier-1 source priority v1 used (["jee","neet","b10"]), ncst appended
    # last since it only ever fires for NCST-only students (jee/neet/b10, when
    # present, are always resolved first by this same priority order).
    jee_ids = pd.concat([refs["jee25"], refs["jee24"][["app", "avanti_id"]]], ignore_index=True).dropna()
    jtag = nodes["jee"].merge(jee_ids, on="app", how="inner")[["node_id", "avanti_id"]].copy()
    jtag["student_key"], jtag["src"] = jtag.node_id.map(n2k), "jee"
    ntag = nodes["neet"].merge(refs["neet24"][["app", "avanti_id"]].dropna(), on="app", how="inner")[["node_id", "avanti_id"]].copy()
    ntag["student_key"], ntag["src"] = ntag.node_id.map(n2k), "neet"

    # b10-anchored direct id (Poojita 2025-students sheet, roll -> avanti_id). The
    # sheet carries no year, and a roll repeats across years, so — unlike v1, which
    # merges on roll alone — resolve against ALL board years and require the
    # sheet's OWN name to AGREE with the matched board record (same roll-collision
    # guard as _roll_cols/#6, #9 elsewhere in this file).
    p25 = refs["p25b10"].dropna(subset=["roll", "avanti_id"])
    p25hit = p25.merge(nodes["b10"][["node_id", "roll", "norm_name"]], on="roll", how="inner")
    p25hit = p25hit[[_name_agree(a, b) for a, b in zip(p25hit.name, p25hit.norm_name)]]
    btag = p25hit[["node_id", "avanti_id"]].drop_duplicates().copy()
    btag["student_key"], btag["src"] = btag.node_id.map(n2k), "b10"

    # NCST-2024 direct id (Dakshana raw's own "Avanti ID" column, already read as
    # ncst24 for the identity-clustering edges) — same (yr_s, roll) join, no extra
    # name-gate needed: ncst24 is already 1:1 on (yr_s, roll) by construction.
    ncst_ids = ncst24.rename(columns={"avanti_id": "avanti_id_ncst"})
    ctag = (nodes["ncst"].merge(ncst_ids, on=["yr_s", "roll"], how="inner")
            [["node_id", "avanti_id_ncst"]].rename(columns={"avanti_id_ncst": "avanti_id"}))
    ctag["student_key"], ctag["src"] = ctag.node_id.map(n2k), "ncst"

    idtag = pd.concat([jtag, ntag, btag, ctag], ignore_index=True).dropna(subset=["student_key"])
    idtag = idtag[_present(idtag.avanti_id)]
    direct = _coalesce_by_source(idtag, "avanti_id", ["jee", "neet", "b10", "ncst"]).rename("source_avanti_student_id")
    sid = sid.merge(direct, on="student_key", how="left")

    # 10th-score crosswalk id — FILL-ONLY, lowest priority (see _match_fk_v2 tier 6);
    # kept separate from `direct` above, matching v1's design (the sheet has known
    # row-alignment defects, so it must never override a name/DOB match).
    b10tag = nodes["b10"].merge(refs["roll10x"].rename(columns={"avanti_id": "roll10_avanti_id"}),
                                on=["yr_s", "roll"], how="inner")[["node_id", "roll10_avanti_id"]].copy()
    b10tag["student_key"] = b10tag.node_id.map(n2k)
    b10tag = b10tag.dropna(subset=["student_key"]).drop_duplicates("student_key")
    sid = sid.merge(b10tag[["student_key", "roll10_avanti_id"]], on="student_key", how="left")

    # ncst_only — student's cluster has NO board/entrance record, only NCST. Used
    # by _match_fk_v2 to route ONLY these students against the wider all-grade
    # avanti reference; everyone else matches against the safer grade-12-only
    # frame (see _read_avanti_reference docstring for why the wide frame isn't
    # safe as the default target).
    src_sets = contrib.groupby("student_key")["src"].agg(lambda s: frozenset(s))
    sid["ncst_only"] = sid["student_key"].map(src_sets) == frozenset({"ncst"})
    return sid


_AM_FUZZY_JACCARD_MIN = 0.5
_AM_FUZZY_MIN_SHARED = 2


def _am_fuzzy_ok(a: str, b: str) -> bool:
    """DOB-blocked fuzzy name match (LAST-RESORT tier): >=2 shared tokens AND
    token-Jaccard >= 0.5. Ported verbatim from v1's _fuzzy_ok."""
    ta, tb = set(a.split()), set(b.split())
    inter = len(ta & tb)
    return inter >= _AM_FUZZY_MIN_SHARED and inter / len(ta | tb) >= _AM_FUZZY_JACCARD_MIN


def _am_strong_tokens(name: str) -> frozenset:
    """Ported verbatim from v1's _strong_tokens: split on any non-letter, upper,
    drop <=2-char tokens (initials / honorifics / concatenated 'PV')."""
    return frozenset(t for t in re.split(r"[^A-Za-z]+", name.upper()) if len(t) > 2)


def _am_strong_ok(a: str, b: str) -> bool:
    """DOB-blocked strong name match. Ported verbatim from v1's _strong_ok:
    exact strong-token-set equality, OR subset with the smaller side >=2 tokens,
    OR >=2 shared strong tokens."""
    ta, tb = _am_strong_tokens(a), _am_strong_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if (ta <= tb or tb <= ta) and min(len(ta), len(tb)) >= 2:
        return True
    return len(ta & tb) >= 2


def _match_fk_v2(sid: pd.DataFrame, avanti_g12: pd.DataFrame, avanti_all: pd.DataFrame,
                 all_ids: set) -> pd.DataFrame:
    """Tiered Avanti fk match — ported from v1's _match_fk, run against v2's OWN
    `sid` (STEP 6, replacing the source-table passthrough) for ALL students
    (b10/b12/jee/neet AND ncst — one unified pipeline, see _build_sid). Priority
    (lowest wins): direct id -> name+dob -> name+dob swapped -> name+father exact
    (no DOB needed — the fallback that reaches DOB-less NCST 2023/2024) ->
    DOB-blocked strong name -> DOB-blocked fuzzy name (last resort) -> 10th-score
    crosswalk id (fill-only). Ambiguous (>1 distinct candidate) is withheld
    (fk=NULL), matching this build's precision-first posture throughout.

    Runs the SAME cascade twice against two different candidate pools, not two
    separate resolvers: sid.ncst_only students (no board/entrance record at all)
    match against avanti_all (the only way they get anything to match); everyone
    else matches against avanti_g12. See _read_avanti_reference's docstring —
    matching the general population against avanti_all was tried and reverted
    (it turned Foundation->TP re-enrollment id pairs into false ambiguity for a
    population that was previously matching cleanly)."""
    cand_cols = ["student_key", "fk", "pri", "conf", "cnt"]

    # pk -> {dim_student JNV names} — used ONLY to name-gate the direct-id tier
    # below. Built from avanti_all (broadest JNV frame) so a direct id whose only
    # dim_student rows are pre-grade-12 is still checkable.
    name_by_pk = (avanti_all.loc[_present(avanti_all.norm_name)]
                  .groupby("pk_student_id")["norm_name"].agg(set).to_dict())

    def _direct_ok(rec_name, fk) -> bool:
        """Keep a direct crosswalk id only if the student it points to actually
        carries the record's name. Catches ROW-MISALIGNED app->id / roll->id
        crosswalks (the #1/#6/#9 lesson, on the direct-id direction): a misaligned
        row hands back a real-but-WRONG id, and because direct id is the top tier
        it would otherwise override the correct name+dob match. Fallback = keep:
        if the candidate id is not in the JNV name frame (a legitimately non-JNV
        label) or the record has no name, we can't verify — preserve it rather
        than regress. Rejected ids fall through to the name+dob tiers below."""
        cand = name_by_pk.get(fk)
        if not cand or not rec_name or pd.isna(rec_name):
            return True
        return any(_name_agree(rec_name, cn) for cn in cand)

    def _match_one(sid, avanti):
        d0 = sid[_present(sid.source_avanti_student_id) & sid.source_avanti_student_id.isin(all_ids)]
        d0 = d0[[_direct_ok(n, f) for n, f in zip(d0.norm_name, d0.source_avanti_student_id)]]
        direct = pd.DataFrame({"student_key": d0.student_key, "fk": d0.source_avanti_student_id,
                               "pri": 1, "conf": "direct_student_id", "cnt": 1})

        def _name_match(right_dob_col, pri, conf):
            m = sid[sid.norm_name.notna() & sid.dob.notna()].merge(
                avanti[["pk_student_id", "norm_name", right_dob_col]],
                left_on=["norm_name", "dob"], right_on=["norm_name", right_dob_col])
            g = m.groupby("student_key").agg(cnt=("pk_student_id", "nunique"),
                                             cand=("pk_student_id", "first")).reset_index()
            return pd.DataFrame({"student_key": g.student_key,
                                 "fk": g.cand.where(g.cnt == 1), "pri": pri, "conf": conf, "cnt": g.cnt})

        nd = _name_match("dob", 2, "name_dob")
        nds = _name_match("dob_swapped", 3, "name_dob_swapped")

        # name+father EXACT match (no DOB required) — reaches DOB-less NCST
        # records (dakshana 2023/2024 carry father but no DOB) via the SAME
        # unified tiers, not a separate resolver. Exact join, matching v1's own
        # _resolve_ncst choice (not the lenient _father_ok subset-match used for
        # identity-clustering).
        def _father_match(already):
            cs = sid[sid.norm_name.notna() & _present(sid.norm_father) & ~sid.student_key.isin(already)]
            av = avanti[_present(avanti.norm_father)]
            m = cs.merge(av[["pk_student_id", "norm_name", "norm_father"]], on=["norm_name", "norm_father"])
            g = m.groupby("student_key").agg(cnt=("pk_student_id", "nunique"),
                                             cand=("pk_student_id", "first")).reset_index()
            return pd.DataFrame({"student_key": g.student_key, "fk": g.cand.where(g.cnt == 1),
                                 "pri": 4, "conf": "name_father", "cnt": g.cnt})

        def _blocked_match(pred, pri, conf, already):
            cs = sid[sid.norm_name.notna() & sid.dob.notna() & ~sid.student_key.isin(already)]
            mm = cs.merge(avanti[["pk_student_id", "norm_name", "dob"]], on="dob", suffixes=("", "_av"))
            mm = mm[[pred(n, a) for n, a in zip(mm.norm_name, mm.norm_name_av)]]
            g = mm.groupby("student_key").agg(cnt=("pk_student_id", "nunique"),
                                              cand=("pk_student_id", "first")).reset_index()
            return pd.DataFrame({"student_key": g.student_key, "fk": g.cand.where(g.cnt == 1),
                                 "pri": pri, "conf": conf, "cnt": g.cnt})

        resolved = set(pd.concat([direct, nd, nds]).loc[lambda d: d.fk.notna(), "student_key"])
        nf = _father_match(resolved)
        resolved = resolved | set(nf.loc[nf.fk.notna(), "student_key"])
        st = _blocked_match(_am_strong_ok, 5, "name_dob_strong", resolved)
        resolved = resolved | set(st.loc[st.fk.notna(), "student_key"])
        fz = _blocked_match(_am_fuzzy_ok, 6, "name_dob_fuzzy", resolved)

        x10 = pd.DataFrame(columns=cand_cols)
        if "roll10_avanti_id" in sid:
            xr = sid[_present(sid.roll10_avanti_id) & sid.roll10_avanti_id.isin(all_ids)]
            x10 = pd.DataFrame({"student_key": xr.student_key, "fk": xr.roll10_avanti_id,
                                "pri": 7, "conf": "roll10_crosswalk", "cnt": 1})

        return pd.concat([direct[cand_cols], nd[cand_cols], nds[cand_cols], nf[cand_cols],
                          st[cand_cols], fz[cand_cols], x10[cand_cols]], ignore_index=True)

    sid_general = sid[~sid.ncst_only].drop(columns=["ncst_only"])
    sid_ncst = sid[sid.ncst_only].drop(columns=["ncst_only"])
    cand = pd.concat([_match_one(sid_general, avanti_g12), _match_one(sid_ncst, avanti_all)],
                     ignore_index=True)

    cand["fk_isnull"] = cand.fk.isna()
    cand = cand.sort_values(["student_key", "fk_isnull", "pri"]).drop_duplicates("student_key", keep="first")
    cand["match_confidence"] = cand.conf.where(cand.fk.notna(),
                                               other=pd.Series("ambiguous", index=cand.index).where(cand.cnt > 1))
    out = cand.rename(columns={"fk": "fk_avanti_student_id", "cnt": "match_count"})[
        ["student_key", "fk_avanti_student_id", "match_confidence", "match_count"]]
    print(f"  step 6 (own matcher) — avanti fk: {out.fk_avanti_student_id.notna().sum():,} resolved, "
          f"{(out.match_confidence == 'ambiguous').sum():,} ambiguous "
          f"({sid_ncst.student_key.nunique():,} ncst-only students routed to the wide reference)")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — outcome / marks payload (ported from v1's _read_marks + _enrich)
# ─────────────────────────────────────────────────────────────────────────────
_MARKS_YEAR_COLS = {"board_10th_exam_year", "board_12th_exam_year", "jee_test_year", "neet_test_year"}


def _read_marks(client) -> dict:
    """The result/marks frames merged onto the resolved spine to reach column-parity
    with v1 (jnv_student_outcome_mapping). Ported verbatim from v1's _read_marks:
    10th/12th subject marks + result, JEE mains+advanced scores/ranks/qualification,
    NEET score/rank/qualification, and the student_program/product lookup. Each frame
    is de-duplicated to ONE row per join key at query time (GROUP BY / QUALIFY
    ROW_NUMBER=1), so the left-merges in _build_rows cannot fan out the
    (student × attempt_year) grain. Only difference from v1: the year columns are
    returned as Int64 (v1 kept them string) to match v2's spine keys — the roll/app
    keys are `_S` strings on both sides, identical to how v2's nodes read them."""
    q = {
        "b10_marks": """
            SELECT exam_year AS board_10th_exam_year, roll_number AS board_10th_roll_number,
                ANY_VALUE(SAFE_CAST(total_marks AS FLOAT64)) AS marks_10_obtained,
                ANY_VALUE(result)                            AS result_10,
                MAX(IF(UPPER(subject_name) LIKE '%MATH%',    SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_math,
                MAX(IF(UPPER(subject_name) LIKE '%SCIENCE%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_science,
                MAX(IF(UPPER(subject_name) LIKE '%ENGLISH%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_english
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_10th`
            WHERE roll_number IS NOT NULL AND exam_year IS NOT NULL GROUP BY 1, 2""",
        "b12_marks": """
            SELECT exam_year AS board_12th_exam_year, roll_number AS board_12th_roll_number,
                ANY_VALUE(SAFE_CAST(total_marks AS FLOAT64)) AS marks_12_obtained,
                ANY_VALUE(result)                            AS result_12,
                MAX(IF(UPPER(subject_name) LIKE '%PHYSIC%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_physics,
                MAX(IF(UPPER(subject_name) LIKE '%CHEMIS%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_chemistry,
                MAX(IF(UPPER(subject_name) LIKE '%MATH%',   SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_maths,
                MAX(IF(UPPER(subject_name) LIKE '%BIOLOG%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_biology
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_12th`
            WHERE roll_number IS NOT NULL AND exam_year IS NOT NULL GROUP BY 1, 2""",
        "jee_results": """
            SELECT test_year AS jee_test_year, application_no AS jee_application_no,
                ANY_VALUE(mains_total_score)      AS jee_total_percentile,
                ANY_VALUE(mains_all_india_rank)   AS jee_air,
                ANY_VALUE(mains_category_rank)    AS jee_category_rank,
                ANY_VALUE(jee_mains_qualified)    AS jee_mains_qualified,
                ANY_VALUE(jee_advanced_qualified) AS jee_advanced_qualified,
                ANY_VALUE(adv_all_india_rank)     AS jee_adv_all_india_rank,
                ANY_VALUE(adv_category_rank)      AS jee_adv_category_rank,
                ANY_VALUE(adv_prep_category_rank) AS jee_adv_prep_category_rank
            FROM `avantifellows.external_data_sources.jnv_fact_jee_results`
            WHERE application_no IS NOT NULL AND test_year IS NOT NULL GROUP BY 1, 2""",
        "neet_results": """
            SELECT test_year AS neet_test_year, application_no AS neet_application_no,
                ANY_VALUE(neet_total_score)    AS neet_total_score,
                ANY_VALUE(neet_all_india_rank) AS neet_air,
                ANY_VALUE(neet_category_rank)  AS neet_category_rank,
                ANY_VALUE(neet_qualified)      AS neet_qualified
            FROM `avantifellows.external_data_sources.jnv_fact_neet_results`
            WHERE application_no IS NOT NULL AND test_year IS NOT NULL GROUP BY 1, 2""",
        "program_lookup": """
            SELECT fk_avanti_student_id, student_program, student_product FROM (
                SELECT COALESCE(pk_student_id, apaar_id) AS fk_avanti_student_id, student_program,
                       COALESCE(student_product_corrected, student_product) AS student_product,
                       academic_year, 1 AS src
                FROM `avantifellows.production_dbt_final.dim_student`
                UNION ALL
                SELECT COALESCE(pk_student_id, apaar_id), student_program, student_product, academic_year, 2 AS src
                FROM `avantifellows.production_dbt_final.dim_student_historical`
            )
            WHERE fk_avanti_student_id IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY fk_avanti_student_id ORDER BY src, academic_year DESC) = 1""",
    }
    out = {}
    for k, sql in q.items():
        df = client.query(sql).to_dataframe()
        for c in df.columns:
            if c in _MARKS_YEAR_COLS:
                df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")   # match v2 spine keys
            elif c.endswith("_qualified"):
                pass                                                             # boolean — leave as-is
            elif c.endswith("_rank") or c.startswith(("marks_", "jee_total", "jee_air",
                                                      "neet_total", "neet_air")):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            else:
                df[c] = _S(df[c])
        out[k] = df
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STEPS 4 & 5 — cohort_year (per student) + explode to (student × attempt_year)
# ─────────────────────────────────────────────────────────────────────────────
def _one_per_student(assigned: pd.DataFrame, val_cols: list[str]) -> pd.DataFrame:
    """Pick one record per student for a pre-entrance stage: earliest year, then
    lowest node_id (deterministic)."""
    return (assigned.sort_values(["student_key", "yr", "node_id"])
                    .drop_duplicates("student_key")[["student_key"] + val_cols])


def _build_rows(nodes: dict, key: pd.DataFrame, refs: dict, avanti_g12: pd.DataFrame,
                avanti_all: pd.DataFrame, all_ids: set, ncst24: pd.DataFrame,
                marks: dict) -> pd.DataFrame:
    n2k = key.set_index("node_id")["student_key"]

    def assign(stage):
        df = nodes[stage].copy()
        df["student_key"] = df.node_id.map(n2k)
        return df

    ncst, b10, b12, jee, neet = (assign(s) for s in STAGES)

    # ── pre-entrance stages: one per student (natural join key only) ───────────
    ncst_p = _one_per_student(
        ncst.assign(ncst_yr=ncst.yr).rename(columns={
            "yr_s": "ncst_test_year", "roll": "ncst_roll_no"}),
        ["ncst_source", "ncst_test_year", "ncst_roll_no", "ncst_yr"])
    b10_p = _one_per_student(
        b10.assign(b10_yr=b10.yr).rename(columns={
            "yr_s": "board_10th_exam_year", "roll": "board_10th_roll_number"}),
        ["board_10th_exam_year", "board_10th_roll_number", "b10_yr"])
    b12_p = _one_per_student(
        b12.assign(b12_yr=b12.yr).rename(columns={
            "yr_s": "board_12th_exam_year", "roll": "board_12th_roll_number"}),
        ["board_12th_exam_year", "board_12th_roll_number", "b12_yr"])

    # ── entrance: one row per (student, attempt_year) ─────────────────────────
    def pick_entrance(df, stage):
        g = (df.sort_values(["student_key", "yr", "node_id"])
               .drop_duplicates(["student_key", "yr"]))
        col = f"{stage}_application_no"
        return g.rename(columns={"yr": "attempt_year", "app": col})[["student_key", "attempt_year", col]]

    jee_a = pick_entrance(jee, "jee")
    neet_a = pick_entrance(neet, "neet")
    attempts = jee_a.merge(neet_a, on=["student_key", "attempt_year"], how="outer")

    # ── STEP 6 — Avanti fk via v2's own tiered matcher (not the source-table passthrough) ──
    sid = _build_sid(nodes, n2k, refs, ncst24)
    fk_df = _match_fk_v2(sid, avanti_g12, avanti_all, all_ids)

    # ── assemble the spine of all students, then attach attempts ──────────────
    students = pd.DataFrame({"student_key": key.student_key.unique()})
    students = (students.merge(ncst_p, on="student_key", how="left")
                        .merge(b10_p, on="student_key", how="left")
                        .merge(b12_p, on="student_key", how="left")
                        .merge(fk_df, on="student_key", how="left"))

    # cohort_year = COALESCE(12th, 10th+2, ncst+2, earliest entrance year)
    first_ent = (attempts.groupby("student_key")["attempt_year"].min()
                 .rename("first_ent_year").reset_index())
    students = students.merge(first_ent, on="student_key", how="left")
    students["cohort_year"] = (students["b12_yr"]
                               .fillna(students["b10_yr"] + 2)
                               .fillna(students["ncst_yr"] + 2)
                               .fillna(students["first_ent_year"]).astype("Int64"))

    rows = students.merge(attempts, on="student_key", how="left")   # left → keeps no-entrance students
    rows["jee_test_year"] = rows.attempt_year.where(rows.jee_application_no.notna()).astype("Int64")
    rows["neet_test_year"] = rows.attempt_year.where(rows.neet_application_no.notna()).astype("Int64")
    rows["ncst_test_year"] = pd.to_numeric(rows["ncst_test_year"], errors="coerce").astype("Int64")
    rows["board_10th_exam_year"] = pd.to_numeric(rows["board_10th_exam_year"], errors="coerce").astype("Int64")
    rows["board_12th_exam_year"] = pd.to_numeric(rows["board_12th_exam_year"], errors="coerce").astype("Int64")

    # ── STEP 7 — enrich with the outcome/marks payload (v1's _enrich) ──────────
    # All five are LEFT-merges onto frames unique per join key (see _read_marks),
    # so the (student × attempt_year) grain is preserved (no fan-out). Keys align
    # with v2's spine: years are Int64 both sides, roll/app are `_S` strings both
    # sides, fk is an `_S` string both sides.
    rows = (rows
            .merge(marks["b10_marks"], on=["board_10th_exam_year", "board_10th_roll_number"], how="left")
            .merge(marks["b12_marks"], on=["board_12th_exam_year", "board_12th_roll_number"], how="left")
            .merge(marks["jee_results"], on=["jee_test_year", "jee_application_no"], how="left")
            .merge(marks["neet_results"], on=["neet_test_year", "neet_application_no"], how="left")
            .merge(marks["program_lookup"], on="fk_avanti_student_id", how="left"))

    # stage-availability flags — STUDENT-LEVEL (true if the student has that stage in
    # ANY of their attempt-year rows), broadcast across the student's rows. jee is
    # split mains vs advanced (v1): has_jee_adv_data keys off the adv rank columns,
    # so this MUST run after the enrich merge above.
    flags = {
        "has_ncst_data":      rows["ncst_test_year"].notna(),
        "has_10th_data":      rows["board_10th_exam_year"].notna(),
        "has_12th_data":      rows["board_12th_exam_year"].notna(),
        "has_jee_mains_data": rows["jee_application_no"].notna(),
        "has_jee_adv_data":   rows[["jee_adv_all_india_rank", "jee_adv_category_rank",
                                    "jee_adv_prep_category_rank"]].notna().any(axis=1),
        "has_neet_data":      rows["neet_application_no"].notna(),
    }
    for col, s in flags.items():
        rows[col] = s.astype(int).groupby(rows["student_key"]).transform("max").astype(bool)

    for c in FINAL_COLS:
        if c not in rows:
            rows[c] = pd.NA
    # attempt_year is dropped from FINAL_COLS (v1 parity) but drives the sort order.
    rows = rows.sort_values(["cohort_year", "student_key", "attempt_year"]).reset_index(drop=True)
    return rows[FINAL_COLS]


def _resolve(client) -> pd.DataFrame:
    print("Step 1 — reading source nodes ...")
    nodes = _read_nodes(client)
    print("        reading crosswalks ...")
    refs = _read_crosswalks()
    ncst24 = _read_ncst_avanti_id()
    avanti_g12, avanti_all, all_ids = _read_avanti_reference(client)
    marks = _read_marks(client)
    print("Steps 2–3 — edges + union-find ...")
    key = _cluster(nodes, refs, ncst24)
    print("Steps 4–7 — cohort_year + avanti fk + explode to (student × attempt_year) + outcome marks ...")
    return _build_rows(nodes, key, refs, avanti_g12, avanti_all, all_ids, ncst24, marks)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — load
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    import argparse
    from google.cloud import bigquery
    from google.cloud.bigquery import LoadJobConfig, WriteDisposition

    argparse.ArgumentParser(
        description="Build jnv_student_outcome_mapping (clean-slate rewrite, steps 1-8; replaces v1).").parse_args()

    for f in (POOJITA, TENTH_SCORE, JEE_2025_RAW.local_path, JEE_2024_RAW.local_path, NEET_2024_RAW.local_path):
        if not f.exists():
            print(f"ERROR: reference file not found: {f}")
            sys.exit(1)

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
    out = _resolve(client)

    print(f"\nFull rebuild → {OUT_TABLE}: {len(out):,} rows, {out.student_key.nunique():,} students")
    client.load_table_from_dataframe(
        out, OUT_TABLE,
        job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
    ).result()

    # coverage summary
    summary = f"""
        SELECT cohort_year,
            COUNT(*) AS n_rows, COUNT(DISTINCT student_key) AS students,
            COUNTIF(ncst_test_year IS NOT NULL) AS has_ncst,
            COUNTIF(board_10th_exam_year IS NOT NULL) AS has_b10,
            COUNTIF(board_12th_exam_year IS NOT NULL) AS has_b12,
            COUNTIF(jee_test_year IS NOT NULL) AS has_jee,
            COUNTIF(neet_test_year IS NOT NULL) AS has_neet
        FROM `{OUT_TABLE}` GROUP BY 1 ORDER BY cohort_year"""
    print(f"\n{'cohort':<7}{'rows':>9}{'students':>10}{'ncst':>8}{'b10':>9}{'b12':>9}{'jee':>9}{'neet':>9}")
    print("-" * 78)
    for r in client.query(summary).result():
        print(f"  {str(r.cohort_year):<5}{r.n_rows:>9,}{r.students:>10,}{r.has_ncst:>8,}"
              f"{r.has_b10:>9,}{r.has_b12:>9,}{r.has_jee:>9,}{r.has_neet:>9,}")
    print("\nDone.")


if __name__ == "__main__":
    main()
