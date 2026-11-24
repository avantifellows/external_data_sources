#!/usr/bin/env python3
"""
Build jnv_student_outcome_mapping — the JNV cross-table student
journey/identity mapping.

Identity resolution is treated as a GRAPH problem:

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
The output is the identity MAP (student_key + cohort/attempt years + each
stage's natural join key) plus the Avanti fk (step 6).
fk_avanti_student_id / match_confidence / match_count are computed by this
file's OWN tiered name+DOB(+father) matcher against dim_student (see
_read_avanti_reference / _build_sid / _match_fk_v2), plus a lowest-priority
fill-only tier from production's operational NTA app→id crosswalk, which is the
only key able to reach the ~8k nameless JEE-2025 rows (see
_read_prod_nta_crosswalk). All five stages —
including NCST — resolve through the SAME pipeline: the union-find attaches an
NCST record to a b10/b12/jee/neet-anchored student by identity where one exists
(IDENTITY_RULES), and an NCST-only student enters `sid` via _build_sid's
coalesce + a name+father tier — one unified matcher for every stage, no
separate NCST path. Marks / outcome columns (step 7) come from
_read_marks + _build_rows. Output is 47 columns.

INPUTS & REPRODUCIBILITY: this build reads several raw Excel files from LOCAL
disk (the POOJITA / TENTH_SCORE identity crosswalks and the JEE/NEET/NCST raw
files — see the imports below), NOT from GCS. All are gitignored, but all are
backed up to GCS (see upload_to_gcs.py): the two mapping crosswalks are stored
as-is (original multi-sheet .xlsx, via `--mapping-files`), so they drop straight
back in; the JEE/NEET/NCST raw files are stored as single-sheet parquet (the
same sheet this build reads), so recovering those for a re-run needs a
parquet→xlsx conversion (or repointing those reads). The data is fully
recoverable from GCS; the build simply does not pull from GCS itself.

Output table (this build IS the production mapping — the canonical table):
    avantifellows.external_data_sources.jnv_student_outcome_mapping

Usage:
    python3 scripts/build_student_outcome_mapping.py
    # Impact check: write to a scratch table, not to the production table.
    python3 scripts/build_student_outcome_mapping.py --out-table avantifellows.analysis.<scratch_table>
    Do not run add_avanti_fk.py after a scratch run. It reads the production table.
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
import name_distance as nd

# This build IS the production JNV student outcome mapping — it writes the
# canonical `jnv_student_outcome_mapping` table.
OUT_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.jnv_student_outcome_mapping"

# Output columns — identity map + Avanti fk (step 6) + outcome/marks (step 7).
# The per-stage name/father/mother/dob comparison columns served their purpose
# (9 rounds of QA, see data-assistant-pr44.md findings #1-9) and are dropped
# here; each stage's natural join key (roll/app/test_year) is kept so a consumer
# can still reach the source row directly. The internal
# `attempt_year` column is dropped from the OUTPUT (the grain is encoded via the
# jee/neet _test_year columns); it is still used internally for sorting. The
# outcome/marks payload (step 7, below the join keys) comes from
# _read_marks + _build_rows.
FINAL_COLS = [
    "student_key", "cohort_year", "fk_avanti_student_id",
    "match_confidence", "match_count",
    # resolved student identity — coalesced across the student's linked records
    # (same values the STEP-6 fk matcher keyed on; see _build_sid).
    "student_name", "father_name", "mother_name", "student_dob", "student_gender",
    "student_program", "student_product",
    # stage-availability flags — STUDENT-LEVEL (true if the student has that stage
    # in ANY of their rows, broadcast onto every row so one row is enough to filter).
    "has_ncst_data", "has_10th_data", "has_12th_data", "has_jee_mains_data", "has_jee_adv_data", "has_neet_data",
    # NCST (selection test — Stage 1, upstream of 10th board)
    "ncst_source", "ncst_test_year", "ncst_roll_no",
    # 10th
    "board_10th_exam_year", "board_10th_roll_number",
    "board_10th_school_code", "board_10th_school_name", "board_10th_school_udise_code",
    "marks_10_obtained", "result_10",
    "marks_10_math", "marks_10_science", "marks_10_english",
    # 12th
    "board_12th_exam_year", "board_12th_roll_number",
    "board_12th_school_code", "board_12th_school_name", "board_12th_school_udise_code",
    "marks_12_obtained", "result_12",
    "marks_12_physics", "marks_12_chemistry", "marks_12_maths", "marks_12_biology",
    # JEE (incl. advanced)
    "jee_test_year", "jee_application_no", "jee_category",
    "jee_total_percentile", "jee_air", "jee_category_rank",
    "jee_mains_qualified", "jee_advanced_qualified",
    "jee_adv_all_india_rank", "jee_adv_category_rank", "jee_adv_prep_category_rank",
    # NEET
    "neet_test_year", "neet_application_no", "neet_category",
    "neet_total_score", "neet_air", "neet_category_rank", "neet_qualified",
    "neet_b1a_cleared", "neet_b1b_cleared",
]

STAGES = ["ncst", "b10", "b12", "jee", "neet"]

# Board-result files we hold (10th & 12th), by exam_year. A roll number is unique
# only WITHIN a year, so a 12th/10th roll named in a crosswalk must be resolved
# per-year (see _roll_cols) — the right year is chosen by the name gate. Searching
# every year (not just the on-time one) is what links DROPPERS, whose 12th board
# record sits an earlier year than their entrance sitting.
BOARD_YEARS = ["2022", "2023", "2024", "2025", "2026"]


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
# gender: MALE or FEMALE, else NULL (the gender check of _CheckedUnion and step 6)
_GENDER = lambda c: f"IF(UPPER(TRIM({c})) IN ('MALE', 'FEMALE'), UPPER(TRIM({c})), NULL)"


def _one_word_once(name):
    """A name that is one word written twice is that word once: 'ASHA ASHA' -> 'ASHA'. Some
    forms (the NCST form, and the Avanti enrolment forms) write the first name twice when the
    student has no surname. The word must have 4 or more letters: a short doubled word can be one
    name written with a space ('TIN TIN' is 'TINTIN'). Every other name stays as it is. Applied to
    the records (_finish_nodes) and to the Avanti names (_read_avanti_reference), so that both
    sides compare the same form."""
    if not isinstance(name, str):
        return name
    w = name.split(" ")
    return w[0] if len(w) == 2 and w[0] == w[1] and len(w[0]) >= 4 else name


def _finish_nodes(df: pd.DataFrame, stage: str, id_parts: list[str]) -> pd.DataFrame:
    """Common post-processing: stringify, blank→NA on identity cols, build node_id."""
    for c in df.columns:
        df[c] = _S(df[c])
    for c in ("dob", "norm_father", "norm_mother", "norm_name", "fk_avanti_id", "gender"):
        if c in df:
            df[c] = _blank_to_na(df[c])
    if "norm_name" in df:
        df["norm_name"] = df["norm_name"].map(_one_word_once).astype("string")
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
                ANY_VALUE({_GENDER('gender')})   AS gender,
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
                ANY_VALUE({_GENDER('gender')})   AS gender,
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
                ANY_VALUE({_GENDER('student_gender')}) AS gender,
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
                ANY_VALUE({_GENDER('student_gender')}) AS gender,
                ANY_VALUE(fk_avanti_student_id)  AS fk_avanti_id
            FROM `{ext}.jnv_fact_neet_results`
            WHERE application_no IS NOT NULL
            GROUP BY 1, 2""",
        "ncst": f"""
            SELECT 'dakshana' AS ncst_source, CAST(test_year AS STRING) AS yr_s,
                roll_no AS roll, {_NNC('student_full_name')} AS norm_name,
                {_NNC('father_name')} AS norm_father, {_NNC('mother_name')} AS norm_mother,
                FORMAT_DATE('%Y-%m-%d', SAFE.PARSE_DATE('%Y-%m-%d', SUBSTR(dob, 1, 10))) AS dob,
                {_GENDER('student_gender')} AS gender,
                fk_avanti_student_id AS fk_avanti_id
            FROM `{ext}.dakshana_fact_ncst_results` WHERE roll_no IS NOT NULL
            UNION ALL
            SELECT 'nvs', CAST(test_year AS STRING), roll_no,
                {_NNC('student_full_name')}, {_NNC('father_name')}, {_NNC('mother_name')},
                FORMAT_DATE('%Y-%m-%d', SAFE.PARSE_DATE('%Y-%m-%d', SUBSTR(dob, 1, 10))),
                {_GENDER('student_gender')},
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
    # (10th Roll Number -> Avanti Student ID), feeding the fk-matcher's b10 direct-id
    # tier. No year column in the sheet, so rather than merge on roll alone (a real
    # cross-year collision risk given this session's findings) we resolve it across
    # ALL board years + a name-agreement gate in _build_sid, same as every other roll
    # bridge in this file.
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
# production NTA (test_year, application_no) → Avanti id crosswalk
# ─────────────────────────────────────────────────────────────────────────────
# Attribute referees used to corroborate a production-supplied id: state, JNV school
# name, category, gender. All four are NAME-FREE by design — the population this
# crosswalk exists to reach carries no name at all (see _read_prod_nta_crosswalk) — and
# none is used by _match_fk_v2, so they are independent evidence rather than a
# restatement of the match key. Require ≥2 to agree.
_PROD_NTA_MIN_REFEREES = 2

# Referees are compared YEAR-ALIGNED: a candidate is judged only against its
# dim_student row(s) for the academic year(s) the exam sits in, never its whole history
# pooled. Pooling inflates a candidate purely for having MORE dim rows (more values to
# match against) — measured on the disagreement set, pooling scored production 2.51 vs
# the build's 2.63, while year-aligning the same rows gives 2.40 vs 2.60. Window =
# {test_year, test_year - 1}: an on-time student sits the exam in the academic year
# ending test_year, a dropper the year after their grade-12 year. Same alignment
# production's own fact_student_jee_main_results uses (test_year = RIGHT(academic_year,4)),
# widened by one, which lifts adjudicable coverage on the target population to 93%.
_PROD_NTA_YEAR_WINDOW = 1

# fk-tier priority for this source — LAST, below roll10_crosswalk (7). Named because
# _match_fk_v2 also has to exclude this tier from the g12→wide fallback decision.
_PROD_NTA_PRI = 8


def _read_prod_nta_crosswalk(client) -> dict:
    """Production's operational (test_year, application_no) → Avanti id crosswalk,
    from the NTA result facts. Returns {stage: frame[yr_s, app, avanti_id]}.

    WHY THIS SOURCE EXISTS HERE. `student_id` on those facts is passed straight
    through from the NTA upload (`stg_nta_*_results.student_id`) — ops fills it in
    when handing over the file — so it is an OPERATIONAL app→id crosswalk of exactly
    the same shape as the local `jee24`/`jee25`/`neet24` "Student ID" columns this
    file already trusts (see _deterministic_edges (d)), just BQ-native, all-years and
    refreshed with each NTA load. It is INDEPENDENT of this build: no dbt model reads
    `external_data_sources`, so there is no feedback loop through add_avanti_fk.py.

    WHAT IT FIXES. The JEE 2025 "All JNV Candidates" file carries NO name, dob or
    father for 8,066 of its 12,103 rows (only an application number + scores), and
    its own `avanti_studentid` column covers just 733. Those rows therefore become
    orphan size-1 `jee:2025:<app>` clusters that NO name/dob tier in _match_fk_v2 can
    ever reach — they end up fk-less while the SAME student sits elsewhere in the
    table (as a board-anchored cluster, or as a `dim_passthrough` roster row claiming
    "no outcome"). This crosswalk is the only key that can join those two halves.
    Reported as a recall gap on data-assistant PR #90: 780 `dim_passthrough` students
    have a production JEE/NEET outcome, and 729 of their exam rows are sitting in
    jnv_fact_* under the very same (test_year, application_no).

    WHY IT IS FILL-ONLY, AND GATED. Production's `student_id` is reliable but NOT
    better than us when it conflicts. Measured against the current table: it supplies an
    id for 5,441 exam rows, of which 3,328 AGREE with the fk we already have (97.5% of
    everything checkable), 125 disagree, and 1,988 are rows we cannot match at all.
    On the 125 disagreements, 39 ids do not exist in dim_student/_historical in ANY
    academic year, and on the 86 that do, the four year-aligned referees make it a
    near-tie: build 2.60 vs production 2.40, build ahead on only 14 rows to production's
    9 with 29 ties. There is no evidence either way, so we do not churn 86 existing
    links — hence:
      • FILL-ONLY — consumed as the LOWEST fk tier (see _match_fk_v2), so it can only
        ever fill a blank, never override a name/dob (or roll10) match. Ranking it above
        a name tier was tested and rejected on the numbers above.
      • ATTRIBUTE-GATED — kept only if ≥_PROD_NTA_MIN_REFEREES of the four referees
        agree, year-aligned. On the target population production scores 3.11/4 with 93%
        coverage, i.e. it is strongly corroborated exactly where it is needed; the gate
        drops the weakly-corroborated tail (1,988 → 1,820).
    Names are NOT checked here (the target rows have none); _match_fk_v2 applies the
    existing `_direct_ok` name gate on top, which still vetoes a candidate whose name is
    visible and disagrees.

    COVERAGE IS 2025+ ONLY, and that is not a bug. Production only began populating
    `application_no` on the NTA upload from 2024: it is blank for every row 2013–2023,
    ~0.3% filled in 2024, ~90% in 2025 and ~99.8% in 2026. So this crosswalk cannot help
    2021–2023 under any design — there is no join key on production's side. It lands
    where it is needed anyway, since JEE 2025 is the nameless file.

    DELIBERATELY NOT INCLUDED:
      • `fact_student_jee_main_results_overall` — pre-selects 'Overall'/Session 1 and
        excludes CoE NEET batches: 864 fewer (test_year, app) pairs than the
        underlying table used here.
      • `fact_student_jee_advanced_results` — its `application_no` is a DIFFERENT
        namespace (Advanced registration no, not the Mains app no the `jee` nodes are
        keyed on): only 72 of its 1,069 pairs hit a jee node, vs 3,904 for Mains. It
        would buy almost nothing and risks a false link on a namespace collision.

    Kept only where (test_year, application_no) maps to exactly ONE id — the same
    unambiguity posture as every other bridge in this file. Note `student_id` is never
    NULL on these facts, it is EMPTY-STRING when unset (280 rows), so it must be
    filtered on TRIM(...) != '' — an `IS NOT NULL` guard silently passes them, and
    because exactly one dim_student row also carries an empty coalesced id, every such
    app would otherwise "resolve" to that one student.
    """
    id_expr = "COALESCE(student_id, apaar_id)"
    prod = f"""
        SELECT stage, ty, app, ANY_VALUE(id) AS avanti_id FROM (
            SELECT 'jee' AS stage, CAST(test_year AS STRING) AS ty,
                   application_no AS app, {id_expr} AS id
            FROM `avantifellows.production_dbt_final.fact_student_jee_main_results`
            WHERE application_no IS NOT NULL AND TRIM({id_expr}) != ''
            UNION ALL
            SELECT 'neet', CAST(test_year AS STRING), application_no, {id_expr}
            FROM `avantifellows.production_dbt_final.fact_student_neet_results`
            WHERE application_no IS NOT NULL AND TRIM({id_expr}) != '')
        GROUP BY stage, ty, app HAVING COUNT(DISTINCT id) = 1"""
    # the JNV source row's name-free attributes, for corroboration
    attrs = ("UPPER(TRIM(COALESCE(jnv_name,''))) AS s_school,"
             " UPPER(TRIM(COALESCE(student_state,''))) AS s_state,"
             " UPPER(TRIM(COALESCE(category,''))) AS s_cat,"
             " UPPER(TRIM(COALESCE(student_gender,''))) AS s_gender")
    src = f"""
        SELECT 'jee' AS stage, CAST(test_year AS STRING) AS ty, application_no AS app, {attrs}
        FROM `avantifellows.external_data_sources.jnv_fact_jee_results`
        WHERE application_no IS NOT NULL
        UNION ALL
        SELECT 'neet', CAST(test_year AS STRING), application_no, {attrs}
        FROM `avantifellows.external_data_sources.jnv_fact_neet_results`
        WHERE application_no IS NOT NULL"""
    # one row per (Avanti id, academic-year-end) — NOT one pooled profile per id, so a
    # candidate is judged only on the year(s) the exam sits in (see _PROD_NTA_YEAR_WINDOW).
    dim_cols = ("SUBSTR(CAST(academic_year AS STRING), 6, 4) AS ay4,"
                " NULLIF(UPPER(TRIM(student_school)),'') AS school,"
                " NULLIF(UPPER(TRIM(student_school_state)),'') AS state,"
                " NULLIF(UPPER(TRIM(student_category)),'') AS cat,"
                " NULLIF(UPPER(TRIM(student_gender)),'') AS gender")
    dim_filt = "WHERE TRIM(COALESCE(pk_student_id, apaar_id)) != ''"
    dim = f"""
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk, {dim_cols}
        FROM `avantifellows.production_dbt_final.dim_student` {dim_filt}
        UNION DISTINCT
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id), {dim_cols}
        FROM `avantifellows.production_dbt_final.dim_student_historical` {dim_filt}"""
    # school agreement = the JNV school name and dim_student's school share a >3-char
    # token ('JNV KOPPAL' vs 'JNV Koppal Karnataka'); bare 'JNV' is too short to count.
    school_ok = ("(SELECT COUNT(*) FROM UNNEST(SPLIT(s.s_school, ' ')) t"
                 " WHERE LENGTH(t) > 3 AND t IN UNNEST(SPLIT(d.school, ' '))) > 0")
    sql = f"""
        WITH prod AS ({prod}), src AS ({src}), dim AS ({dim})
        SELECT p.stage, p.ty AS yr_s, p.app, p.avanti_id
        FROM prod p
        JOIN src s ON s.stage = p.stage AND s.ty = p.ty AND s.app = p.app
        JOIN dim d ON d.pk = p.avanti_id
                  AND d.ay4 BETWEEN CAST(CAST(p.ty AS INT64) - {_PROD_NTA_YEAR_WINDOW} AS STRING)
                                AND p.ty
        GROUP BY p.stage, p.ty, p.app, p.avanti_id
        HAVING (
            CAST(LOGICAL_OR(s.s_state  != '' AND s.s_state  = d.state)  AS INT64)
          + CAST(LOGICAL_OR(s.s_gender != '' AND s.s_gender = d.gender) AS INT64)
          + CAST(LOGICAL_OR(s.s_cat    != '' AND s.s_cat    = d.cat)    AS INT64)
          + CAST(LOGICAL_OR({school_ok}) AS INT64)
        ) >= {_PROD_NTA_MIN_REFEREES}"""
    df = client.query(sql).to_dataframe()
    for c in df.columns:
        df[c] = _S(df[c])
    out = {s: g[["yr_s", "app", "avanti_id"]].reset_index(drop=True)
           for s, g in df.groupby("stage")}
    for s in ("jee", "neet"):
        print(f"  crosswalk prod_{s:<5}{len(out.get(s, [])):>7,}  "
              f"gated (test_year, app)→id")
    return out


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


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2b — round 2: fuzzy-name identity edges, last
# ─────────────────────────────────────────────────────────────────────────────
# After all exact edges (rounds 0 and 1), each IDENTITY_RULE gets a fuzzy pass for the
# students that are still apart: a student who has the rule's left stage and not its
# right stage, against a student who has the right stage and not the left stage.
# Names use name_distance.py: an edit distance with low costs for common Indian spelling
# variants (idea from devdatalab/masala-merge; our own code). In the fuzzy pass:
#   • the student name may be a spelling variant (nd.same_name);
#   • name + DOB rule:    the same DOB; the fathers must not differ (nd.father_check_v2);
#   • name + father rule: the fathers must match (nd.father_check_v2 in FUZZY_FATHER_OK).
# Pairs are compared only inside blocks: (DOB, first letter of the name) for a DOB rule;
# (name skeleton, first letter of the father) for a father rule, with the skeleton taken
# in word order and in sorted word order. Then the rule's year gap and the same
# component-level unambiguity check as the exact pass.
# Each fuzzy edge then goes through _CheckedUnion like every other union (one record per
# stage, years that fit), and is refused when step 6 gives the two students two different
# Avanti ids (_round2_fuzzy).
FUZZY_FATHER_OK = {"same", "spelling variant", "initial or dropped word", "joined or split words"}
_FUZZY_OPTS = frozenset({"placeholders", "abbrev", "prefix", "span"})
_FUZZY_COLS = ["node_id", "yr", "norm_name", "norm_father", "dob"]


def _fuzzy_keys(nodes: dict) -> dict:
    """Per stage: the node columns that the fuzzy pass needs, plus its blocking keys."""
    out = {}
    for st in STAGES:
        df = nodes[st][_FUZZY_COLS].dropna(subset=["norm_name", "yr"]).copy()
        df = df[df.norm_name.str.len() > 0]
        df["skel"] = df.norm_name.map(nd.skeleton)
        df["skel_sorted"] = df.norm_name.map(nd.skeleton_sorted)
        df["nfl"] = df.skel.str[:1]
        df["ffl"] = df.norm_father.map(nd.father_first_letter)
        out[st] = df
    return out


def _fuzzy_rule_edges(fk: dict, left: str, right: str, keys: list, lo: int, hi: int,
                      comp: dict, comp_stages: dict) -> list[tuple]:
    """Fuzzy candidates of one IDENTITY_RULE between students that are still apart: the left
    student has no `right` record, the right student has no `left` record."""
    L, R = fk[left], fk[right]
    L = L[L.node_id.map(lambda n: right not in comp_stages[comp[n]]).astype(bool)]
    R = R[R.node_id.map(lambda n: left not in comp_stages[comp[n]]).astype(bool)]
    take = [c + s for c in _FUZZY_COLS for s in ("_l", "_r")]
    if "dob" in keys:
        L, R = L[_present(L.dob)], R[_present(R.dob)]
        m = L.merge(R, on=["dob", "nfl"], suffixes=("_l", "_r"))
        m["dob_l"] = m["dob_r"] = m["dob"]
        m = m[take]
    else:
        L, R = L[L.ffl.notna()], R[R.ffl.notna()]
        m = pd.concat([L.merge(R, on=[blk, "ffl"], suffixes=("_l", "_r"))[take]
                       for blk in ("skel", "skel_sorted")], ignore_index=True)
    if m.empty:
        return []
    gap = m.yr_r - m.yr_l
    m = m[(gap >= lo) & (gap <= hi)].drop_duplicates(["node_id_l", "node_id_r"])
    m = m.assign(comp_l=m.node_id_l.map(comp), comp_r=m.node_id_r.map(comp))
    m = m[m.comp_l != m.comp_r]
    # row filters as boolean Series on m's index (a plain empty list would select columns)
    m = m[pd.Series([nd.same_name(a, b) for a, b in zip(m.norm_name_l, m.norm_name_r)], index=m.index, dtype=bool)]
    if "dob" in keys:
        ok = [not (isinstance(a, str) and isinstance(b, str)) or nd.father_check_v2(a, b, _FUZZY_OPTS) != "different"
              for a, b in zip(m.norm_father_l, m.norm_father_r)]
    else:
        ok = [nd.father_check_v2(a, b, _FUZZY_OPTS) in FUZZY_FATHER_OK
              for a, b in zip(m.norm_father_l, m.norm_father_r)]
    m = m[pd.Series(ok, index=m.index, dtype=bool)]
    if m.empty:
        return []
    lc = m.groupby("comp_l")["comp_r"].transform("nunique")
    rc = m.groupby("comp_r")["comp_l"].transform("nunique")
    m = m[(lc == 1) & (rc == 1)]
    return list(zip(m.node_id_l, m.node_id_r))


def _student_avanti_ids(cu, nodes: dict, refs: dict, ncst24: pd.DataFrame, avanti: dict) -> dict:
    """component root -> the Avanti id that step 6 gives the student as it is now, before the
    fuzzy round. The same matcher as step 6 (_build_sid + _match_fk_v2), on this build's own
    inputs (source records, crosswalks, dim_student)."""
    uf = cu.uf
    n2k = pd.Series({n: uf.find(n) for n in uf.parent}, name="student_key")
    sid = _build_sid(nodes, n2k, refs, ncst24, avanti["prod_nta"])
    tie = avanti.get("tie")
    fk = _match_fk_v2(sid, avanti["g12"], avanti["all"], avanti["all_ids"],
                      rec=_record_identities(nodes, n2k), tie=tie,
                      facts=_student_facts(nodes, n2k, tie) if tie is not None else None)
    fk = fk[fk.fk_avanti_student_id.notna()]
    return {k: {v} for k, v in zip(fk.student_key, fk.fk_avanti_student_id)}


def _round2_fuzzy(cu, nodes: dict, refs: dict, ncst24: pd.DataFrame, avanti: dict) -> None:
    """Round 2: add the fuzzy-name edges, then the father's-word edges (_middle_name_edges), last.
    Each edge goes through _CheckedUnion (one record per stage, years that fit). An edge is
    also refused when step 6 gives the two students two different Avanti ids
    (_student_avanti_ids). The build does not read fk_avanti_student_id from the source
    tables, because add_avanti_fk.py writes it from this table."""
    uf = cu.uf
    comp = {n: uf.find(n) for n in uf.parent}
    comp_stages = {root: {r[0] for r in recs} for root, recs in cu.recs.items()}
    print("    step 6 matcher on the students before the fuzzy round:")
    ids = _student_avanti_ids(cu, nodes, refs, ncst24, avanti)   # root -> {Avanti id}

    fk = _fuzzy_keys(nodes)
    cands = []
    # name + DOB rules first (stronger), then name + father rules
    for left, right, keys, lo, hi in sorted(IDENTITY_RULES, key=lambda r: "dob" not in r[2]):
        e = _fuzzy_rule_edges(fk, left, right, keys, lo, hi, comp, comp_stages)
        print(f"    fuzzy {left}->{right} {'+'.join(keys)}: {len(e):,} candidates")
        cands += e

    fmt = lambda recs: " ".join(sorted(f"{r[0]}:{r[1]}" for r in recs))
    before, added = len(cu.refused), 0
    for a, b in cands:
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            continue
        ia, ib = ids.get(ra, set()), ids.get(rb, set())
        if ia and ib and not ia & ib:
            cu.refused.append(("fuzzy names", "two different Avanti ids",
                               a, b, fmt(cu.recs[ra]), fmt(cu.recs[rb])))
            continue
        cu.union(a, b, "fuzzy names")
        if uf.find(a) == uf.find(b):
            ids[uf.find(a)] = ids.pop(ra, set()) | ids.pop(rb, set())
            added += 1
    print(f"    {'fuzzy names':<22}{len(cands):>9,} edges, {len(cu.refused) - before:>6,} refused")
    print(f"  round-2 fuzzy edges:    {added:>8,}")

    # The father's first name as an extra word, after the fuzzy edges, with the same checks.
    comp = {n: uf.find(n) for n in uf.parent}
    comp_stages = {root: {r[0] for r in recs} for root, recs in cu.recs.items()}
    school = (avanti.get("tie") or {}).get("school", {})
    cands = []
    # name + DOB rules first (stronger), then name + father rules
    for left, right, keys, lo, hi in sorted(IDENTITY_RULES, key=lambda r: "dob" not in r[2]):
        e = _middle_name_edges(fk, left, right, keys, lo, hi, comp, comp_stages, school)
        print(f"    father's word {left}->{right} {'+'.join(keys)}: {len(e):,} candidates")
        cands += e
    global _MIDDLE
    _MIDDLE = []
    before, added = len(cu.refused), 0
    for a, b, info in cands:
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            continue
        ia, ib = ids.get(ra, set()), ids.get(rb, set())
        if ia and ib and not ia & ib:
            cu.refused.append((_MIDDLE_EDGE, "two different Avanti ids",
                               a, b, fmt(cu.recs[ra]), fmt(cu.recs[rb])))
            continue
        recs_a, recs_b = fmt(cu.recs[ra]), fmt(cu.recs[rb])
        cu.union(a, b, _MIDDLE_EDGE)
        if uf.find(a) == uf.find(b):
            ids[uf.find(a)] = ids.pop(ra, set()) | ids.pop(rb, set())
            _MIDDLE.append({"node_a": a, "node_b": b, **info,
                            "student_a_records": recs_a, "student_b_records": recs_b})
            added += 1
    print(f"    {_MIDDLE_EDGE:<22}{len(cands):>9,} edges, {len(cu.refused) - before:>6,} refused")
    print(f"  father's-word edges:    {added:>8,}")


# The father's first name as an extra word. Some records write the student's name with the
# father's first name as one more word ('ASHA RAMESH PATIL' or 'PATIL ASHA RAMESH', father
# 'RAMESH PATIL'), and other records of the same student do not ('ASHA PATIL', 'PATIL ASHA').
# The name rules see two names, so the records stay apart. This pass links a record of one
# student and a record of another student that are still apart (as in the fuzzy pass) when:
#   • one name is the other name with one more word, spaces ignored, and that word is the
#     first word of the father's name of one of the two records (any position in the name;
#     the name with the word has 3 or more words);
#   • for a name + DOB rule: the DOBs are the same, and the fathers do not differ
#     (nd.father_check_v2) when both records have a father;
#   • for a name + father rule: the fathers match (nd.father_check_v2 in FUZZY_FATHER_OK),
#     and a 10th and a 12th record have the same school code;
#   • the years fit the IDENTITY_RULE, and each student has only one such pair for the rule.
# The link then goes through _CheckedUnion (no early exam, as for a fuzzy link) and the
# "two different Avanti ids" check of the fuzzy round.
_MIDDLE_EDGE = "father's name as a word"
_INEXACT_EDGES = {"fuzzy names", _MIDDLE_EDGE}
_MIDDLE = None   # scratch run: the father's-word links (written to <out_table>_middle_name)


def _father_first_word(father) -> str | None:
    """The first word of the father's name after the honorifics, or None (fewer than 2 letters)."""
    if not isinstance(father, str):
        return None
    fwords = nd._strip_honorific(nd._raw_words(father))
    return fwords[0] if fwords and len(fwords[0]) >= 2 else None


def _names_without_one_word(name) -> list[tuple]:
    """(word, position, name without the word, spaces removed) for each word of a name of 3 or
    more words. Position is 'first', 'middle' or 'last'. A word that is in the name two times
    gives one row for each place; when the two names without it are the same ('ASHA RAMESH
    RAMESH'), only the first row stays."""
    if not isinstance(name, str):
        return []
    words = nd._raw_words(name)
    if len(words) < 3:
        return []
    out, seen = [], set()
    for i, w in enumerate(words):
        core = "".join(words[:i] + words[i + 1:])
        if (w, core) in seen:
            continue
        seen.add((w, core))
        pos = "first" if i == 0 else "last" if i == len(words) - 1 else "middle"
        out.append((w, pos, core))
    return out


def _middle_name_edges(fk: dict, left: str, right: str, keys: list, lo: int, hi: int,
                       comp: dict, comp_stages: dict, school: dict) -> list[tuple]:
    """Father's-word candidates of one IDENTITY_RULE between students that are still apart: the
    left student has no `right` record, the right student has no `left` record. Returns
    (left node, right node, {"rule", "position"}) for each link."""
    dob_rule = "dob" in keys
    cols = ["node_id", "yr", "norm_father", "fw"] + (["dob"] if dob_rule else [])

    def prep(df, other):
        df = df[_present(df.dob)] if dob_rule else df[df.norm_father.notna()]
        df = df[df.node_id.map(lambda n: other not in comp_stages[comp[n]]).astype(bool)].copy()
        df["full"] = ["".join(nd._raw_words(n)) for n in df.norm_name]
        df["fw"] = [_father_first_word(f) for f in df.norm_father]   # object dtype: None, not NA
        return df

    def with_word(df):
        """One row per (record, word that can be taken away)."""
        rows = [(n, w, p, c) for n, name in zip(df.node_id, df.norm_name)
                for w, p, c in _names_without_one_word(name)]
        words = pd.DataFrame(rows, columns=["node_id", "word", "pos", "core"])
        return df[cols].merge(words, on="node_id")

    def pairs(big, small, big_is_left):
        """Pairs where the `big` name, less one word, is the `small` name."""
        on = ["dob"] if dob_rule else []
        m = with_word(big).merge(small[cols + ["full"]], left_on=on + ["core"],
                                 right_on=on + ["full"], suffixes=("_b", "_s"))
        m = m[(m.word == m.fw_b) | (m.word == m.fw_s)]
        b, s = ("_l", "_r") if big_is_left else ("_r", "_l")
        return pd.DataFrame({"node_id" + b: m.node_id_b, "node_id" + s: m.node_id_s,
                             "yr" + b: m.yr_b, "yr" + s: m.yr_s,
                             "norm_father" + b: m.norm_father_b, "norm_father" + s: m.norm_father_s,
                             "pos": m.pos})

    L, R = prep(fk[left], right), prep(fk[right], left)
    m = pd.concat([pairs(L, R, True), pairs(R, L, False)], ignore_index=True)
    if m.empty:
        return []
    gap = m.yr_r - m.yr_l
    m = m[(gap >= lo) & (gap <= hi)].drop_duplicates(["node_id_l", "node_id_r"])
    m = m.assign(comp_l=m.node_id_l.map(comp), comp_r=m.node_id_r.map(comp))
    m = m[m.comp_l != m.comp_r]
    if dob_rule:
        ok = [not (isinstance(a, str) and isinstance(b, str)) or nd.father_check_v2(a, b, _FUZZY_OPTS) != "different"
              for a, b in zip(m.norm_father_l, m.norm_father_r)]
    else:
        ok = [nd.father_check_v2(a, b, _FUZZY_OPTS) in FUZZY_FATHER_OK
              for a, b in zip(m.norm_father_l, m.norm_father_r)]
    m = m[pd.Series(ok, index=m.index, dtype=bool)]
    if {left, right} == {"b10", "b12"}:
        same = [school.get(a) is not None and school.get(a) == school.get(b)
                for a, b in zip(m.node_id_l, m.node_id_r)]
        m = m[pd.Series(same, index=m.index, dtype=bool)]
    if m.empty:
        return []
    lc = m.groupby("comp_l")["comp_r"].transform("nunique")
    rc = m.groupby("comp_r")["comp_l"].transform("nunique")
    m = m[(lc == 1) & (rc == 1)]
    rule = "+".join(keys)
    return [(a, b, {"rule": rule, "position": p}) for a, b, p in zip(m.node_id_l, m.node_id_r, m.pos)]


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
# Twin check: two records with the same DOB and parents whose names pass
# _name_subset or _name_similar can still be twins with close given names (a shared surname
# makes the whole names look alike). The check runs only when the (dob, father, mother) block
# shows a second person: two records of one stage and one year. Then nd.given_names_differ
# refuses the pair when each name keeps a word that has no partner in the other name.
# Without a second person, a spelling difference is one person (a typo), and the pair links.
# The refused pairs go to _REFUSED.
_TWIN_REFUSED = []


def _stage_year(node_id: str) -> tuple:
    """(stage, year) of a node id: 'b10:<yr>:<roll>' -> ('b10', '<yr>');
    'ncst:<source>:<yr>:<roll>' -> ('ncst', '<yr>') (both NCST sources are one stage)."""
    parts = node_id.split(":")
    return (parts[0], parts[2] if parts[0] == "ncst" else parts[1])


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
    highly specific. Skips placeholder parent tokens and oversized (garbage) blocks.
    The name gates still pass twins whose given names are close. When the block shows a
    second person (two records of one stage and one year), the twin check
    (nd.given_names_differ) refuses those pairs and keeps them in _TWIN_REFUSED."""
    cols = ["node_id", "norm_name", "norm_father", "norm_mother", "dob"]
    alln = pd.concat([nodes[s][cols] for s in STAGES], ignore_index=True)
    sub = alln[_present(alln.dob) & _present(alln.norm_name)
               & _present(alln.norm_father) & _present(alln.norm_mother)].copy()
    sub["ff"] = sub.norm_father.str.split().str[0]
    sub["mf"] = sub.norm_mother.str.split().str[0]
    sub = sub[(sub.ff.str.len() >= 3) & (sub.mf.str.len() >= 3)
              & ~sub.ff.isin(_PARENT_STOP) & ~sub.mf.isin(_PARENT_STOP)]
    global _TWIN_REFUSED
    edges, _TWIN_REFUSED = [], []
    for _, grp in sub.groupby(["dob", "ff", "mf"], sort=True):
        recs = list(zip(grp.node_id, grp.norm_name))
        if len(recs) < 2 or len(recs) > _PARENT_DOB_BLOCK_MAX:
            continue
        stage_years = [_stage_year(n) for n in grp.node_id]
        second_person = len(set(stage_years)) < len(stage_years)
        pairs = []
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                na, nb = recs[i][1], recs[j][1]
                if _name_subset(na, nb) or _name_similar(na, nb):
                    if second_person and nd.given_names_differ(na, nb):
                        _TWIN_REFUSED.append((recs[i][0], recs[j][0]))
                    else:
                        pairs.append((_pair_order(na, nb), *sorted((recs[i][0], recs[j][0]))))
        # The first union of a record wins (one record per stage), and twins with close given
        # names ('ANKIT'/'ANKITA') pass the twin check. So the closest names join first, then
        # the record ids, and the result does not depend on the order of the rows.
        edges += [(a, b) for _, a, b in sorted(pairs)]
    return edges


def _pair_order(na: str, nb: str) -> tuple:
    """Sort key of a name pair, closest first: the same name (spaces ignored), then the
    higher character similarity."""
    x, y = _despace(na), _despace(nb)
    return (x != y, -difflib.SequenceMatcher(None, x, y).ratio())


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


# ── one record per stage, years that fit ──────────────────────────────────────
# Every union is checked against the two whole students before it joins them:
#   • at most one NCST, one 10th and one 12th record per student;
#   • JEE and NEET may repeat (a repeater sits again in a later year), but at most
#     one JEE and one NEET record per year;
#   • every pair of the student's records fits the journey years (_JOURNEY_YEARS).
#     A JEE or NEET record may sit one year before the 12th year (an early attempt,
#     in grade 11). An exact link may join an early attempt when the father or the
#     mother of the early record agrees with a parent on the 10th, 12th or NCST record
#     of the other student (two people can share a name and DOB). A fuzzy link may not
#     make an exam early: it joins only when each early exam already has a 10th,
#     12th or NCST year in its own student.
# A link that would break a rule is refused. Edges are applied strongest first:
# crosswalk ids, entrance same-person edges, DOB/parent edges (round 0), then the
# identity rules (round 1). Refused links are kept in _REFUSED (a scratch run writes
# them to <out_table>_refused).
_JOURNEY_YEARS = {
    # (earlier, later): (lo, hi) — gap = later.yr - earlier.yr; hi None = no upper limit
    ("ncst", "b10"): (0, 0), ("ncst", "b12"): (2, 2), ("b10", "b12"): (2, 2),
    ("ncst", "jee"): (2, None), ("ncst", "neet"): (2, None),
    ("b10", "jee"): (2, None), ("b10", "neet"): (2, None),
    ("b12", "jee"): (0, None), ("b12", "neet"): (0, None),
}
_ONE_PER_STUDENT = {"ncst", "b10", "b12"}
_ONE_PER_YEAR = {"jee", "neet"}
_EARLY_YEARS = 1   # a JEE or NEET record may sit this many years before the 12th year
_REFUSED = None


def _years_fit(recs_a: list, recs_b: list, early_ok: bool, parents_agree=None) -> str | None:
    """None when every (stage, yr) of one student fits every (stage, yr) of the other, else
    the reason. recs are (stage, yr, node_id). A JEE or NEET record one year before the 12th
    year (an early attempt) fits when its own student already has a 10th, 12th or NCST year
    (the link makes no new early exam), or on an exact link (early_ok) when
    parents_agree(early node, the 10th / 12th / NCST nodes of the other student) is True."""
    anchors = ([n for s, _, n in recs_a if s in _ONE_PER_STUDENT],
               [n for s, _, n in recs_b if s in _ONE_PER_STUDENT])
    for s1, y1, n1 in recs_a:
        for s2, y2, n2 in recs_b:
            # the later stage of the pair is the JEE or NEET record, when there is one
            if (s1, s2) in _JOURNEY_YEARS:
                (lo, hi), gap, later, own, other = _JOURNEY_YEARS[(s1, s2)], y2 - y1, n2, anchors[1], anchors[0]
                later_stage = s2
            elif (s2, s1) in _JOURNEY_YEARS:
                (lo, hi), gap, later, own, other = _JOURNEY_YEARS[(s2, s1)], y1 - y2, n1, anchors[0], anchors[1]
                later_stage = s1
            else:
                continue
            if lo <= gap and (hi is None or gap <= hi):
                continue
            if later_stage not in _ONE_PER_YEAR or gap != lo - _EARLY_YEARS:
                return "years do not fit"
            if own:
                continue                       # already an early attempt of its own student
            if not early_ok:
                return "exam one year early on a fuzzy link"
            if parents_agree is not None and not parents_agree(later, other):
                return "early exam, parents do not agree"
    return None


def _gender_conflict(g_a, n_a, g_b, n_b) -> bool:
    """True when two people are named: the genders differ AND the given names differ
    (nd.given_names_differ), and the names are not one typo apart (nd.one_letter_typo). A
    gender alone can be a data-entry error, and twins can have one DOB and one surname.
    Used on two records (_CheckedUnion) and on a student and an Avanti student (step 6)."""
    if not (isinstance(g_a, str) and isinstance(g_b, str) and g_a and g_b and g_a != g_b):
        return False
    if not (isinstance(n_a, str) and isinstance(n_b, str) and n_a and n_b):
        return False
    return nd.given_names_differ(n_a, n_b) and not nd.one_letter_typo(n_a, n_b)


class _CheckedUnion:
    """Union-find wrapper: refuses a union when the joined student would break a rule above,
    or when a record of one student and a record of the other are two people (_gender_conflict)."""

    def __init__(self, uf: _UnionFind, nodes: dict):
        self.uf = uf
        self.recs = {}      # root -> [(stage, yr, node_id)] (yr None when the record has no year)
        self.parents = {}   # node_id -> (norm_father, norm_mother)
        self.who = {}       # node_id -> (gender, norm_name), for records with both
        for st in STAGES:
            df = nodes[st]
            fathers = df.norm_father if "norm_father" in df else [None] * len(df)
            mothers = df.norm_mother if "norm_mother" in df else [None] * len(df)
            genders = df.gender if "gender" in df else [None] * len(df)
            for nid, yr, fa, mo, g, nm in zip(df.node_id, df.yr, fathers, mothers, genders, df.norm_name):
                if nid in uf.parent:
                    self.recs[nid] = [(st, int(yr) if pd.notna(yr) else None, nid)]
                    self.parents[nid] = (fa if isinstance(fa, str) and fa else None,
                                         mo if isinstance(mo, str) and mo else None)
                    if isinstance(g, str) and g and isinstance(nm, str) and nm:
                        self.who[nid] = (g, nm)
        self.refused = []

    def _parents_agree(self, node: str, others: list) -> bool:
        """True when the father or the mother of `node` agrees with that parent of one of
        `others` (nd.father_check_v2, the check of the fuzzy round)."""
        fa, mo = self.parents.get(node, (None, None))
        for o in others:
            fo, mo_o = self.parents.get(o, (None, None))
            if fa and fo and nd.father_check_v2(fa, fo, _FUZZY_OPTS) in FUZZY_FATHER_OK:
                return True
            if mo and mo_o and nd.father_check_v2(mo, mo_o, _FUZZY_OPTS) in FUZZY_FATHER_OK:
                return True
        return False

    def _why_not(self, ra: list, rb: list, early_ok: bool) -> str | None:
        if {r[0] for r in ra if r[0] in _ONE_PER_STUDENT} & {r[0] for r in rb if r[0] in _ONE_PER_STUDENT}:
            return "second NCST, 10th or 12th record"
        if ({(r[0], r[1]) for r in ra if r[0] in _ONE_PER_YEAR and r[1] is not None}
                & {(r[0], r[1]) for r in rb if r[0] in _ONE_PER_YEAR and r[1] is not None}):
            return "two JEE or two NEET records in one year"
        wa = [self.who[n] for _, _, n in ra if n in self.who]
        wb = [self.who[n] for _, _, n in rb if n in self.who]
        if any(_gender_conflict(ga, na, gb, nb) for ga, na in wa for gb, nb in wb):
            return "gender and given names differ"
        return _years_fit([r for r in ra if r[1] is not None], [r for r in rb if r[1] is not None],
                          early_ok, self._parents_agree)

    def union(self, a: str, b: str, edge_type: str) -> None:
        ra, rb = self.uf.find(a), self.uf.find(b)
        if ra == rb:
            return
        # every link is exact except the fuzzy-name round and the middle-name pass
        why = self._why_not(self.recs[ra], self.recs[rb], early_ok=edge_type not in _INEXACT_EDGES)
        if why:
            fmt = lambda recs: " ".join(sorted(f"{r[0]}:{r[1]}" for r in recs))
            self.refused.append((edge_type, why, a, b, fmt(self.recs[ra]), fmt(self.recs[rb])))
            return
        self.uf.union(a, b)
        root = self.uf.find(a)
        other = rb if root == ra else ra
        self.recs[root] = self.recs[root] + self.recs.pop(other)


def _cluster(nodes: dict, refs: dict, ncst24: pd.DataFrame, avanti: dict) -> pd.DataFrame:
    """Run the two-round union-find and return node_id → student_key. Every union goes
    through _CheckedUnion (one record per stage, years that fit)."""
    global _REFUSED
    all_nodes = pd.concat([nodes[s][["node_id"]] for s in STAGES], ignore_index=True)
    uf = _UnionFind(all_nodes.node_id.tolist())
    cu = _CheckedUnion(uf, nodes)

    def apply(edges, edge_type):
        edges = [(a, b) for a, b in edges if a in uf.parent and b in uf.parent]
        before = len(cu.refused)
        for a, b in edges:
            cu.union(a, b, edge_type)
        print(f"    {edge_type:<22}{len(edges):>9,} edges, {len(cu.refused) - before:>6,} refused")
        return edges

    # Round 0 — hard edges (deterministic + entrance same-person + DOB/parent), strongest first.
    hard = (apply(_deterministic_edges(nodes, refs, ncst24), "crosswalk / id")
            + apply(_entrance_edges(nodes), "entrance same-person")
            + apply(_parent_dob_edges(nodes), "DOB + parents"))
    print(f"  round-0 hard edges:     {len(hard):>8,}")

    # Round 1 — identity edges, ambiguity judged against round-0 components.
    comp = {n: uf.find(n) for n in uf.parent}
    soft = apply(_identity_edges(nodes, comp), "identity rules")
    print(f"  round-1 identity edges: {len(soft):>8,}")

    # Round 2 — fuzzy-name edges, last, through the same checks as every other union.
    _round2_fuzzy(cu, nodes, refs, ncst24, avanti)

    twin_rows = [("DOB + parents", "given names differ (twin check)", a, b, "", "")
                 for a, b in _TWIN_REFUSED]
    _REFUSED = pd.DataFrame(twin_rows + cu.refused,
                            columns=["edge_type", "reason", "node_a", "node_b",
                                     "student_a_records", "student_b_records"])
    if len(_REFUSED):
        print("  refused links: " + ", ".join(
            f"{r} {n:,}" for r, n in _REFUSED.reason.value_counts().items()))

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
    as the PRIMARY frame for everyone; only students avanti_g12 can't place at all
    fall back to avanti_all (see the g12-primary → wide-fallback cascade in
    _match_fk_v2). Those fallback students — the pre-grade-12 NCST/10th cohorts not
    in grade 12 yet — have no grade-12 id, so they carry no Foundation->TP dual id
    to be ambiguous against; the wide frame is simply the only one that can match
    them at all."""
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
            CAST(student_grade AS STRING) AS student_grade, {_GENDER('student_gender')} AS gender
        FROM `avantifellows.production_dbt_final.dim_student`  WHERE {filt}
        UNION ALL
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk_student_id,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS dob,
            {name} AS norm_name, {fname} AS norm_father,
            FORMAT_DATE('%Y-%m-%d', {swap}) AS dob_swapped,
            CAST(student_grade AS STRING) AS student_grade, {_GENDER('student_gender')} AS gender
        FROM `avantifellows.production_dbt_final.dim_student_historical` WHERE {filt}
    """
    avanti = client.query(sql).to_dataframe().drop_duplicates()
    avanti["norm_father"] = avanti["norm_father"].where(_present(avanti["norm_father"]))
    for c in avanti.columns:
        avanti[c] = _S(avanti[c])
    avanti["norm_name"] = avanti["norm_name"].map(_one_word_once).astype("string")
    avanti = avanti.drop_duplicates()

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


def _read_tie_facts(client) -> dict:
    """STEP 6b tie-breaker inputs (see _reconcile_shared_fk).
    avanti: Avanti id -> {"schools", "cohorts", "dobs", "fathers"} (sets), from dim_student
            (school code through dim_school) and dim_student_historical (school_code). The
            Avanti cohort is the academic year end + 12 - grade (the student's 12th year).
    school: 10th / 12th node id -> the board school code."""
    fname = r"UPPER(TRIM(REGEXP_REPLACE(COALESCE(s.father_name,''), r'\s+', ' ')))"
    cohort = ("SAFE_CAST(SUBSTR(CAST(s.academic_year AS STRING), 6, 4) AS INT64) + 12"
              " - SAFE_CAST(s.student_grade AS INT64)")
    av = client.query(f"""
        SELECT COALESCE(s.pk_student_id, s.apaar_id) AS fk, CAST(sc.school_code AS STRING) AS school,
               {cohort} AS cohort, FORMAT_DATE('%Y-%m-%d', DATE(s.date_of_birth)) AS dob, {fname} AS father
        FROM `avantifellows.production_dbt_final.dim_student` s
        LEFT JOIN `avantifellows.production_dbt_final.dim_school` sc ON sc.pk_school_id = s.fk_school_id
        WHERE COALESCE(s.pk_student_id, s.apaar_id) IS NOT NULL
        UNION ALL
        SELECT COALESCE(s.pk_student_id, s.apaar_id), CAST(s.school_code AS STRING),
               {cohort}, FORMAT_DATE('%Y-%m-%d', DATE(s.date_of_birth)), {fname}
        FROM `avantifellows.production_dbt_final.dim_student_historical` s
        WHERE COALESCE(s.pk_student_id, s.apaar_id) IS NOT NULL""").to_dataframe()
    avanti = {}
    for fk, school, coh, dob, father in av.itertuples(index=False, name=None):
        a = avanti.setdefault(str(fk), {"schools": set(), "cohorts": set(), "dobs": set(), "fathers": set()})
        if isinstance(school, str) and school.strip():
            a["schools"].add(school.strip())
        if pd.notna(coh):
            a["cohorts"].add(int(coh))
        if isinstance(dob, str) and dob:
            a["dobs"].add(dob)
        if isinstance(father, str) and father:
            a["fathers"].add(father)
    ext = f"{BQ_PROJECT}.{BQ_DATASET}"
    sch = client.query(f"""
        SELECT CONCAT('b10:', CAST(exam_year AS STRING), ':', roll_number) AS node_id,
               ANY_VALUE(CAST(school_code AS STRING)) AS school
        FROM `{ext}.jnv_fact_board_results_10th` GROUP BY 1
        UNION ALL
        SELECT CONCAT('b12:', CAST(exam_year AS STRING), ':', roll_number),
               ANY_VALUE(CAST(school_code AS STRING))
        FROM `{ext}.jnv_fact_board_results_12th` GROUP BY 1""").to_dataframe()
    school = {n: s.strip() for n, s in zip(sch.node_id, sch.school) if isinstance(s, str) and s.strip()}
    print(f"  tie-breaker facts: {len(avanti):,} Avanti ids, {len(school):,} board records with a school code")
    return {"avanti": avanti, "school": school}


def _student_facts(nodes: dict, n2k: pd.Series, tie: dict) -> dict:
    """student_key -> the facts that the tie-breakers score (_tie_points): "schools" (10th / 12th
    school codes), "cohort" (12th year, else 10th or NCST year + 2, else the first JEE / NEET
    year), "dobs" and "fathers" (of every record)."""
    k_of = n2k.to_dict()
    f = {}
    for st in STAGES:
        df = nodes[st]
        yrs = pd.to_numeric(df.yr, errors="coerce")
        for n, y, d, fa in zip(df.node_id, yrs, df.dob, df.norm_father):
            k = k_of.get(n)
            if k is None:
                continue
            x = f.setdefault(k, {"schools": set(), "pre": set(), "ent": set(), "dobs": set(), "fathers": set()})
            sc = tie["school"].get(n)
            if sc:
                x["schools"].add(sc)
            if pd.notna(y):
                (x["ent"] if st in ("jee", "neet") else x["pre"]).add(int(y) + (0 if st in ("b12", "jee", "neet") else 2))
            if isinstance(d, str) and d:
                x["dobs"].add(d)
            if isinstance(fa, str) and fa:
                x["fathers"].add(fa)
    for x in f.values():
        x["cohort"] = min(x["pre"]) if x["pre"] else (min(x["ent"]) if x["ent"] else None)
    return f


def _tie_points(f: dict | None, av: dict | None) -> dict:
    """The tie-breaker points of a student (facts f, _student_facts) against an Avanti student
    (av, _read_tie_facts): school, cohort, DOB and father, 1 each."""
    if f is None or av is None:
        return {"school": 0, "cohort": 0, "dob": 0, "father": 0}
    return {
        "school": int(bool(f["schools"] & av["schools"])),
        "cohort": int(f["cohort"] is not None and f["cohort"] in av["cohorts"]),
        "dob": int(bool(f["dobs"] & av["dobs"])),
        "father": int(any(nd.father_check_v2(a, b, _FUZZY_OPTS) in FUZZY_FATHER_OK
                          for a in f["fathers"] for b in av["fathers"])),
    }


def _pick_by_points(f: dict | None, ids: list, tie: dict | None):
    """Of 2+ Avanti ids, the one with the most _tie_points; None when the top score is shared
    or zero."""
    if tie is None or f is None:
        return None
    pts = [sum(_tie_points(f, tie["avanti"].get(str(i))).values()) for i in ids]
    top = max(pts)
    return ids[pts.index(top)] if top > 0 and pts.count(top) == 1 else None


def _read_dim_passthrough(client) -> pd.DataFrame:
    """Grade-12 JNV `dim_student` students, to seed the ones with NO exam/board/NCST
    record as size-1 'dim-only' rows — roster completeness for enrolled students whose
    outcomes are not in our exam data (NVS/Enable content-only programs, CLAT/CUET/CA
    aspirants, not-yet-sat). Same school-JNV + grade-12 universe as _read_avanti_reference
    so 'already resolved' compares apples-to-apples. `_build_rows` keeps a row ONLY if it
    is neither fk-resolved NOR identity-present (name+dob) in the graph, so a matched or
    matchable (recall-miss) student is never re-created as a phantom dim-only duplicate.
    Scope note: current-snapshot AYs 2024-25/2025-26 (cohorts 2025/2026 — the validated
    dim-only window); extend `years` to add the incoming 2026-27 cohort or historical AYs."""
    name = r"UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\s+', ' ')))"
    fname = r"UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\s+', ' ')))"
    mname = r"UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\s+', ' ')))"
    years = "'2024-2025','2025-2026'"
    filt = (f"(LOWER(COALESCE(student_school,'')) LIKE '%jnv%'"
            f" OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')"
            f" AND CAST(student_grade AS STRING) = '12'"
            f" AND academic_year IN ({years})"
            f" AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL")
    sql = f"""
        SELECT DISTINCT
            COALESCE(pk_student_id, apaar_id) AS fk_avanti_student_id,
            {name} AS student_name, {fname} AS father_name, {mname} AS mother_name,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS student_dob,
            {_GENDER('student_gender')} AS student_gender,
            student_program, student_product,
            CAST(SUBSTR(CAST(academic_year AS STRING), 6, 4) AS INT64) AS cohort_year
        FROM `avantifellows.production_dbt_final.dim_student`
        WHERE {filt}
    """
    df = client.query(sql).to_dataframe()
    for c in df.columns:
        df[c] = _S(df[c])
    df["father_name"] = df.father_name.where(_present(df.father_name))
    df["mother_name"] = df.mother_name.where(_present(df.mother_name))
    df["student_gender"] = df.student_gender.where(_present(df.student_gender))
    df["cohort_year"] = pd.to_numeric(df.cohort_year, errors="coerce").astype("Int64")
    df = df[_present(df.fk_avanti_student_id) & _present(df.student_dob)]
    # a grade-12 repeater can appear in both AYs — keep the later cohort
    return df.sort_values("cohort_year").drop_duplicates("fk_avanti_student_id", keep="last")


_COALESCE_NAME_ORDER = ["b12", "b10", "jee", "neet", "ncst"]
_COALESCE_DOB_ORDER = ["b10", "jee", "neet", "ncst"]   # 12th board carries no usable DOB (verified empty)
_COALESCE_FATHER_ORDER = ["b12", "b10", "jee", "neet", "ncst"]
_COALESCE_MOTHER_ORDER = ["b12", "b10", "jee", "neet", "ncst"]
_COALESCE_GENDER_ORDER = ["b12", "b10", "jee", "neet", "ncst"]


def _coalesce_by_source(contrib: pd.DataFrame, col: str, order: list) -> pd.Series:
    """Per student_key, take `col` from the first source in `order` that has a
    present value. Ported from v1's identically-named helper (secondary sort on
    node_id added for determinism when a student has >1 node in the same stage)."""
    rank = {s: i for i, s in enumerate(order)}
    d = contrib[contrib.src.isin(order) & _present(contrib[col])].copy()
    d["r"] = d.src.map(rank)
    d = d.sort_values(["student_key", "r", "node_id"]).drop_duplicates("student_key", keep="first")
    return d.set_index("student_key")[col]


def _build_sid(nodes: dict, n2k: pd.Series, refs: dict, ncst24: pd.DataFrame,
               prod_nta: dict) -> pd.DataFrame:
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
        df = nodes[stage][["node_id", "norm_name", "norm_father", "norm_mother", "dob", "gender"]].copy()
        df["student_key"] = df.node_id.map(n2k)
        df["src"] = stage
        return df.dropna(subset=["student_key"])

    contrib = pd.concat([assign(s) for s in ("b12", "b10", "jee", "neet", "ncst")], ignore_index=True)
    keys = pd.Index(contrib.student_key.unique(), name="student_key")
    sid = pd.DataFrame(index=keys)
    sid["norm_name"] = _coalesce_by_source(contrib, "norm_name", _COALESCE_NAME_ORDER)
    sid["dob"] = _coalesce_by_source(contrib, "dob", _COALESCE_DOB_ORDER)
    sid["norm_father"] = _coalesce_by_source(contrib, "norm_father", _COALESCE_FATHER_ORDER)
    sid["norm_mother"] = _coalesce_by_source(contrib, "norm_mother", _COALESCE_MOTHER_ORDER)
    # gender: the one gender of the student's records; NA when they have none or both
    g = contrib.loc[_present(contrib.gender), ["student_key", "gender"]].drop_duplicates()
    sid["gender"] = g.drop_duplicates("student_key", keep=False).set_index("student_key").gender
    # student_gender: the output column. It takes the first source that has a gender, in the
    # same order as the name, so a student with two different genders still gets a value.
    # The gender check of step 6 uses `gender` above, not this column.
    sid["student_gender"] = _coalesce_by_source(contrib, "gender", _COALESCE_GENDER_ORDER)
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

    # Production NTA app→id — FILL-ONLY, the LOWEST tier of all (see _match_fk_v2 tier 8
    # and _read_prod_nta_crosswalk for the evidence). Kept in its OWN column rather than
    # folded into `direct` above for the same reason roll10_avanti_id is: it must never
    # override a name/dob match. It is nonetheless the ONLY key that reaches the nameless
    # JEE-2025 rows (8,066 of 12,103 carry no name/dob/father ⇒ invisible to every other
    # tier), which is the whole point of adding it.
    ptag = []
    for st in ("jee", "neet"):
        px = prod_nta.get(st)
        if px is None or px.empty:
            continue
        t = nodes[st].merge(px, on=["yr_s", "app"], how="inner")[["node_id", "avanti_id"]].copy()
        t["student_key"], t["src"] = t.node_id.map(n2k), st
        ptag.append(t)
    if ptag:
        pt = pd.concat(ptag, ignore_index=True).dropna(subset=["student_key"])
        pt = pt[_present(pt.avanti_id)]
        sid = sid.merge(_coalesce_by_source(pt, "avanti_id", ["jee", "neet"])
                        .rename("prod_nta_avanti_id"), on="student_key", how="left")
    else:
        sid["prod_nta_avanti_id"] = pd.Series(pd.NA, index=sid.index, dtype="string")

    # Frame routing (grade-12 vs the wider all-grade avanti reference) is decided in
    # _match_fk_v2 by a g12-primary → wide-fallback cascade, so no per-cluster source
    # classification is needed here. (Earlier revisions precomputed an ncst_only /
    # pre_g12 flag to partition the two frames up front; the fallback subsumes it —
    # a student is sent to the wide frame iff grade-12 can't place them at all.)
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


# ── STEP 6 record pass ────────────────────────────────────────────────────────
# _match_fk_v2 matches ONE resolved identity per student (name 12th > 10th > JEE > NEET >
# NCST; DOB 10th > JEE > NEET > NCST). When that identity takes the name or DOB of one
# record, another record of the same student can hold the name and DOB that dim_student
# has, and the student stays without an Avanti id. The record pass fixes that, FILL-ONLY:
#   • only students with no candidate at all from the resolved identity (not 'ambiguous');
#   • each record's own name, DOB and father, on the exact tiers only: name + DOB,
#     name + DOB swapped, name + father (not the DOB-blocked strong/fuzzy name tiers);
#   • grade-12 frame first, the all-grade frame for students it does not place;
#   • one Avanti id across all the student's record matches, or nothing ('ambiguous').
# Its tiers rank below every existing tier (_CONF_PRI), so in step 6b a student that
# already holds an id always beats a record-pass claimant.
_RECORD_TIERS = {"record_name_dob": 9, "record_name_dob_swapped": 10, "record_name_father": 11}


def _record_identities(nodes: dict, n2k: pd.Series) -> pd.DataFrame:
    """One row per source record: its own name, DOB and father, with its student_key."""
    parts = []
    for st in STAGES:
        df = nodes[st][["node_id", "norm_name", "norm_father", "dob", "gender"]].copy()
        df["student_key"] = df.node_id.map(n2k)
        parts.append(df.dropna(subset=["student_key"]))
    return pd.concat(parts, ignore_index=True)


def _record_candidates(r: pd.DataFrame, avanti: pd.DataFrame) -> pd.DataFrame:
    """Exact tiers on each record's own identity. One row per (student_key, Avanti id, tier)."""
    cols = ["student_key", "pk_student_id", "conf"]
    rd = r[_present(r.norm_name) & _present(r.dob)]
    a = rd.merge(avanti[["pk_student_id", "norm_name", "dob"]], on=["norm_name", "dob"])
    b = rd.merge(avanti.loc[_present(avanti.dob_swapped), ["pk_student_id", "norm_name", "dob_swapped"]],
                 left_on=["norm_name", "dob"], right_on=["norm_name", "dob_swapped"])
    rf = r[_present(r.norm_name) & _present(r.norm_father)]
    c = rf.merge(avanti.loc[_present(avanti.norm_father), ["pk_student_id", "norm_name", "norm_father"]],
                 on=["norm_name", "norm_father"])
    return pd.concat([a.assign(conf="record_name_dob")[cols],
                      b.assign(conf="record_name_dob_swapped")[cols],
                      c.assign(conf="record_name_father")[cols]], ignore_index=True)


# ── STEP 6 strong record pass ─────────────────────────────────────────────────
# Fill-only, last, for students that still have no candidate at all after the record pass
# and the school pass. A student's identity takes the name of one record. When that name has
# fewer words than the dim_student name ('PATEL KIRANBHAI', dim_student 'PATEL KIRAN
# NARESHBHAI'), the strong name tier fails, but another record of the student ('PATEL
# KIRANBHAI NARESHBHAI') can match. This pass takes each record's own name and DOB:
#   • the DOB is the Avanti DOB, and the names pass the strong name test (_am_strong_ok);
#   • the first name word of one name is in the other name (_first_word_ok): names that
#     share only the middle and last words ('AMIT PRATAP SINGH', 'VIVEK PRATAP SINGH') are
#     two people;
#   • the gender check (_gender_conflict) does not say two people;
#   • when the student has a 10th or 12th school code and the Avanti student has a board school
#     code, one of them agrees (a common name and a DOB alone can be another student);
#   • grade-12 frame first, the all-grade frame for students it does not place;
#   • one Avanti id, or the forward tie-breaker for two or more.
_STRONG_RECORD_TIERS = {"record_name_dob_strong": 13}


def _first_word_ok(a, b) -> bool:
    """True when the first name word (3 or more letters) of one name is a word of the other
    name, or a close spelling or a prefix of one ('KAVITA' ~ 'KAVITHA', 'ROHAN' ~
    'ROHANBHAI')."""
    ta = [t for t in re.split(r"[^A-Za-z]+", str(a).upper()) if len(t) > 2]
    tb = [t for t in re.split(r"[^A-Za-z]+", str(b).upper()) if len(t) > 2]

    def close(x, y):
        return (x == y or nd._word_match(x, y) == "word"
                or (min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x))))
    return bool(ta and tb) and (any(close(ta[0], y) for y in tb) or any(close(tb[0], x) for x in ta))


def _record_strong_candidates(r: pd.DataFrame, avanti: pd.DataFrame, tie: dict | None) -> pd.DataFrame:
    """The strong record pass tests on each record's own name and DOB. One row per
    (student_key, Avanti id, tier)."""
    cols = ["student_key", "pk_student_id", "conf"]
    rd = r[_present(r.norm_name) & _present(r.dob)]
    m = rd.merge(avanti.loc[_present(avanti.dob), ["pk_student_id", "norm_name", "dob", "gender"]],
                 on="dob", suffixes=("", "_av"))
    if len(m):   # a list mask on an empty frame drops its columns
        m = m[[_am_strong_ok(n, a) and _first_word_ok(n, a) and not _gender_conflict(g, n, ga, a)
               for n, a, g, ga in zip(m.norm_name, m.norm_name_av, m.gender, m.gender_av)]]
    if len(m) and tie is not None:
        # school veto: the student's 10th/12th school codes and the Avanti board school codes, when
        # both are known, must have one in common. Only Avanti codes that are 10th/12th board
        # codes count: dim_student_historical has codes of another kind, which never agree.
        b = r[r.node_id.str.match(r"b1[02]:")]
        own = b.assign(school=b.node_id.map(tie["school"])).dropna(subset=["school"])
        own = own.groupby("student_key").school.agg(set).to_dict()
        board = set(tie["school"].values())
        av = {fk: a["schools"] & board for fk, a in tie["avanti"].items() if a["schools"] & board}
        m = m[[not (own.get(k) and av.get(str(fk))) or bool(own[k] & av[str(fk)])
               for k, fk in zip(m.student_key, m.pk_student_id)]]
    return m.assign(conf="record_name_dob_strong")[cols]


def _strong_record_pass(rec: pd.DataFrame, blank: set, avanti_g12: pd.DataFrame,
                        avanti_all: pd.DataFrame, tie: dict | None, pick=None) -> pd.DataFrame:
    """Match the students in `blank` with the strong record pass tests. Returns rows in the
    _match_fk_v2 output shape."""
    r = rec[rec.student_key.isin(blank)]
    g12 = _record_strong_candidates(r, avanti_g12, tie)
    wide = _record_strong_candidates(r[~r.student_key.isin(set(g12.student_key))], avanti_all, tie)
    cand = pd.concat([g12, wide], ignore_index=True).drop_duplicates()
    return _settle_candidates(cand, _STRONG_RECORD_TIERS, pick)


def _settle_candidates(cand: pd.DataFrame, tiers: dict, pick) -> pd.DataFrame:
    """Candidate rows (student_key, pk_student_id, conf) -> one row per student in the
    _match_fk_v2 output shape. One Avanti id -> filled (its best tier); two or more -> the
    forward tie-breaker pick(student_key, ids), else 'ambiguous'. match_count = the ids."""
    out_cols = ["student_key", "fk_avanti_student_id", "match_confidence", "match_count"]
    if cand.empty:
        return pd.DataFrame(columns=out_cols)
    cand = cand.assign(pri=cand.conf.map(tiers))
    best = (cand.sort_values(["student_key", "pk_student_id", "pri"])
                .drop_duplicates(["student_key", "pk_student_id"]).set_index(["student_key", "pk_student_id"]).conf)
    ids = cand.groupby("student_key")["pk_student_id"].agg(lambda x: sorted(set(x)))
    rows = []
    for k, v in ids.items():
        fk = v[0] if len(v) == 1 else (pick(k, v) if pick is not None else None)
        rows.append((k, fk if fk is not None else pd.NA,
                     best[(k, fk)] if fk is not None else "ambiguous", len(v)))
    return pd.DataFrame(rows, columns=out_cols)


def _record_pass(rec: pd.DataFrame, blank: set, avanti_g12: pd.DataFrame,
                 avanti_all: pd.DataFrame, pick=None) -> pd.DataFrame:
    """Match the students in `blank` on each record's own identity. Returns rows in the
    _match_fk_v2 output shape: one Avanti id -> filled; two or more -> the forward
    tie-breaker (pick), else 'ambiguous'."""
    r = rec[rec.student_key.isin(blank)]
    g12 = _record_candidates(r, avanti_g12)
    wide = _record_candidates(r[~r.student_key.isin(set(g12.student_key))], avanti_all)
    cand = pd.concat([g12, wide], ignore_index=True).drop_duplicates()
    return _settle_candidates(cand, _RECORD_TIERS, pick)


# ── STEP 6 school pass ────────────────────────────────────────────────────────
# Fill-only, after the record pass, for students that still have no candidate at all. A 10th
# or 12th record often has the given name only (HIMANSHI) where dim_student has the full name
# (HIMANSHI BISHNOI), so no name tier matches. A given name and a DOB alone are not enough
# (other students in India share them), so the school code must agree too:
#   • the record DOB is the Avanti DOB, and the record's board school code is an Avanti school;
#   • the name words of the shorter name are all in the other name (_name_part_ok);
#   • the gender check (_gender_conflict) does not say two people;
#   • one Avanti id, or the forward tie-breaker for two or more.
_SCHOOL_TIERS = {"name_part_dob_school": 12}


def _name_part_ok(a, b) -> bool:
    """True when the name words (3+ letters) of the shorter name are all in the longer name, and
    one of them is not a common filler word (KUMAR, SINGH, ...)."""
    if not (isinstance(a, str) and isinstance(b, str)):
        return False
    ta, tb = _am_strong_tokens(a), _am_strong_tokens(b)
    short, long = sorted((ta, tb), key=len)
    return short <= long and bool({nd.normalise(t) for t in short} - nd.FILLERS)


def _school_pass(rec: pd.DataFrame, blank: set, avanti_all: pd.DataFrame, tie: dict,
                 pick=None) -> pd.DataFrame:
    """Match the students in `blank` on a 10th / 12th record's DOB, school code and name part."""
    r = rec[rec.student_key.isin(blank) & rec.node_id.str.match(r"b1[02]:")
            & _present(rec.dob) & _present(rec.norm_name)].copy()
    r["school"] = r.node_id.map(tie["school"])
    r = r[_present(r.school)]
    sch = pd.DataFrame([(fk, sc) for fk, a in tie["avanti"].items() for sc in a["schools"]],
                       columns=["pk_student_id", "school"])
    av = avanti_all[["pk_student_id", "norm_name", "dob", "gender"]].drop_duplicates().merge(sch, on="pk_student_id")
    m = r.merge(av, on=["dob", "school"], suffixes=("", "_av"))
    if len(m):
        m = m[[_name_part_ok(a, b) and not _gender_conflict(g, a, ga, b)
               for a, b, g, ga in zip(m.norm_name, m.norm_name_av, m.gender, m.gender_av)]]
    cand = m.assign(conf="name_part_dob_school")[["student_key", "pk_student_id", "conf"]].drop_duplicates()
    return _settle_candidates(cand, _SCHOOL_TIERS, pick)


def _match_fk_v2(sid: pd.DataFrame, avanti_g12: pd.DataFrame, avanti_all: pd.DataFrame,
                 all_ids: set, rec: pd.DataFrame = None, tie: dict | None = None,
                 facts: dict | None = None) -> pd.DataFrame:
    """Tiered Avanti fk match — ported from v1's _match_fk, run against v2's OWN
    `sid` (STEP 6, replacing the source-table passthrough) for ALL students
    (b10/b12/jee/neet AND ncst — one unified pipeline, see _build_sid). Priority
    (lowest wins): direct id -> name+dob -> name+dob swapped -> name+father exact
    (no DOB needed — the fallback that reaches DOB-less NCST 2023/2024) ->
    DOB-blocked strong name -> DOB-blocked fuzzy name (last resort) -> 10th-score
    crosswalk id (fill-only). Ambiguous (>1 distinct candidate) is withheld
    (fk=NULL), matching this build's precision-first posture throughout.

    Forward tie-breaker: when a tier matches the student to 2+ Avanti ids (often one person
    with two dim_student ids, enrolled again under a new id), the one id with the most
    _tie_points (school, cohort, DOB, father; `tie` and `facts`) gets it, with match_count =
    the number of ids. A shared or zero top score stays 'ambiguous'. A pick is a last resort:
    a unique match on any tier comes first, and in step 6b a pick ranks below every unique
    match.

    Gender check (_gender_conflict) on the tiers that do not need equal names: direct id,
    strong name, fuzzy name and the two crosswalk ids drop an Avanti student whose gender and
    given names both differ from the student's. In the strong and fuzzy tiers this is done
    before the count, so a twin of the other gender does not make the match ambiguous.

    Runs the SAME cascade against two candidate pools in a g12-primary →
    wide-fallback order, not two independent resolvers: EVERYONE is matched against
    avanti_g12 first, and only students that frame places nowhere (no candidate row
    — the pre-grade-12 NCST/10th cohorts not in grade 12 yet) fall back to
    avanti_all. This lets those young cohorts match at all while keeping students
    who DO sit in the g12 frame there — matching the WHOLE population against
    avanti_all was tried and reverted (it turned Foundation->TP re-enrollment id
    pairs into false ambiguity for students that were matching cleanly), and the
    fallback confines avanti_all to exactly the students g12 can't place, who by
    construction have no grade-12 id to be ambiguous against."""
    cand_cols = ["student_key", "fk", "pri", "conf", "cnt"]

    def pick(k, ids):
        return _pick_by_points(facts.get(k) if facts is not None else None, ids, tie)

    def _settle(m: pd.DataFrame, pri: int, conf: str) -> pd.DataFrame:
        """Candidate rows (student_key, pk_student_id) -> one row per student: one id, or
        the forward tie-breaker for 2+ ids (else fk NA); cnt = the number of ids."""
        if m.empty:
            return pd.DataFrame(columns=cand_cols)
        ids = m.groupby("student_key")["pk_student_id"].agg(lambda x: sorted(set(x)))
        fks = [v[0] if len(v) == 1 else pick(k, v) for k, v in ids.items()]
        return pd.DataFrame({"student_key": ids.index, "fk": [pd.NA if f is None else f for f in fks],
                             "pri": pri, "conf": conf, "cnt": [len(v) for v in ids]})

    # pk -> {dim_student JNV names} — used ONLY to name-gate the direct-id tier
    # below. Built from avanti_all (broadest JNV frame) so a direct id whose only
    # dim_student rows are pre-grade-12 is still checkable.
    name_by_pk = (avanti_all.loc[_present(avanti_all.norm_name)]
                  .groupby("pk_student_id")["norm_name"].agg(set).to_dict())
    # pk -> its one gender (NA when dim_student has none or both), for the gender check
    gp = avanti_all.loc[_present(avanti_all.gender), ["pk_student_id", "gender"]].drop_duplicates()
    gender_by_pk = gp.drop_duplicates("pk_student_id", keep=False).set_index("pk_student_id").gender.to_dict()

    def _two_people(gender, rec_name, fk) -> bool:
        """Gender check (_gender_conflict) of a student against the Avanti student fk, on
        every name dim_student has for fk. Used on the tiers that do not need equal names."""
        names = name_by_pk.get(fk)
        return bool(names) and all(_gender_conflict(gender, rec_name, gender_by_pk.get(fk), n) for n in names)

    def _direct_ok(rec_name, fk) -> bool:
        """Keep a direct crosswalk id only if the student it points to actually
        carries the record's name. Catches ROW-MISALIGNED app->id / roll->id
        crosswalks (the #1/#6/#9 lesson, on the direct-id direction): a misaligned
        row hands back a real-but-WRONG id, and because direct id is the top tier
        it would otherwise override the correct name+dob match. Fallback = keep:
        if the candidate id is not in the JNV name frame (a legitimately non-JNV
        label) or the record has no name, we can't verify — preserve it rather
        than regress. Rejected ids fall through to the name+dob tiers below.

        The NA check must come BEFORE any truthiness test on rec_name: `not pd.NA`
        raises TypeError, and the prod_nta tier feeds this exactly the nameless rows
        (a name-less record is the "can't verify -> keep" case)."""
        cand = name_by_pk.get(fk)
        if not cand:
            return True
        if rec_name is None or pd.isna(rec_name) or not str(rec_name):
            return True
        return any(_name_agree(rec_name, cn) for cn in cand)

    def _match_one(sid, avanti):
        d0 = sid[_present(sid.source_avanti_student_id) & sid.source_avanti_student_id.isin(all_ids)]
        if len(d0):   # a list mask on an empty frame drops its columns (see the prod_nta tier)
            d0 = d0[[_direct_ok(n, f) and not _two_people(g, n, f)
                     for n, f, g in zip(d0.norm_name, d0.source_avanti_student_id, d0.gender)]]
        direct = pd.DataFrame({"student_key": d0.student_key, "fk": d0.source_avanti_student_id,
                               "pri": 1, "conf": "direct_student_id", "cnt": 1})

        def _name_match(right_dob_col, pri, conf):
            m = sid[sid.norm_name.notna() & sid.dob.notna()].merge(
                avanti[["pk_student_id", "norm_name", right_dob_col]],
                left_on=["norm_name", "dob"], right_on=["norm_name", right_dob_col])
            return _settle(m, pri, conf)

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
            return _settle(m, 4, "name_father")

        def _blocked_match(pred, pri, conf, already):
            cs = sid[sid.norm_name.notna() & sid.dob.notna() & ~sid.student_key.isin(already)]
            mm = cs.merge(avanti[["pk_student_id", "norm_name", "dob", "gender"]], on="dob", suffixes=("", "_av"))
            if len(mm):
                mm = mm[[pred(n, a) and not _gender_conflict(g, n, ga, a)
                         for n, a, g, ga in zip(mm.norm_name, mm.norm_name_av, mm.gender, mm.gender_av)]]
            return _settle(mm, pri, conf)

        # resolved = one Avanti id; a forward tie-breaker pick still lets the lower tiers try
        # for a unique match, which comes first (see the final selection below)
        def _unique(d):
            return set(d.loc[d.fk.notna() & (pd.to_numeric(d.cnt, errors="coerce") == 1), "student_key"])
        resolved = _unique(pd.concat([direct, nd, nds]))
        nf = _father_match(resolved)
        resolved = resolved | _unique(nf)
        st = _blocked_match(_am_strong_ok, 5, "name_dob_strong", resolved)
        resolved = resolved | _unique(st)
        fz = _blocked_match(_am_fuzzy_ok, 6, "name_dob_fuzzy", resolved)

        x10 = pd.DataFrame(columns=cand_cols)
        if "roll10_avanti_id" in sid:
            xr = sid[_present(sid.roll10_avanti_id) & sid.roll10_avanti_id.isin(all_ids)]
            if len(xr):
                xr = xr[[not _two_people(g, n, f) for n, f, g in zip(xr.norm_name, xr.roll10_avanti_id, xr.gender)]]
            x10 = pd.DataFrame({"student_key": xr.student_key, "fk": xr.roll10_avanti_id,
                                "pri": 7, "conf": "roll10_crosswalk", "cnt": 1})

        # tier 8 — production NTA app→id (see _read_prod_nta_crosswalk). LAST on purpose:
        # where it conflicts with a name/dob match the two are a statistical near-tie, so
        # it may only fill a blank. Name-gated by _direct_ok exactly like the direct tier
        # (a no-op for the nameless rows this reaches — nothing to contradict — but it
        # still vetoes a candidate whose name IS visible and disagrees).
        xp = pd.DataFrame(columns=cand_cols)
        if "prod_nta_avanti_id" in sid:
            xr = sid[_present(sid.prod_nta_avanti_id) & sid.prod_nta_avanti_id.isin(all_ids)]
            # `len(xr)` guard: a list-comprehension mask on an EMPTY frame is `[]`, which
            # pandas reads as "select zero columns" rather than "keep zero rows", so the
            # frame loses its columns and the construction below raises. Empty is a real
            # case (no production rows for these apps / crosswalk unavailable).
            if len(xr):
                xr = xr[[_direct_ok(n, f) and not _two_people(g, n, f)
                         for n, f, g in zip(xr.norm_name, xr.prod_nta_avanti_id, xr.gender)]]
            if len(xr):
                xp = pd.DataFrame({"student_key": xr.student_key, "fk": xr.prod_nta_avanti_id,
                                   "pri": _PROD_NTA_PRI, "conf": "prod_nta_crosswalk", "cnt": 1})

        return pd.concat([direct[cand_cols], nd[cand_cols], nds[cand_cols], nf[cand_cols],
                          st[cand_cols], fz[cand_cols], x10[cand_cols], xp[cand_cols]],
                         ignore_index=True)

    # g12-primary → wide-fallback: match EVERYONE against the safer grade-12 frame
    # first; only students that frame can't place at all (no candidate row — the
    # young NCST/10th cohorts not in grade 12 yet) fall back to the wider all-grade
    # reference. Students who DO sit in the g12 frame (incl. dual-pk NVS/Enable
    # re-enrollees, who match their single grade-12 id there) stay on g12, so the
    # Foundation->TP false ambiguity the wide frame induces never fires for them;
    # the fallback students have no grade-12 id to be ambiguous against.
    # The prod_nta tier is EXCLUDED from "did the g12 frame place them": unlike the
    # name/dob tiers it never consults `avanti` at all (it validates against all_ids), so
    # it returns the SAME candidate in both passes and is no evidence either way. Counting
    # it suppressed the wide-frame fallback for students who only match there, measured as
    # 20 existing fks being overwritten (name_dob 10, name_dob_strong 9, name_dob_fuzzy 1)
    # and 11 becoming NULL — a fill-only violation. (The direct and roll10 tiers are
    # frame-independent in the same way and ARE still counted here; left as-is
    # deliberately, to keep this change scoped to the one tier being added.)
    g12_cand = _match_one(sid, avanti_g12)
    seen_g12 = set(g12_cand.loc[g12_cand.pri != _PROD_NTA_PRI, "student_key"])
    sid_fallback = sid[~sid.student_key.isin(seen_g12)]
    wide_cand = _match_one(sid_fallback, avanti_all)
    cand = pd.concat([g12_cand, wide_cand], ignore_index=True)

    cand["fk_isnull"] = cand.fk.isna()
    # a unique match on any tier comes before a forward tie-breaker pick (a last resort)
    cand["picked"] = cand.fk.notna() & (pd.to_numeric(cand.cnt, errors="coerce") > 1)
    cand = (cand.sort_values(["student_key", "fk_isnull", "picked", "pri"])
                .drop_duplicates("student_key", keep="first"))
    cand["match_confidence"] = cand.conf.where(cand.fk.notna(),
                                               other=pd.Series("ambiguous", index=cand.index).where(cand.cnt > 1))
    out = cand.rename(columns={"fk": "fk_avanti_student_id", "cnt": "match_count"})[
        ["student_key", "fk_avanti_student_id", "match_confidence", "match_count"]]
    print(f"  step 6 (own matcher) — avanti fk: {out.fk_avanti_student_id.notna().sum():,} resolved, "
          f"{(out.match_confidence == 'ambiguous').sum():,} ambiguous "
          f"({sid_fallback.student_key.nunique():,} students unplaced by g12 fell back to the wide reference)")

    if rec is not None:
        # record pass — fill-only, for students with no candidate at all (see _RECORD_TIERS)
        known = set(out.loc[out.fk_avanti_student_id.notna() | out.match_confidence.notna(), "student_key"])
        blank = set(sid.student_key) - known
        rp = _record_pass(rec, blank, avanti_g12, avanti_all, pick)
        out = pd.concat([out[~out.student_key.isin(set(rp.student_key))], rp], ignore_index=True)
        tiers = rp.match_confidence.value_counts()
        print(f"  step 6 record pass (fill-only) — {rp.fk_avanti_student_id.notna().sum():,} filled ("
              + ", ".join(f"{t} {int(tiers.get(t, 0)):,}" for t in _RECORD_TIERS)
              + f"), {int(tiers.get('ambiguous', 0)):,} withheld (records point to 2+ Avanti students)")
        if tie is not None:
            # school pass — fill-only, for students that still have no candidate (see _SCHOOL_TIERS)
            sp = _school_pass(rec, blank - set(rp.student_key), avanti_all, tie, pick)
            out = pd.concat([out[~out.student_key.isin(set(sp.student_key))], sp], ignore_index=True)
            print(f"  step 6 school pass (fill-only) — {sp.fk_avanti_student_id.notna().sum():,} filled, "
                  f"{(sp.match_confidence == 'ambiguous').sum():,} withheld (2+ Avanti students)")
            # strong record pass — fill-only, last, for students that still have no candidate
            gp = _strong_record_pass(rec, blank - set(rp.student_key) - set(sp.student_key),
                                     avanti_g12, avanti_all, tie, pick)
            out = pd.concat([out[~out.student_key.isin(set(gp.student_key))], gp], ignore_index=True)
            print(f"  step 6 strong record pass (fill-only) — {gp.fk_avanti_student_id.notna().sum():,} filled, "
                  f"{(gp.match_confidence == 'ambiguous').sum():,} withheld (2+ Avanti students)")
    n_pick = int((out.fk_avanti_student_id.notna() & (pd.to_numeric(out.match_count, errors="coerce") > 1)).sum())
    print(f"  step 6 forward tie-breaker — {n_pick:,} students got one of 2+ Avanti ids, "
          f"{(out.match_confidence == 'ambiguous').sum():,} stay ambiguous")
    return out


# Tier order of _match_fk_v2's match_confidence values, best first — used to rank
# the claimants of one Avanti id in _reconcile_shared_fk. The record-pass and school-pass tiers rank last.
_CONF_PRI = {"direct_student_id": 1, "name_dob": 2, "name_dob_swapped": 3, "name_father": 4,
             "name_dob_strong": 5, "name_dob_fuzzy": 6, "roll10_crosswalk": 7,
             "prod_nta_crosswalk": _PROD_NTA_PRI, **_RECORD_TIERS, **_SCHOOL_TIERS, **_STRONG_RECORD_TIERS}


_TIES = None   # scratch run: the 6b ties and their points (written to <out_table>_ties)


def _reconcile_shared_fk(nodes: dict, key: pd.DataFrame, fk_df: pd.DataFrame,
                         tie: dict | None = None) -> tuple:
    """STEP 6b — enforce ONE student_key per Avanti id.

    _match_fk_v2 withholds an fk when one student matches >1 Avanti id, but never
    checked the reverse: one Avanti id claimed by >1 student_key. Measured on the
    live table 2026-09-29, 2,968 ids were claimed twice or more, in two shapes:

      • COMPLEMENTARY — e.g. a b10 component and a jee component that no roll/app
        bridge joined (JEE-2025 nameless rows reached only by prod_nta_crosswalk).
        Same person, split by the over-split posture. Left alone, every consumer
        counting student_key counts them twice. → MERGED into one student_key.
      • CONFLICTING — two records of the SAME stage (two 10th-board rolls, often at
        different schools) each matched to the one id, e.g. two "KAJAL, 2008-07-16".
        At most one is the Avanti student. → the id stays with the claimant of the
        strictly best tier; the others lose it (match_confidence='shared_fk_conflict').
        If the best tier is itself a tie between conflicting claimants, the tie-breaker
        gives each tied claimant points against the Avanti student (`tie` facts): school
        (a 10th or 12th school code is the Avanti school code), cohort (its cohort is the
        Avanti cohort), DOB (a record DOB is the Avanti DOB) and father (a record father
        agrees, nd.father_check_v2). The one claimant with the most points keeps the id.
        When the top score is shared or zero, nobody keeps it (precision-first).

    Claimants are taken best tier first. Each is merged in only if it adds stages the
    accepted set does not already have AND its years fit one journey (every pre-entrance
    stage implies the same cohort_year; no entrance sitting before that cohort, except an
    early attempt one year before it that a claimant already has). A merge makes no new
    early attempt: an early attempt needs the parent check of _CheckedUnion, and step 6b
    has no parents.

    Returns (key, fk_df) with merged student_keys remapped (root = smallest key, as in
    _cluster) and fk_df re-keyed to one row per surviving student_key."""
    n2k = key.set_index("node_id")["student_key"]
    prof = {}   # student_key -> {"stages": set, "cohort": set, "entrance": set}
    for st in STAGES:
        df = nodes[st]
        yr = pd.to_numeric(df.yr, errors="coerce")
        for sk, y in zip(df.node_id.map(n2k), yr):
            p = prof.setdefault(sk, {"stages": set(), "cohort": set(), "entrance": set()})
            p["stages"].add(st)
            if pd.isna(y):
                continue
            if st in ("jee", "neet"):
                p["entrance"].add(int(y))
            else:
                p["cohort"].add(int(y) + (0 if st == "b12" else 2))

    def fits(acc, p):
        if acc["stages"] & p["stages"]:
            return False
        cohort = acc["cohort"] | p["cohort"]
        if len(cohort) > 1:
            return False
        ent = acc["entrance"] | p["entrance"]
        if not (cohort and ent) or min(ent) >= min(cohort):
            return True
        c = min(cohort)
        if min(ent) < c - _EARLY_YEARS:
            return False
        # an early attempt fits only when its part already had the cohort (no new early exam)
        return not [y for part in (acc, p) if not part["cohort"] for y in part["entrance"] if y < c]

    has = fk_df[fk_df.fk_avanti_student_id.notna()].copy()
    # a forward tie-breaker pick (match_count > 1) ranks below every unique match
    has["pri"] = (has.match_confidence.map(_CONF_PRI).fillna(99)
                  + 100 * (pd.to_numeric(has.match_count, errors="coerce") > 1))
    shared = has[has.duplicated("fk_avanti_student_id", keep=False)]

    # tie-breaker inputs: the facts of each student (school, cohort, DOBs, fathers)
    global _TIES
    _TIES = []
    facts = _student_facts(nodes, n2k, tie) if tie is not None else {}

    def points(k, fk) -> dict:
        """The tie-breaker points of claimant k against the Avanti student fk."""
        return _tie_points(facts.get(k), tie["avanti"].get(str(fk)) if tie is not None else None)

    def merge_from(first, keys):
        """Accept the claimants that fit with `first` (in tier order); return (accepted, rejected)."""
        acc = {f: set(v) for f, v in prof[first].items()}
        accepted, rejected = [first], []
        for k in keys:
            if k == first:
                continue
            if fits(acc, prof[k]):
                accepted.append(k)
                for f in acc:
                    acc[f] |= prof[k][f]
            else:
                rejected.append(k)
        return accepted, rejected

    remap, conflict = {}, set()
    n_ties, n_decided = 0, 0
    for fk, g in shared.sort_values(["pri", "student_key"]).groupby("fk_avanti_student_id"):
        keys, pris = g.student_key.tolist(), g.pri.tolist()
        accepted, rejected = merge_from(keys[0], keys)
        pri_of = dict(zip(keys, pris))
        if any(pri_of[k] == pris[0] for k in rejected):
            # tie at the best tier: the tie-breaker, else nobody keeps the id
            n_ties += 1
            conf_of = dict(zip(g.student_key, g.match_confidence))
            best = [k for k in keys if pri_of[k] == pris[0]]
            pts = {k: points(k, fk) for k in best}
            top = max(sum(v.values()) for v in pts.values())
            winners = [k for k in best if sum(pts[k].values()) == top]
            decided = top > 0 and len(winners) == 1
            for k in best:
                _TIES.append({"fk_avanti_student_id": str(fk), "student_key": k,
                              "match_confidence": conf_of[k], **pts[k],
                              "points": sum(pts[k].values()), "decided": decided,
                              "keeps_id": decided and k == winners[0]})
            if not decided:
                conflict.update(keys)
                continue
            n_decided += 1
            accepted, rejected = merge_from(winners[0], [winners[0]] + [k for k in keys if k != winners[0]])
        conflict.update(rejected)
        root = min(accepted)
        remap.update({k: root for k in accepted if k != root})

    key = key.assign(student_key=key.student_key.replace(remap))
    fk_df = fk_df.copy()
    lost = fk_df.student_key.isin(conflict)
    fk_df.loc[lost, "fk_avanti_student_id"] = pd.NA
    fk_df.loc[lost, "match_confidence"] = "shared_fk_conflict"
    fk_df["student_key"] = fk_df.student_key.replace(remap)
    # a merged student keeps its best-tier match (the root's own row may not be the best)
    fk_df["pri"] = fk_df.match_confidence.map(_CONF_PRI).fillna(99)
    fk_df = (fk_df.sort_values(["student_key", "pri"]).drop_duplicates("student_key")
                  .drop(columns="pri"))

    print(f"  step 6b — Avanti ids claimed by >1 student_key: "
          f"{shared.fk_avanti_student_id.nunique():,}; merged {len(remap):,} components into "
          f"their id's student; withheld the id from {len(conflict):,} conflicting claimants")
    print(f"  step 6b tie-breaker — {n_ties:,} ties at the best tier: {n_decided:,} decided "
          f"(school, cohort, DOB, father points), {n_ties - n_decided:,} left (nobody keeps the id)")
    left = fk_df.loc[fk_df.fk_avanti_student_id.notna(), "fk_avanti_student_id"]
    if left.duplicated().any():
        raise AssertionError(f"{int(left.duplicated().sum())} Avanti ids still sit on >1 student_key")
    return key, fk_df


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7 — outcome / marks payload (ported from v1's _read_marks + _enrich)
# ─────────────────────────────────────────────────────────────────────────────
_MARKS_YEAR_COLS = {"board_10th_exam_year", "board_12th_exam_year", "jee_test_year", "neet_test_year"}


def _read_marks(client) -> dict:
    """The result/marks frames merged onto the resolved spine to reach column-parity
    with v1 (jnv_student_outcome_mapping). Ported from v1's _read_marks:
    10th/12th school + subject marks + result, JEE mains+advanced scores/ranks/
    qualification, NEET score/rank/qualification, and the student_program/product
    lookup. Each frame is de-duplicated to ONE row per join key at query time
    (GROUP BY / QUALIFY ROW_NUMBER=1), so the left-merges in _build_rows cannot fan
    out the (student × attempt_year) grain. Two differences from v1: the year columns
    are returned as Int64 (v1 kept them string) to match v2's spine keys — the
    roll/app keys are `_S` strings on both sides, identical to how v2's nodes read
    them — and the board school (`school_code` / `school_name`) is carried through.
    ANY_VALUE is safe for the school: both board tables hold exactly one school_code
    and one school_name per (exam_year, roll_number), and neither is ever null."""
    q = {
        "b10_marks": """
            SELECT exam_year AS board_10th_exam_year, roll_number AS board_10th_roll_number,
                ANY_VALUE(school_code)                       AS board_10th_school_code,
                ANY_VALUE(school_name)                       AS board_10th_school_name,
                ANY_VALUE(SAFE_CAST(total_marks AS FLOAT64)) AS marks_10_obtained,
                ANY_VALUE(result)                            AS result_10,
                MAX(IF(UPPER(subject_name) LIKE '%MATH%',    SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_math,
                MAX(IF(UPPER(subject_name) LIKE '%SCIENCE%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_science,
                MAX(IF(UPPER(subject_name) LIKE '%ENGLISH%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_english
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_10th`
            WHERE roll_number IS NOT NULL AND exam_year IS NOT NULL GROUP BY 1, 2""",
        "b12_marks": """
            SELECT exam_year AS board_12th_exam_year, roll_number AS board_12th_roll_number,
                ANY_VALUE(school_code)                       AS board_12th_school_code,
                ANY_VALUE(school_name)                       AS board_12th_school_name,
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
                ANY_VALUE(category)               AS jee_category,
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
                ANY_VALUE(category)            AS neet_category,
                ANY_VALUE(neet_total_score)    AS neet_total_score,
                ANY_VALUE(neet_all_india_rank) AS neet_air,
                ANY_VALUE(neet_category_rank)  AS neet_category_rank,
                ANY_VALUE(neet_qualified)      AS neet_qualified,
                ANY_VALUE(b1a_cleared)         AS neet_b1a_cleared,
                ANY_VALUE(b1b_cleared)         AS neet_b1b_cleared
            FROM `avantifellows.external_data_sources.jnv_fact_neet_results`
            WHERE application_no IS NOT NULL AND test_year IS NOT NULL GROUP BY 1, 2""",
        # school_code -> UDISE code. A school code with two UDISE codes gives no value.
        "school_udise": """
            SELECT school_code, ANY_VALUE(udise) AS school_udise_code
            FROM (
                SELECT CAST(school_code AS STRING) AS school_code, TRIM(school_udise_code) AS udise
                FROM `avantifellows.production_dbt_final.dim_school`
                WHERE school_code IS NOT NULL AND NULLIF(TRIM(school_udise_code), '') IS NOT NULL
            )
            GROUP BY 1
            HAVING COUNT(DISTINCT udise) = 1""",
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
            elif c.endswith(("_qualified", "_cleared")):
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
                marks: dict, dim_pt: pd.DataFrame, prod_nta: dict, tie: dict | None = None) -> pd.DataFrame:
    # ── STEP 6 — Avanti fk via v2's own tiered matcher (not the source-table passthrough),
    # then 6b: one student_key per Avanti id. 6b can MERGE components, so it runs before
    # anything below is keyed on student_key, and `sid` is rebuilt on the merged keys.
    n2k = key.set_index("node_id")["student_key"]
    sid = _build_sid(nodes, n2k, refs, ncst24, prod_nta)
    facts = _student_facts(nodes, n2k, tie) if tie is not None else None
    fk_df = _match_fk_v2(sid, avanti_g12, avanti_all, all_ids, rec=_record_identities(nodes, n2k),
                         tie=tie, facts=facts)
    key, fk_df = _reconcile_shared_fk(nodes, key, fk_df, tie)
    n2k = key.set_index("node_id")["student_key"]
    sid = _build_sid(nodes, n2k, refs, ncst24, prod_nta)

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

    # resolved per-student identity (name / parents / dob) for the output — the
    # SAME source-coalesced values the STEP-6 matcher used (see _build_sid), so
    # the emitted identity is consistent with what the fk match keyed on.
    ident = sid[["student_key", "norm_name", "norm_father", "norm_mother", "dob", "student_gender"]].rename(
        columns={"norm_name": "student_name", "norm_father": "father_name",
                 "norm_mother": "mother_name", "dob": "student_dob"})

    # ── assemble the spine of all students, then attach attempts ──────────────
    students = pd.DataFrame({"student_key": key.student_key.unique()})
    students = (students.merge(ncst_p, on="student_key", how="left")
                        .merge(b10_p, on="student_key", how="left")
                        .merge(b12_p, on="student_key", how="left")
                        .merge(fk_df, on="student_key", how="left")
                        .merge(ident, on="student_key", how="left"))

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
    # UDISE code of each board school: the join key to dim_school and the UDISE tables for
    # the state, district and region of the school.
    udise = marks["school_udise"].set_index("school_code").school_udise_code
    for grade in ("10th", "12th"):
        rows[f"board_{grade}_school_udise_code"] = rows[f"board_{grade}_school_code"].map(udise)

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
    exam_rows = rows[FINAL_COLS]

    # ── dim-passthrough spine: enrolled grade-12 JNV students with NO exam/board/
    # NCST record → size-1 'dim-only' rows (roster completeness). Gate on BOTH: not
    # fk-resolved AND identity-absent (name+dob) from the graph, so a matched or
    # matchable (recall-miss) student is never re-created as a phantom duplicate.
    # fk = the student's own pk/apaar (a certain self-link).
    resolved = set(exam_rows.fk_avanti_student_id.dropna().astype(str)) - {"", "nan", "<NA>", "None"}
    # identity-present set: raw node (name,dob) UNION the component-coalesced (name,dob)
    # of every exam student. The coalesced half catches same-person collisions the raw
    # nodes miss — a student's emitted name/dob is coalesced across sources, so it can
    # differ from any single node's pair.
    present_nd = set()
    for st in STAGES:
        nd = nodes[st][["norm_name", "dob"]].dropna()
        present_nd |= set(zip(nd.norm_name, nd.dob))
    ex_nd = exam_rows[["student_name", "student_dob"]].dropna()
    present_nd |= set(zip(ex_nd.student_name, ex_nd.student_dob))
    cand = dim_pt[~dim_pt.fk_avanti_student_id.astype(str).isin(resolved)].copy()
    cand = cand[[(_one_word_once(nm), db) not in present_nd
                 for nm, db in zip(cand.student_name, cand.student_dob)]].copy()
    cand["student_key"] = "dim:" + cand.fk_avanti_student_id.astype(str)
    cand["match_confidence"], cand["match_count"] = "dim_passthrough", 1
    for f in ("has_ncst_data", "has_10th_data", "has_12th_data",
              "has_jee_mains_data", "has_jee_adv_data", "has_neet_data"):
        cand[f] = False
    for c in FINAL_COLS:
        if c not in cand:
            cand[c] = pd.NA
    print(f"  dim-passthrough: seeded {len(cand):,} dim-only students "
          f"({len(dim_pt) - len(cand):,} of {len(dim_pt):,} candidates already present in the graph)")
    return pd.concat([exam_rows, cand[FINAL_COLS]], ignore_index=True)


def _resolve(client) -> pd.DataFrame:
    print("Step 1 — reading source nodes ...")
    nodes = _read_nodes(client)
    print("        reading crosswalks ...")
    refs = _read_crosswalks()
    ncst24 = _read_ncst_avanti_id()
    avanti_g12, avanti_all, all_ids = _read_avanti_reference(client)
    marks = _read_marks(client)
    dim_pt = _read_dim_passthrough(client)
    prod_nta = _read_prod_nta_crosswalk(client)
    tie = _read_tie_facts(client)
    print("Steps 2–3 — edges + union-find ...")
    key = _cluster(nodes, refs, ncst24, {"g12": avanti_g12, "all": avanti_all,
                                          "all_ids": all_ids, "prod_nta": prod_nta, "tie": tie})
    print("Steps 4–7 — cohort_year + avanti fk + explode to (student × attempt_year) + outcome marks ...")
    return _build_rows(nodes, key, refs, avanti_g12, avanti_all, all_ids, ncst24, marks,
                       dim_pt, prod_nta, tie)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8 — load
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    import argparse
    from google.cloud import bigquery
    from google.cloud.bigquery import LoadJobConfig, WriteDisposition

    parser = argparse.ArgumentParser(
        description="Build jnv_student_outcome_mapping (clean-slate rewrite, steps 1-8; replaces v1).")
    parser.add_argument(
        "--out-table", default=OUT_TABLE,
        help="Table to write (project.dataset.table). The default is the production table. "
             "Give a scratch table to check the impact of a change. Do not run "
             "add_avanti_fk.py after a scratch run.")
    out_table = parser.parse_args().out_table
    if out_table != OUT_TABLE:
        print(f"SCRATCH RUN: writes {out_table}. The production table does not change.\n")

    for f in (POOJITA, TENTH_SCORE, JEE_2025_RAW.local_path, JEE_2024_RAW.local_path, NEET_2024_RAW.local_path):
        if not f.exists():
            print(f"ERROR: reference file not found: {f}")
            sys.exit(1)

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
    out = _resolve(client)

    print(f"\nFull rebuild → {out_table}: {len(out):,} rows, {out.student_key.nunique():,} students")
    client.load_table_from_dataframe(
        out, out_table,
        job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
    ).result()

    # scratch run only: the links that _CheckedUnion refused, for review (expires in 30 days)
    if out_table != OUT_TABLE and _REFUSED is not None and len(_REFUSED):
        import datetime as dt
        refused_table = f"{out_table}_refused"
        client.load_table_from_dataframe(
            _REFUSED, refused_table,
            job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
        ).result()
        t = client.get_table(refused_table)
        t.expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
        client.update_table(t, ["expires"])
        print(f"Refused links → {refused_table}: {len(_REFUSED):,} rows (expires in 30 days)")

    # scratch run only: the step 6b ties and their tie-breaker points, for review (expires in 30 days)
    if out_table != OUT_TABLE and _TIES:
        import datetime as dt
        ties_table = f"{out_table}_ties"
        client.load_table_from_dataframe(
            pd.DataFrame(_TIES), ties_table,
            job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
        ).result()
        t = client.get_table(ties_table)
        t.expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
        client.update_table(t, ["expires"])
        print(f"Ties → {ties_table}: {len(_TIES):,} rows (expires in 30 days)")

    # scratch run only: the middle-name links, for review (expires in 30 days)
    if out_table != OUT_TABLE and _MIDDLE:
        import datetime as dt
        middle_table = f"{out_table}_middle_name"
        client.load_table_from_dataframe(
            pd.DataFrame(_MIDDLE), middle_table,
            job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
        ).result()
        t = client.get_table(middle_table)
        t.expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)
        client.update_table(t, ["expires"])
        print(f"Middle-name links → {middle_table}: {len(_MIDDLE):,} rows (expires in 30 days)")

    # coverage summary
    summary = f"""
        SELECT cohort_year,
            COUNT(*) AS n_rows, COUNT(DISTINCT student_key) AS students,
            COUNTIF(ncst_test_year IS NOT NULL) AS has_ncst,
            COUNTIF(board_10th_exam_year IS NOT NULL) AS has_b10,
            COUNTIF(board_12th_exam_year IS NOT NULL) AS has_b12,
            COUNTIF(jee_test_year IS NOT NULL) AS has_jee,
            COUNTIF(neet_test_year IS NOT NULL) AS has_neet
        FROM `{out_table}` GROUP BY 1 ORDER BY cohort_year"""
    print(f"\n{'cohort':<7}{'rows':>9}{'students':>10}{'ncst':>8}{'b10':>9}{'b12':>9}{'jee':>9}{'neet':>9}")
    print("-" * 78)
    for r in client.query(summary).result():
        print(f"  {str(r.cohort_year):<5}{r.n_rows:>9,}{r.students:>10,}{r.has_ncst:>8,}"
              f"{r.has_b10:>9,}{r.has_b12:>9,}{r.has_jee:>9,}{r.has_neet:>9,}")
    print("\nDone.")


if __name__ == "__main__":
    main()
