#!/usr/bin/env python3
"""
Build jnv_student_outcome_mapping: a unified cross-table student IDENTITY map
for JNV students across board_10th, board_12th, JEE, and NEET — plus the
analyst-facing journey-of-results columns (10th → 12th → JEE/NEET).

ENGINE: this runs **entirely in pandas**. We pull each source down from BigQuery
ALREADY AGGREGATED to one row per natural key (the board tables are subject-long
and only collapse to ~one-row-per-student after GROUP BY), do all the identity
resolution / linking / FK matching as ordinary DataFrame merges, then upload the
finished table. There is no server-side CTE graph, so BigQuery's query-planner
complexity limit ("too many subqueries / query too complex") simply cannot occur.
The reference crosswalks (Poojita sheets, JEE-2024 file) are read straight from
local Excel — no temp tables.

The aggregated frames are small (board 12th ~400k students, board 10th ~450k,
JEE ~64k, NEET ~114k) so the whole pipeline fits comfortably in memory.

Grain: one row per (student_key, attempt_year), where
       attempt_year = COALESCE(jee_test_year, neet_test_year).
       Multiple JEE/NEET sittings → one row per entrance year.
       A student with no entrance record → one row with null attempt fields.

Spine: a RESOLVED STUDENT IDENTITY built from the UNION of all four stages —
       NOT anchored on 12th. A student with a JEE/NEET record but no 12th row
       still gets a journey (their cohort_year falls back to first entrance year).
       Bare 10th-only students are NOT seeded EXCEPT for the 2026/2027 frontier
       cohorts, whose 10th roster IS the cohort (no 12th/entrance data yet).

Run model: `_resolve()` builds the ENTIRE cross-year identity universe in one
       in-memory pass, so the default (no flag) rebuilds the whole table at once
       (WRITE_TRUNCATE). `--year YYYY` slices that same resolution to one cohort
       and refreshes it idempotently (DELETE rows for the year, then INSERT) —
       useful when only one year's source data changed. Each student has exactly
       one cohort_year, so cohorts are disjoint.

  cohort_year = COALESCE(board_12th_exam_year, board_10th_exam_year+2,
                         first_entrance_attempt_year)

Linkage priority (lowest number wins; "candidate-emit then keep-lowest-pri"):
  identity resolution (cluster records into one student):
    1. Poojita 2024 sheet  (12th↔10th↔JEE↔NEET roll/app crosswalk, 2024 cohort)
    2. roll_number_10th    (12th 2025 file → 10th direct) / JEE-2024 file rolls
    3. name (+father)      (12th→10th / 12th→JEE/NEET, unambiguous only)
  Avanti FK (= COALESCE(pk_student_id, apaar_id) — see note below):
    1. direct_student_id   (JEE 2025 avanti_studentid, NEET student_id, Poojita,
                            and the 10th-score crosswalk's (10th year, roll)→Avanti id,
                            which fills a direct id for b10-anchored students)
    2. name + DOB          (DOB from board_10th — richest identity source)
    3. name + DOB swapped  (DD/MM transposition)
    4. name_dob_fuzzy      (exact-DOB block + ≥2 shared name tokens AND token-
                            Jaccard ≥ 0.5 — LAST resort, unambiguous only; catches
                            token reorder/extra tokens, not initials-vs-full-name.
                            Single-token hits are dropped as coincidence-prone.)

⚠️ fk_avanti_student_id semantics: it is `pk_student_id` for MOST students, but for
   students who have NO pk_student_id in dim_student (only an apaar_id — mostly JNV
   NVS), it holds their `apaar_id` instead. So to join back to dim_student, match on
   `COALESCE(pk_student_id, apaar_id) = fk_avanti_student_id`, not on pk_student_id
   alone. Same for the fk written onto the source tables by add_avanti_fk.py.

Output columns are LEAN and grouped by stage. The join keys (rolls, app numbers)
and FK match metadata are retained because (a) they are the table's reason to
exist — they let you join out to the fact tables — and (b) `add_avanti_fk.py`
reads them to key the FK back onto the source tables.

Usage:
    python3 scripts/build_student_journey_mapping.py             # rebuild ALL cohorts
    python3 scripts/build_student_journey_mapping.py --year 2026 # refresh one cohort only
"""

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (BQ_PROJECT, BQ_LOCATION,
                     POOJITA, TENTH_SCORE, JEE_2024_RAW, JEE_2025_RAW, NEET_2024_RAW,
                     NCST_2024_RAW_CANDIDATES, NCST_2024_RAW_SHEET)

# Final column order: key → cohort → fk + match meta → program → ncst → 10th → 12th → jee → neet.
FINAL_COLS = [
    "student_key", "cohort_year", "fk_avanti_student_id",
    "match_confidence", "match_count",
    "student_program", "student_product",
    # stage-availability flags (student-level)
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


# ─────────────────────────────────────────────────────────────────────────────
# small helpers
# ─────────────────────────────────────────────────────────────────────────────
def _S(series: pd.Series) -> pd.Series:
    """Normalise a key column to trimmed pandas-string (NA stays NA)."""
    return series.astype("string").str.strip()


def _ne(series: pd.Series) -> pd.Series:
    """Boolean mask: value is present (not NA and not empty string)."""
    s = series.astype("string")
    return s.notna() & (s.str.len() > 0)


def _coalesce(*series: pd.Series) -> pd.Series:
    """First present (non-NA, non-empty) value across the given string Series."""
    out = series[0].astype("string").copy()
    for s in series[1:]:
        out = out.where(_ne(out), s.astype("string"))
    return out


def _year_shift(series: pd.Series, n: int) -> pd.Series:
    """'2025' → '2025'+n as a pandas-string ('2027'); NA-safe."""
    return (pd.to_numeric(series, errors="coerce").astype("Int64") + n).astype("string")


def _lowest_pri(cands: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Keep one candidate per key — the lowest `pri` (the priority ladder)."""
    if cands.empty:
        return cands
    return (cands.sort_values(keys + ["pri"])
                 .drop_duplicates(subset=keys, keep="first")
                 .reset_index(drop=True))


def _unambiguous(df: pd.DataFrame, group_keys: list[str]) -> pd.DataFrame:
    """Rows whose (group_keys) group has exactly one member (a unique match)."""
    if df.empty:
        return df
    sz = df.groupby(group_keys, dropna=False)[group_keys[0]].transform("size")
    return df[sz == 1]


# Token-set Jaccard for the fuzzy FK tier (last resort in _match_fk). Catches
# token reordering / extra-or-missing tokens that exact norm_name equality
# misses (common between NTA and dim_student name variants). Always DOB-blocked,
# so the candidate set per name is tiny → false positives stay low. Does NOT
# catch initials-vs-full-name ('S DEVI' vs 'SUNILA DEVI' → Jaccard 1/3) — that
# residual needs a different signal. Mirrors the DOB-blocked fuzzy idea first
# prototyped at board-10th clean time (the retired _add_fk_student_id, which used
# BQ EDIT_DISTANCE); here it runs in pandas so uses token Jaccard (no extra dep).
_FUZZY_JACCARD_MIN = 0.5
# Require ≥2 name tokens to agree. A single shared token — even at Jaccard 1.0,
# e.g. 'RAHUL' vs 'RAHUL' — is coincidence-prone within a same-age DOB block
# (JNV cohorts cluster on ~2 birth years), so single-token hits are dropped.
_FUZZY_MIN_SHARED = 2


def _fuzzy_ok(a: str, b: str) -> bool:
    """Fuzzy name match: ≥ _FUZZY_MIN_SHARED shared tokens AND Jaccard ≥ threshold."""
    ta, tb = set(a.split()), set(b.split())
    inter = len(ta & tb)
    return inter >= _FUZZY_MIN_SHARED and inter / len(ta | tb) >= _FUZZY_JACCARD_MIN


def _name_agree(a: str, b: str) -> bool:
    """Looser name agreement for crosswalk corroboration: equal ignoring spaces/dots,
    or token-set Jaccard ≥ 0.5. Accepts 'MANVITHA K T' ≈ 'MANVITHA KT' and token
    reorders; rejects genuinely different people. (Single-token exact still passes via
    the strip-equal test, unlike _fuzzy_ok which needs ≥2 shared tokens.)"""
    if not a or not b:
        return False
    if a.replace(" ", "").replace(".", "") == b.replace(" ", "").replace(".", ""):
        return True
    ta, tb = set(a.replace(".", " ").split()), set(b.replace(".", " ").split())
    return bool(ta) and bool(tb) and len(ta & tb) / len(ta | tb) >= _FUZZY_JACCARD_MIN


def _ent_key(name, father, dob, exam, yr, app, avanti_id) -> str:
    """
    Identity key for an entrance-only record (no 12th/10th anchor) — 3-tier HYBRID:
      1. avanti_id present  → `ent:sid:<id>`  (authoritative — a production-linked
         Avanti student; merges that person's records and stays distinct from others)
      2. name AND dob present → `ent:md5(name|father|dob)` (JEE+NEET / retakes merge)
      3. otherwise           → natural exam key `<exam>:<yr>:<app>` so identity-less
         records (e.g. the ~8k JEE-2025 rows with blank name+dob) stay DISTINCT
         instead of collapsing into one md5('||') bucket.
    (See student_journey_mapping.md decisions log.)
    """
    def _s(v):
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NA else str(v)
    aid = _s(avanti_id)
    if aid:
        return "ent:sid:" + aid
    name, dob = _s(name), _s(dob)
    if name and dob:
        return "ent:" + hashlib.md5(f"{name}|{_s(father)}|{dob}".encode("utf-8")).hexdigest()[:16]
    return f"{_s(exam)}:{_s(yr)}:{_s(app)}"


def _coalesce_by_source(contrib: pd.DataFrame, col: str, order: list[str],
                        is_date: bool = False) -> pd.Series:
    """
    Per student_key, pick `col` from the first source in `order` that has a
    present value (mirrors the SQL COALESCE(MAX(IF(src=...)))). Returns a Series
    indexed by student_key.
    """
    rank = {s: i for i, s in enumerate(order)}
    d = contrib.loc[contrib["src"].isin(order), ["student_key", "src", col]].copy()
    if is_date:
        d = d[d[col].notna()]
    else:
        d = d[_ne(d[col])]
    d["r"] = d["src"].map(rank)
    d = d.sort_values(["student_key", "r"]).drop_duplicates("student_key", keep="first")
    return d.set_index("student_key")[col]


# ─────────────────────────────────────────────────────────────────────────────
# BigQuery reads — each is a single, simple, single-table aggregation
# ─────────────────────────────────────────────────────────────────────────────
def _read_sources(client) -> dict:
    """Pull the four normalised source frames (one row per natural key)."""
    name = r"UPPER(TRIM(REGEXP_REPLACE({c}, r'\s+', ' ')))"
    nn   = lambda c: name.format(c=c)
    nnc  = lambda c: name.format(c=f"COALESCE({c},'')")
    dob_parse = ("COALESCE(SAFE.PARSE_DATE('%d-%m-%Y', dob),"
                 " SAFE.PARSE_DATE('%Y-%m-%d', dob),"
                 " SAFE.PARSE_DATE('%d%m%Y', dob))")

    q = {
        "b12": f"""
            SELECT exam_year AS yr12, roll_number AS roll12,
                ANY_VALUE({nn('student_name')})  AS norm_name,
                ANY_VALUE({nnc('father_name')})  AS norm_father,
                ANY_VALUE({nnc('mother_name')})  AS norm_mother,
                ANY_VALUE(roll_number_10th)      AS roll_number_10th
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_12th`
            WHERE roll_number IS NOT NULL AND student_name IS NOT NULL
            GROUP BY 1, 2""",
        "b10": f"""
            SELECT exam_year AS yr10, roll_number AS roll10,
                ANY_VALUE({nn('student_name')}) AS norm_name,
                FORMAT_DATE('%Y-%m-%d',
                    ANY_VALUE(SAFE.PARSE_DATE('%d%m%Y', LPAD(date_of_birth, 8, '0')))) AS dob,
                ANY_VALUE({nnc('father_name')}) AS norm_father,
                ANY_VALUE({nnc('mother_name')}) AS norm_mother
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_10th`
            WHERE roll_number IS NOT NULL AND student_name IS NOT NULL
            GROUP BY 1, 2""",
        "jee": f"""
            SELECT test_year, application_no,
                ANY_VALUE({nnc('student_full_name')}) AS norm_name,
                FORMAT_DATE('%Y-%m-%d', ANY_VALUE({dob_parse})) AS dob,
                ANY_VALUE({nnc('father_name')}) AS norm_father,
                ANY_VALUE({nnc('mother_name')}) AS norm_mother
            FROM `avantifellows.external_data_sources.jnv_fact_jee_results`
            WHERE application_no IS NOT NULL
            GROUP BY 1, 2""",
        "neet": f"""
            SELECT test_year, application_no,
                ANY_VALUE({nnc('student_full_name')}) AS norm_name,
                FORMAT_DATE('%Y-%m-%d', ANY_VALUE({dob_parse})) AS dob,
                ANY_VALUE({nnc('father_name')}) AS norm_father,
                ANY_VALUE({nnc('mother_name')}) AS norm_mother
            FROM `avantifellows.external_data_sources.jnv_fact_neet_results`
            WHERE application_no IS NOT NULL
            GROUP BY 1, 2""",
    }
    out = {}
    for k, sql in q.items():
        df = client.query(sql).to_dataframe()
        for c in df.columns:
            df[c] = _S(df[c])  # everything (incl. dob as 'YYYY-MM-DD') stays string
        out[k] = df
        print(f"  read {k:<4} {len(df):>8,} rows")
    return out


def _read_avanti(client) -> pd.DataFrame:
    """
    JNV grade-12 students from dim_student (+ historical), with DOB & swapped DOB.

    The Avanti id is `COALESCE(pk_student_id, apaar_id)`: some students (mostly JNV
    NVS) have NO pk_student_id, only an apaar_id, so we fall back to apaar so they can
    still be linked. This means `fk_avanti_student_id` in the output holds a pk for
    most rows but an apaar_id for pk-less students — join on
    `COALESCE(pk_student_id, apaar_id)`. (See schema note in student_journey_mapping.md.)
    """
    name = r"UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\s+', ' ')))"
    swap = ("SAFE.DATE(EXTRACT(YEAR FROM date_of_birth),"
            " EXTRACT(DAY FROM date_of_birth), EXTRACT(MONTH FROM date_of_birth))")
    years = "'2020-2021','2021-2022','2022-2023','2023-2024','2024-2025','2025-2026','2026-2027'"
    filt = (f"(LOWER(COALESCE(student_school,'')) LIKE '%jnv%'"
            f" OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')"
            f" AND student_grade = 12 AND academic_year IN ({years})"
            f" AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL")
    sql = f"""
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk_student_id,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS dob,
            {name} AS norm_name,
            FORMAT_DATE('%Y-%m-%d', {swap}) AS dob_swapped
        FROM `avantifellows.production_dbt_final.dim_student`  WHERE {filt}
        UNION ALL
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk_student_id,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS dob,
            {name} AS norm_name,
            FORMAT_DATE('%Y-%m-%d', {swap}) AS dob_swapped
        FROM `avantifellows.production_dbt_final.dim_student_historical` WHERE {filt}
    """
    df = client.query(sql).to_dataframe().drop_duplicates()
    for c in df.columns:
        df[c] = _S(df[c])  # dob / dob_swapped kept as 'YYYY-MM-DD' strings

    # Full id universe (NO JNV/grade filter) — used to validate a DIRECT FK (e.g. a
    # production-supplied student_id may sit under a non-JNV label). Same
    # COALESCE(pk_student_id, apaar_id) as above so apaar-only students validate too.
    # Name/DOB matching still uses the tighter `df` frame above. We also carry the
    # student's name here (one extra column on this already-run scan, NOT a new query)
    # so the 10th-score crosswalk can be name-corroborated against ALL grades — the 2027
    # frontier ids are grade 11 now, so the grade-12 `df` frame above wouldn't cover them.
    id_names = client.query(
        f"SELECT COALESCE(pk_student_id, apaar_id) AS id, {name} AS nm "
        f"FROM `avantifellows.production_dbt_final.dim_student` "
        f"WHERE COALESCE(pk_student_id, apaar_id) IS NOT NULL "
        f"UNION DISTINCT "
        f"SELECT COALESCE(pk_student_id, apaar_id), {name} "
        f"FROM `avantifellows.production_dbt_final.dim_student_historical` "
        f"WHERE COALESCE(pk_student_id, apaar_id) IS NOT NULL"
    ).to_dataframe()
    for c in id_names.columns:
        id_names[c] = _S(id_names[c])
    all_ids = set(id_names["id"].dropna())

    # Broader JNV frame — ALL grades (not just 12) — for NCST name+DOB matching.
    # NCST is sat ~grade 10; its students (esp. the nvs 2026 cohort, currently grade
    # 10/11) are NOT in the grade-12 `df` frame, so matching NCST against `df` would
    # miss almost all of them. Same JNV + year + dob filters, minus the grade=12 clause.
    fname = r"UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\s+', ' ')))"
    filt_all = (f"(LOWER(COALESCE(student_school,'')) LIKE '%jnv%'"
                f" OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')"
                f" AND academic_year IN ({years})"
                f" AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL")
    avanti_ncst = client.query(f"""
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id) AS pk_student_id,
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)) AS dob,
            {name} AS norm_name, {fname} AS norm_father,
            FORMAT_DATE('%Y-%m-%d', {swap}) AS dob_swapped
        FROM `avantifellows.production_dbt_final.dim_student`  WHERE {filt_all}
        UNION DISTINCT
        SELECT DISTINCT COALESCE(pk_student_id, apaar_id),
            FORMAT_DATE('%Y-%m-%d', DATE(date_of_birth)),
            {name}, {fname},
            FORMAT_DATE('%Y-%m-%d', {swap})
        FROM `avantifellows.production_dbt_final.dim_student_historical` WHERE {filt_all}
    """).to_dataframe().drop_duplicates()
    for c in avanti_ncst.columns:
        avanti_ncst[c] = _S(avanti_ncst[c])
    avanti_ncst["norm_father"] = avanti_ncst["norm_father"].where(_ne(avanti_ncst["norm_father"]))

    print(f"  read avanti {len(df):>6,} rows  ({len(all_ids):,} total pk ids, "
          f"{len(id_names):,} id×name, {len(avanti_ncst):,} JNV all-grade for ncst)")
    return df, all_ids, id_names, avanti_ncst


def _read_marks(client) -> dict:
    """The result/marks frames used to enrich the resolved spine."""
    q = {
        "b10_marks": f"""
            SELECT exam_year AS board_10th_exam_year, roll_number AS board_10th_roll_number,
                ANY_VALUE(SAFE_CAST(total_marks AS FLOAT64)) AS marks_10_obtained,
                ANY_VALUE(result)                            AS result_10,
                MAX(IF(UPPER(subject_name) LIKE '%MATH%',    SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_math,
                MAX(IF(UPPER(subject_name) LIKE '%SCIENCE%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_science,
                MAX(IF(UPPER(subject_name) LIKE '%ENGLISH%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_10_english
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_10th`
            WHERE roll_number IS NOT NULL AND exam_year IS NOT NULL GROUP BY 1, 2""",
        "b12_marks": f"""
            SELECT exam_year AS board_12th_exam_year, roll_number AS board_12th_roll_number,
                ANY_VALUE(SAFE_CAST(total_marks AS FLOAT64)) AS marks_12_obtained,
                ANY_VALUE(result)                            AS result_12,
                MAX(IF(UPPER(subject_name) LIKE '%PHYSIC%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_physics,
                MAX(IF(UPPER(subject_name) LIKE '%CHEMIS%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_chemistry,
                MAX(IF(UPPER(subject_name) LIKE '%MATH%',   SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_maths,
                MAX(IF(UPPER(subject_name) LIKE '%BIOLOG%', SAFE_CAST(final_marks AS FLOAT64), NULL)) AS marks_12_biology
            FROM `avantifellows.external_data_sources.jnv_fact_board_results_12th`
            WHERE roll_number IS NOT NULL AND exam_year IS NOT NULL GROUP BY 1, 2""",
        "jee_results": f"""
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
        "neet_results": f"""
            SELECT test_year AS neet_test_year, application_no AS neet_application_no,
                ANY_VALUE(neet_total_score)    AS neet_total_score,
                ANY_VALUE(neet_all_india_rank) AS neet_air,
                ANY_VALUE(neet_category_rank)  AS neet_category_rank,
                ANY_VALUE(neet_qualified)      AS neet_qualified
            FROM `avantifellows.external_data_sources.jnv_fact_neet_results`
            WHERE application_no IS NOT NULL AND test_year IS NOT NULL GROUP BY 1, 2""",
        "program_lookup": f"""
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
            -- one row per student: prefer current dim over historical (src), then the
            -- latest enrollment (academic_year) — matters for the 54k pks that appear
            -- in multiple historical rows.
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY fk_avanti_student_id ORDER BY src, academic_year DESC) = 1""",
    }
    out = {}
    for k, sql in q.items():
        df = client.query(sql).to_dataframe()
        for c in df.columns:
            if c.endswith("_qualified"):
                pass  # boolean — leave as-is (check first: 'jee_advanced_qualified' etc.)
            elif (c.endswith("_rank") or c.startswith(("marks_", "jee_total", "jee_air",
                                                       "neet_total", "neet_air"))):
                df[c] = pd.to_numeric(df[c], errors="coerce")
            else:
                df[c] = _S(df[c])
        out[k] = df
    return out


def _read_prod_fk(client) -> dict:
    """
    Avanti's own `application_no → student_id` linkage, lifted from the production
    dbt fact tables (fact_student_jee_main_results / fact_student_neet_results).
    These rows are Avanti students whose JEE/NEET result dbt already matched to
    `pk_student_id` — an AUTHORITATIVE direct FK, independent of the (often blank)
    identity fields in our jnv_fact_* sources. Keyed (test_year, application_no).
    """
    P = "avantifellows.production_dbt_final"
    out = {}
    for k, tbl in (("jee", "fact_student_jee_main_results"), ("neet", "fact_student_neet_results")):
        # Only trust an application_no→student_id link when it is UNAMBIGUOUS.
        # production's application_no is a placeholder before 2025 (one constant
        # value shared by hundreds of students), so HAVING COUNT(DISTINCT
        # student_id)=1 both (a) prevents an arbitrary ANY_VALUE mis-assignment
        # and (b) cleanly drops the placeholder years. Net effect: this fetch
        # contributes only where the app number really identifies one student
        # (JEE 2025/2026, NEET 2025); earlier years fall back to name+DOB.
        df = client.query(f"""
            SELECT CAST(test_year AS STRING) AS test_year,
                   CAST(application_no AS STRING) AS application_no,
                   ANY_VALUE(CAST(student_id AS STRING)) AS prod_sid
            FROM `{P}.{tbl}`
            WHERE application_no IS NOT NULL AND student_id IS NOT NULL
            GROUP BY 1, 2
            HAVING COUNT(DISTINCT student_id) = 1
        """).to_dataframe()
        for c in df.columns:
            df[c] = _S(df[c])
        out[k] = df
        print(f"  read prod_fk {k:<4} {len(df):>7,} rows")
    return out


def _read_refs() -> dict:
    """Local Excel crosswalks — no upload."""
    p24 = pd.read_excel(POOJITA, sheet_name="Mapped Data (2024 Students)", dtype=str).rename(
        columns={"JEE application No": "jee_app_no", "NEET Application No": "neet_app_no",
                 "10th Roll No": "roll_10th", "12th Roll No": "roll_12th"})
    p24 = p24[["jee_app_no", "neet_app_no", "roll_10th", "roll_12th"]]

    p25 = pd.read_excel(POOJITA, sheet_name="Mapped Data (2025 Students)", dtype=str).rename(
        columns={"Avanti Student ID": "avanti_student_id", "10th Roll Number": "roll_10th"})
    p25 = p25[["avanti_student_id", "roll_10th"]]

    j25 = pd.read_excel(JEE_2025_RAW.local_path, sheet_name=JEE_2025_RAW.sheet,
                        usecols=["JEEApplicationNumber", "avanti_studentid"], dtype=str).rename(
        columns={"JEEApplicationNumber": "application_no", "avanti_studentid": "avanti_student_id"})

    j24 = pd.read_excel(JEE_2024_RAW.local_path, sheet_name=JEE_2024_RAW.sheet,
                        usecols=["Application Number", "10th Roll Number", "12th Roll Number", "Student ID"],
                        dtype=str).rename(
        columns={"Application Number": "application_no", "10th Roll Number": "roll_10",
                 "12th Roll Number": "roll_12", "Student ID": "student_id"})

    # NEET-2024 board crosswalk — same shape as jee24x (app → 10th/12th roll, Student ID).
    n24 = pd.read_excel(NEET_2024_RAW.local_path, sheet_name=NEET_2024_RAW.sheet,
                        usecols=["Application Number", "10th Roll Number", "12th Roll Number", "Student ID"],
                        dtype=str).rename(
        columns={"Application Number": "application_no", "10th Roll Number": "roll_10",
                 "12th Roll Number": "roll_12", "Student ID": "student_id"})

    # 10th-roll → Avanti id crosswalk (Physical Mapping sheet). Gives a DIRECT Avanti
    # student id keyed on the (10th year, 10th roll) PAIR — used to fill an id for
    # b10-anchored students that the entrance side didn't supply.
    r10 = pd.read_excel(TENTH_SCORE, sheet_name="Physical Mapping", dtype=str).rename(
        columns={"10th Year": "yr10", "10th Roll No": "roll10", "Avanti Student ID": "avanti_id"})
    r10 = r10[["yr10", "roll10", "avanti_id"]]

    refs = {"poojita24": p24, "poojita25": p25, "jee25_avanti": j25, "jee24x": j24,
            "neet24x": n24, "roll10x": r10}
    for name, df in refs.items():
        for c in df.columns:
            df[c] = _S(df[c]).replace("nan", pd.NA)
        print(f"  read ref {name:<13} {len(df):>7,} rows")

    # roll10x: keep only rows with all three keys, and only (yr10, roll10) pairs that map
    # to exactly ONE id — a roll is unique only WITHIN a year, and an ambiguous pair must
    # not guess (mirrors the roll/app (year, key) rule used throughout this build).
    rx = refs["roll10x"]
    rx = rx[rx.yr10.notna() & rx.roll10.notna() & rx.avanti_id.notna()]
    n_uniq = rx.groupby(["yr10", "roll10"]).avanti_id.transform("nunique")
    refs["roll10x"] = rx[n_uniq == 1].drop_duplicates(["yr10", "roll10"]).reset_index(drop=True)
    print(f"  roll10x → {len(refs['roll10x']):,} unambiguous (yr10, roll10)→id pairs")
    return refs


def _corroborate_roll10x(roll10x: pd.DataFrame, b10: pd.DataFrame, id_names: pd.DataFrame) -> pd.DataFrame:
    """Keep only crosswalk (yr10, roll10)→avanti_id rows whose identity is CORROBORATED:
    the 10th-board name for that (year, roll) must agree with dim_student's name for that
    Avanti id. The Physical-Mapping sheet has row-alignment errors — a shifted NVS block
    where each roll mapped to a NEIGHBOUR's id, plus scattered wrong roll→id rows — that
    would otherwise inject links to the wrong student. A board name that disagrees with the
    id's dim name is the signal that flags them. Same-person rows whose DOBs merely differ
    (data-entry noise) are KEPT — their names still agree, and those are exactly the gap the
    crosswalk exists to fill (name+DOB missed them BECAUSE the DOBs disagree).

    `id_names` is the in-memory (id, nm) frame from _read_avanti — NO extra BQ query."""
    if roll10x.empty:
        return roll10x
    bn = (b10[["yr10", "roll10", "norm_name"]]
          .dropna(subset=["norm_name"]).rename(columns={"norm_name": "board_name"}))
    r = roll10x.merge(bn, on=["yr10", "roll10"], how="left")

    # dim_student name(s) per crosswalk id (all grades — the (id, nm) frame already
    # covers both dim tables; 2027 frontier ids are grade 11 so grade-12-only wouldn't do).
    xids = set(r.avanti_id.dropna())
    sub = id_names[id_names["id"].isin(xids) & id_names["nm"].notna()]
    names_by_id = sub.groupby("id")["nm"].apply(set).to_dict()

    def _ok(board_nm, aid):
        if board_nm is None or (isinstance(board_nm, float) and pd.isna(board_nm)) or board_nm is pd.NA:
            return False
        return any(_name_agree(str(board_nm), dm) for dm in names_by_id.get(aid, ()))

    keep = pd.Series([_ok(b, a) for b, a in zip(r.board_name, r.avanti_id)], index=r.index)
    out = r[keep][["yr10", "roll10", "avanti_id"]].reset_index(drop=True)
    print(f"  roll10x corroborated → {len(out):,} of {len(roll10x):,} kept "
          f"(board name agrees with dim id; {len(roll10x) - len(out):,} dropped as uncorroborated)")
    return out


def _read_ncst(client) -> pd.DataFrame:
    """
    NCST (Navodaya CoE Selection Test) records from both external tables (dakshana +
    nvs) in BigQuery, one row per (ncst_source, ncst_test_year, ncst_roll_no) with
    normalised identity fields (name, DOB, father).

    NCST is a Stage-1 selection test with NO roll/app that bridges to the board /
    JEE / NEET keys, so it can only be linked to a resolved student by IDENTITY:
    name+DOB, name+father, or the 2024 direct Avanti id crosswalk. DOB is present only
    for dakshana 2022 and nvs 2026; father_name for dakshana 2023/2024 and nvs 2026 —
    so the DOB-less dakshana 2023/2024 reach an fk via name+father, while 2025 (no DOB,
    no father) can only match through the 2024 direct-id crosswalk (which it lacks) →
    2025 gets no fk. Reads father_name from BigQuery, so the NCST tables must carry it
    (load dakshana/ + nvs/ clean → BQ before rebuilding — see run order below).
    """
    name = r"UPPER(TRIM(REGEXP_REPLACE({c}, r'\s+', ' ')))"
    nnc  = lambda c: name.format(c=f"COALESCE({c},'')")
    # normalise dob to 'YYYY-MM-DD' (the clean tables already store it that way; the
    # SAFE.PARSE_DATE round-trips valid values and nulls anything unexpected).
    dob = "FORMAT_DATE('%Y-%m-%d', SAFE.PARSE_DATE('%Y-%m-%d', dob))"
    sql = f"""
        SELECT 'dakshana' AS ncst_source, test_year AS ncst_test_year, roll_no AS ncst_roll_no,
               {nnc('student_full_name')} AS norm_name, {nnc('father_name')} AS norm_father,
               {dob} AS dob
        FROM `avantifellows.external_data_sources.dakshana_fact_ncst_results`
        WHERE roll_no IS NOT NULL
        UNION ALL
        SELECT 'nvs', test_year, roll_no,
               {nnc('student_full_name')}, {nnc('father_name')}, {dob}
        FROM `avantifellows.external_data_sources.nvs_fact_ncst_results`
        WHERE roll_no IS NOT NULL
    """
    df = client.query(sql).to_dataframe()
    for c in df.columns:
        df[c] = _S(df[c])
    df["dob"] = df["dob"].where(_ne(df["dob"]))
    df["norm_father"] = df["norm_father"].where(_ne(df["norm_father"]))
    print(f"  read ncst {len(df):>8,} rows "
          f"({(df.ncst_source=='dakshana').sum():,} dakshana, {(df.ncst_source=='nvs').sum():,} nvs; "
          f"{df.dob.notna().sum():,} with dob, {_ne(df.norm_father).sum():,} with father)")
    return df


def _read_ncst_avanti_id() -> pd.DataFrame:
    """
    The Dakshana NCST-2024 raw Excel carries a direct 'Avanti ID' keyed on
    'Dakshana Roll Number' (= the table's roll_no for 2024). Read as a
    highest-confidence direct-id crosswalk: (ncst_test_year='2024', ncst_roll_no)
    → ncst_avanti_id. Kept only where a single id maps to the roll. Missing raw is
    non-fatal — the direct tier is simply skipped and matching falls back to name+DOB.
    """
    cols = ["ncst_test_year", "ncst_roll_no", "ncst_avanti_id"]
    for path in NCST_2024_RAW_CANDIDATES:
        if not path.exists():
            continue
        d = pd.read_excel(path, sheet_name=NCST_2024_RAW_SHEET, dtype=str)
        out = pd.DataFrame({
            "ncst_test_year": "2024",
            "ncst_roll_no":   _S(d["Dakshana Roll Number"]),
            "ncst_avanti_id": _S(d["Avanti ID"]),
        })
        out = out[_ne(out.ncst_avanti_id) & _ne(out.ncst_roll_no)]
        # keep only rolls that map to exactly one id (drop contested rolls)
        n = out.groupby("ncst_roll_no").ncst_avanti_id.transform("nunique")
        out = out[n == 1].drop_duplicates("ncst_roll_no").reset_index(drop=True)
        print(f"  read ncst_2024 direct-id crosswalk {len(out):>5,} rows  ({path})")
        return out[cols]
    print("  WARNING: NCST 2024 raw not found in any candidate path — direct-id tier skipped")
    return pd.DataFrame(columns=cols)


# ─────────────────────────────────────────────────────────────────────────────
# NCST resolution — attach to resolved students, seed Avanti-linked orphans
# ─────────────────────────────────────────────────────────────────────────────
def _resolve_ncst(ncst: pd.DataFrame, ncst_aid: pd.DataFrame, sid: pd.DataFrame,
                  avanti_ncst: pd.DataFrame, all_ids: set, fk_resolved: pd.DataFrame):
    """
    Link each NCST record to a resolved student (decision 2026-07-10,
    "attach + seed Avanti-linked orphans"), in three modes:

      ATTACH (identity) — the NCST identity matches EXACTLY ONE already-resolved
        student (`sid`) by name+DOB, else name+father; the NCST roll/year/source
        decorate that existing student_key. Ambiguous (>1) matches are dropped.

      ATTACH (fk) — an NCST record with no `sid` identity match still resolves to an
        Avanti fk (below) that ALREADY belongs to a spine student. Decorate that
        existing student_key rather than minting a new one — this avoids counting
        one Avanti person as two students when their NCST identity (name/DOB from
        the NCST file) differs from their board/JEE/NEET-derived identity.

      SEED — an NCST record with no `sid` match whose Avanti fk is NOT already on a
        spine student is seeded as a NEW student. fk from an unambiguous match to the
        JNV (all-grade) dim frame, priority: direct 2024 id → name+DOB → name+DOB-
        swapped → name+father. name+father is what lets the DOB-less dakshana 2023/
        2024 rows reach an fk at all (2025 has neither DOB nor father → no fk). Never
        floods the table with the ~85k non-Avanti test-takers, never drops an
        Avanti-linked one. Seed key = `ncst:<source>:<year>:<roll>`, cohort_year =
        ncst_test_year + 2 (verified: dakshana NCST 2022 → 12th board 2024).

    Returns (ncst_key, seed_master, seed_fk):
      ncst_key    — student_key → (ncst_source, ncst_test_year, ncst_roll_no), one per key
      seed_master — new spine rows for seeded orphans (master_cols shape, board/* null)
      seed_fk     — student_key → (fk_avanti_student_id, match_confidence, match_count)
    """
    KEYS = ["ncst_source", "ncst_test_year", "ncst_roll_no"]
    ncst = ncst.merge(ncst_aid, on=["ncst_test_year", "ncst_roll_no"], how="left")

    def _uniq(left, right, rid, left_cols, right_cols, conf):
        """Per NCST key, count/pick the matched right-id on (left_cols == right_cols).
        Blank/NA keys on either side are excluded, so an empty father/name never joins."""
        sub = left
        for c in left_cols:
            sub = sub[_ne(sub[c])]
        r = right
        for c in right_cols:
            r = r[_ne(r[c])]
        r = r[[rid] + right_cols].drop_duplicates()
        mm = sub.merge(r, left_on=left_cols, right_on=right_cols)
        gg = mm.groupby(KEYS).agg(cnt=(rid, "nunique"), cand=(rid, "first")).reset_index()
        gg["conf"] = conf
        return gg[KEYS + ["cnt", "cand", "conf"]]

    # ── ATTACH (identity): NCST → resolved student (sid) by name+DOB, then name+father ──
    a = pd.concat([
        _uniq(ncst, sid, "student_key", ["norm_name", "dob"], ["norm_name", "dob"], "name_dob"),
        _uniq(ncst, sid, "student_key", ["norm_name", "norm_father"], ["norm_name", "norm_father"], "name_father"),
    ], ignore_index=True)
    matched_any = set(map(tuple, a[KEYS].itertuples(index=False, name=None)))
    a["amb"] = a.cnt != 1
    a["pri"] = a.conf.map({"name_dob": 1, "name_father": 2})
    a = a.sort_values(KEYS + ["amb", "pri"]).drop_duplicates(KEYS, keep="first")
    attached = a[a.cnt == 1][KEYS + ["cand"]].rename(columns={"cand": "student_key"})

    # ── resolve an Avanti fk for records with NO sid match (candidates to seed) ──
    orphan = ncst[~pd.Series(list(zip(ncst.ncst_source, ncst.ncst_test_year, ncst.ncst_roll_no)),
                             index=ncst.index).isin(matched_any)]

    # direct 2024 Avanti id (validated against the full pk/apaar universe)
    direct = orphan[_ne(orphan.ncst_avanti_id) & orphan.ncst_avanti_id.isin(all_ids)]
    direct = pd.DataFrame({**{k: direct[k] for k in KEYS},
                           "fk": direct.ncst_avanti_id, "conf": "direct_avanti_id", "cnt": 1})

    def _seed(left_cols, right_cols, conf):
        g = _uniq(orphan, avanti_ncst, "pk_student_id", left_cols, right_cols, conf)
        return pd.DataFrame({**{k: g[k] for k in KEYS},
                             "fk": g["cand"].where(g.cnt == 1), "conf": conf, "cnt": g.cnt})

    pri = {"direct_avanti_id": 1, "name_dob": 2, "name_dob_swapped": 3, "name_father": 4}
    cand = pd.concat([
        direct,
        _seed(["norm_name", "dob"], ["norm_name", "dob"], "name_dob"),
        _seed(["norm_name", "dob"], ["norm_name", "dob_swapped"], "name_dob_swapped"),
        _seed(["norm_name", "norm_father"], ["norm_name", "norm_father"], "name_father"),
    ], ignore_index=True)
    cand["fk_isnull"] = cand.fk.isna()
    cand["pri"] = cand.conf.map(pri)
    cand = cand.sort_values(KEYS + ["fk_isnull", "pri"]).drop_duplicates(KEYS, keep="first")
    resolved = cand[cand.fk.notna()].copy()

    # split resolved orphans: fk already on a spine student → attach to that key;
    # otherwise → mint a new seed key.
    fk2key = (fk_resolved[fk_resolved.fk_avanti_student_id.notna()]
              .drop_duplicates("fk_avanti_student_id")
              .set_index("fk_avanti_student_id")["student_key"])
    resolved["student_key"] = resolved.fk.map(fk2key)
    fk_attach = resolved[resolved.student_key.notna()]
    seed = resolved[resolved.student_key.isna()].copy()
    seed["student_key"] = ("ncst:" + seed.ncst_source + ":" + seed.ncst_test_year
                           + ":" + seed.ncst_roll_no)

    # ── ncst_key: one NCST sitting per student_key (earliest year) ──────────────
    ncst_key = pd.concat([attached[["student_key"] + KEYS],
                          fk_attach[["student_key"] + KEYS],
                          seed[["student_key"] + KEYS]], ignore_index=True)
    ncst_key = (ncst_key.sort_values(["student_key", "ncst_test_year"])
                        .drop_duplicates("student_key", keep="first").reset_index(drop=True))

    seed_master = pd.DataFrame({
        "student_key": seed.student_key,
        "cohort_year": _year_shift(seed.ncst_test_year, 2),
        "cohort_year_source": "ncst",
        "board_12th_exam_year": pd.NA, "board_12th_roll_number": pd.NA,
        "board_10th_exam_year": pd.NA, "board_10th_roll_number": pd.NA,
        "board_10th_link_source": pd.NA,
    })
    seed_fk = pd.DataFrame({
        "student_key": seed.student_key, "fk_avanti_student_id": seed.fk,
        "match_confidence": seed.conf, "match_count": seed.cnt,
    })
    print(f"  ncst → {len(attached):,} attached (identity), {len(fk_attach):,} attached (fk), "
          f"{len(seed):,} seeded as new Avanti-linked orphans "
          f"(direct_id {(seed.conf=='direct_avanti_id').sum():,}, "
          f"name_dob {(seed.conf=='name_dob').sum():,}, "
          f"swapped {(seed.conf=='name_dob_swapped').sum():,}, "
          f"name_father {(seed.conf=='name_father').sum():,})")
    return ncst_key, seed_master, seed_fk


# ─────────────────────────────────────────────────────────────────────────────
# identity resolution (all pandas)
# ─────────────────────────────────────────────────────────────────────────────
def _resolve(src: dict, refs: dict, avanti: pd.DataFrame, prod: dict, all_ids: set,
             ncst: pd.DataFrame, ncst_aid: pd.DataFrame, avanti_ncst: pd.DataFrame) -> pd.DataFrame:
    b12, b10, jee, neet = src["b12"], src["b10"], src["jee"], src["neet"]
    p24, p25 = refs["poojita24"], refs["poojita25"]
    j25, j24x, n24x = refs["jee25_avanti"], refs["jee24x"], refs["neet24x"]
    roll10x = refs["roll10x"]

    # Direct-Avanti-id, highest trust first:
    #   1. production dbt's application_no→student_id (Avanti's own authoritative link)
    #   2. JEE-2025 file avanti_studentid · 3. JEE-2024 file Student ID
    jee = (jee.merge(prod["jee"], on=["test_year", "application_no"], how="left")
              .merge(j25[["application_no", "avanti_student_id"]], on="application_no", how="left")
              .merge(j24x[["application_no", "student_id"]], on="application_no", how="left"))
    jee["avanti_id"] = _coalesce(jee["prod_sid"], jee["avanti_student_id"], jee["student_id"])
    jee = jee.drop(columns=["prod_sid", "avanti_student_id", "student_id"])

    # NEET avanti id: production → NEET-2024 file Student ID.
    # (jnv_fact_neet_results.student_id was dropped — it was only ~1.5% populated,
    # all 2024, i.e. fully redundant with the NEET-2024 file that neet24x reads.)
    neet = (neet.merge(prod["neet"], on=["test_year", "application_no"], how="left")
                .merge(n24x[["application_no", "student_id"]].rename(columns={"student_id": "n24_sid"}),
                       on="application_no", how="left"))
    neet["avanti_id"] = _coalesce(neet["prod_sid"], neet["n24_sid"])
    neet = neet.drop(columns=["prod_sid", "n24_sid"])

    # ── b12 → b10 link ────────────────────────────────────────────────────────
    cols = ["yr12", "roll12", "yr10", "roll10", "pri", "b10_src"]
    c1 = b12[(b12.yr12 == "2025") & _ne(b12.roll_number_10th)].copy()
    c1["yr10"], c1["roll10"], c1["pri"], c1["b10_src"] = _year_shift(c1.yr12, -2), c1.roll_number_10th, 1, "direct_roll"
    c2 = b12[b12.yr12 == "2024"].merge(
        p24[_ne(p24.roll_10th)][["roll_12th", "roll_10th"]], left_on="roll12", right_on="roll_12th")
    c2["yr10"], c2["roll10"], c2["pri"], c2["b10_src"] = "2022", c2.roll_10th, 2, "poojita_2024"
    xr = j24x[_ne(j24x.roll_12) & _ne(j24x.roll_10)][["roll_12", "roll_10"]].drop_duplicates()
    c3 = b12[b12.yr12 == "2024"].merge(xr, left_on="roll12", right_on="roll_12")
    c3["yr10"], c3["roll10"], c3["pri"], c3["b10_src"] = "2022", c3.roll_10, 3, "jee2024_file"
    nr = n24x[_ne(n24x.roll_12) & _ne(n24x.roll_10)][["roll_12", "roll_10"]].drop_duplicates()
    c3b = b12[b12.yr12 == "2024"].merge(nr, left_on="roll12", right_on="roll_12")
    c3b["yr10"], c3b["roll10"], c3b["pri"], c3b["b10_src"] = "2022", c3b.roll_10, 3, "neet2024_file"
    m = b12[_ne(b12.norm_name)].merge(b10[["yr10", "roll10", "norm_name"]], on="norm_name")
    m = m[m.yr10 == _year_shift(m.yr12, -2)]
    m = _unambiguous(m, ["yr12", "roll12"]).copy()
    m["pri"], m["b10_src"] = 4, "name_match"
    b10_link = _lowest_pri(pd.concat([c[cols] for c in (c1, c2, c3, c3b, m)], ignore_index=True),
                           ["yr12", "roll12"])

    # ── b12 → JEE link ──────────────────────────────────────────────────────────
    jcols = ["yr12", "roll12", "jee_yr", "jee_app_no", "pri", "jee_src"]
    pj = p24[_ne(p24.jee_app_no)][["roll_12th", "jee_app_no"]]
    j1 = (b12[b12.yr12 == "2024"].merge(pj, left_on="roll12", right_on="roll_12th")
          .merge(jee[["test_year", "application_no"]], left_on="jee_app_no", right_on="application_no"))
    j1["jee_yr"], j1["jee_app_no"], j1["pri"], j1["jee_src"] = j1.test_year, j1.application_no, 1, "poojita_2024"
    xj = j24x[_ne(j24x.roll_12)][["roll_12", "application_no"]]
    j2 = (b12[b12.yr12 == "2024"].merge(xj, left_on="roll12", right_on="roll_12")
          .merge(jee[jee.test_year == "2024"][["test_year", "application_no"]], on="application_no"))
    j2["jee_yr"], j2["jee_app_no"], j2["pri"], j2["jee_src"] = j2.test_year, j2.application_no, 2, "jee2024_file"
    mj = b12[_ne(b12.norm_father)].merge(
        jee[_ne(jee.norm_name) & _ne(jee.norm_father)][["test_year", "application_no", "norm_name", "norm_father"]],
        on=["norm_name", "norm_father"])
    y, ty = pd.to_numeric(mj.yr12, errors="coerce"), pd.to_numeric(mj.test_year, errors="coerce")
    mj = mj[(ty >= y) & (ty <= y + 2)]
    mj = _unambiguous(mj, ["yr12", "roll12", "test_year"]).copy()
    mj["jee_yr"], mj["jee_app_no"], mj["pri"], mj["jee_src"] = mj.test_year, mj.application_no, 3, "name_father_match"
    jee_link = _lowest_pri(pd.concat([j[jcols] for j in (j1, j2, mj)], ignore_index=True),
                           ["jee_app_no", "jee_yr"])

    # ── b12 → NEET link ─────────────────────────────────────────────────────────
    #   1 = Poojita · 2 = NEET-2024 file (app→12th roll) · 3 = name+father
    ncols = ["yr12", "roll12", "neet_yr", "neet_app_no", "pri", "neet_src"]
    pn = p24[_ne(p24.neet_app_no)][["roll_12th", "neet_app_no"]]
    n1 = (b12[b12.yr12 == "2024"].merge(pn, left_on="roll12", right_on="roll_12th")
          .merge(neet[["test_year", "application_no"]], left_on="neet_app_no", right_on="application_no"))
    n1["neet_yr"], n1["neet_app_no"], n1["pri"], n1["neet_src"] = n1.test_year, n1.application_no, 1, "poojita_2024"
    xn = n24x[_ne(n24x.roll_12)][["roll_12", "application_no"]]
    n2 = (b12[b12.yr12 == "2024"].merge(xn, left_on="roll12", right_on="roll_12")
          .merge(neet[neet.test_year == "2024"][["test_year", "application_no"]], on="application_no"))
    n2["neet_yr"], n2["neet_app_no"], n2["pri"], n2["neet_src"] = n2.test_year, n2.application_no, 2, "neet2024_file"
    mn = b12[_ne(b12.norm_father)].merge(
        neet[_ne(neet.norm_name) & _ne(neet.norm_father)][["test_year", "application_no", "norm_name", "norm_father"]],
        on=["norm_name", "norm_father"])
    y, ty = pd.to_numeric(mn.yr12, errors="coerce"), pd.to_numeric(mn.test_year, errors="coerce")
    mn = mn[(ty >= y) & (ty <= y + 2)]
    mn = _unambiguous(mn, ["yr12", "roll12", "test_year"]).copy()
    mn["neet_yr"], mn["neet_app_no"], mn["pri"], mn["neet_src"] = mn.test_year, mn.application_no, 3, "name_father_match"
    neet_link = _lowest_pri(pd.concat([n[ncols] for n in (n1, n2, mn)], ignore_index=True),
                            ["neet_app_no", "neet_yr"])

    # ── spine 1: 12th-anchored students ────────────────────────────────────────
    spine_12th = b12[["yr12", "roll12"]].copy()
    spine_12th = spine_12th.merge(b10_link[["yr12", "roll12", "yr10", "roll10", "b10_src"]],
                                  on=["yr12", "roll12"], how="left")
    spine_12th = pd.DataFrame({
        "student_key": "b12:" + spine_12th.yr12 + ":" + spine_12th.roll12,
        "cohort_year": spine_12th.yr12, "cohort_year_source": "12th",
        "board_12th_exam_year": spine_12th.yr12, "board_12th_roll_number": spine_12th.roll12,
        "board_10th_exam_year": spine_12th.yr10, "board_10th_roll_number": spine_12th.roll10,
        "board_10th_link_source": spine_12th.b10_src,
    })

    # ── no-12th 10th-anchored crosswalk (lead on Poojita) ──────────────────────
    p24_no12 = p24[(~_ne(p24.roll_12th)) & _ne(p24.roll_10th)][["roll_10th", "jee_app_no", "neet_app_no"]].drop_duplicates()
    linked_jee_2024 = set(jee_link[jee_link.jee_yr == "2024"].jee_app_no.dropna())
    poj_jee_apps    = set(p24_no12.jee_app_no.dropna())
    jx = j24x[_ne(j24x.roll_10)]
    jx = jx[(~jx.application_no.isin(linked_jee_2024)) & (~jx.application_no.isin(poj_jee_apps))]
    j24_no12 = pd.DataFrame({"roll_10th": jx.roll_10, "jee_app_no": jx.application_no,
                             "neet_app_no": pd.NA}).drop_duplicates()
    # NEET-2024 no-12th: anchor on 10th roll, same as the JEE-2024 file path.
    linked_neet_2024 = set(neet_link[neet_link.neet_yr == "2024"].neet_app_no.dropna())
    poj_neet_apps    = set(p24_no12.neet_app_no.dropna())
    nx = n24x[_ne(n24x.roll_10)]
    nx = nx[(~nx.application_no.isin(linked_neet_2024)) & (~nx.application_no.isin(poj_neet_apps))]
    n24_no12 = pd.DataFrame({"roll_10th": nx.roll_10, "jee_app_no": pd.NA,
                             "neet_app_no": nx.application_no}).drop_duplicates()
    no12 = pd.concat([p24_no12.assign(src="poojita_2024"),
                      j24_no12.assign(src="jee2024_file"),
                      n24_no12.assign(src="neet2024_file")], ignore_index=True)

    jee_link_p10 = no12[_ne(no12.jee_app_no)].merge(
        jee[["test_year", "application_no"]], left_on="jee_app_no", right_on="application_no")
    jee_link_p10 = pd.DataFrame({"student_key": "b10:2022:" + jee_link_p10.roll_10th,
                                 "jee_yr": jee_link_p10.test_year, "jee_app_no": jee_link_p10.jee_app_no,
                                 "jee_src": jee_link_p10.src})
    neet_link_p10 = no12[_ne(no12.neet_app_no)].merge(
        neet[["test_year", "application_no"]], left_on="neet_app_no", right_on="application_no")
    neet_link_p10 = pd.DataFrame({"student_key": "b10:2022:" + neet_link_p10.roll_10th,
                                  "neet_yr": neet_link_p10.test_year, "neet_app_no": neet_link_p10.neet_app_no,
                                  "neet_src": neet_link_p10.src})

    spb = no12.groupby("roll_10th", as_index=False).agg(src=("src", "first"))
    spine_poojita_b10 = pd.DataFrame({
        "student_key": "b10:2022:" + spb.roll_10th,
        "cohort_year": "2024", "cohort_year_source": "10th",
        "board_10th_exam_year": "2022", "board_10th_roll_number": spb.roll_10th,
        "board_10th_link_source": spb.src,
    })

    # ── spine 3: 10th frontier (2026/2027 cohorts — only 10th exists) ──────────
    fr = b10[b10.yr10.isin(["2024", "2025"])]
    spine_b10_frontier = pd.DataFrame({
        "student_key": "b10:" + fr.yr10 + ":" + fr.roll10,
        "cohort_year": _year_shift(fr.yr10, 2), "cohort_year_source": "10th",
        "board_10th_exam_year": fr.yr10, "board_10th_roll_number": fr.roll10,
        "board_10th_link_source": "spine_10th",
    })
    # JEE 2026 → 10th 2024 by name+father (unambiguous, not already claimed).
    claimed_jee = set(jee_link.jee_app_no.dropna()) | set(jee_link_p10.jee_app_no.dropna())
    bf = b10[(b10.yr10 == "2024") & _ne(b10.norm_father)]
    jf = jee[(jee.test_year == "2026") & _ne(jee.norm_name) & _ne(jee.norm_father)]
    mbf = bf.merge(jf[["test_year", "application_no", "norm_name", "norm_father"]], on=["norm_name", "norm_father"])
    mbf = mbf[~mbf.application_no.isin(claimed_jee)]
    mbf = _unambiguous(mbf, ["application_no", "test_year"])
    jee_link_b10f = pd.DataFrame({"student_key": "b10:2024:" + mbf.roll10,
                                  "jee_yr": mbf.test_year, "jee_app_no": mbf.application_no,
                                  "jee_src": "name_father_match"})

    # ── entrance-only students (JEE/NEET linked to nothing) ────────────────────
    claimed_jee_keys = set(zip(jee_link.jee_app_no, jee_link.jee_yr)) \
        | set(zip(jee_link_p10.jee_app_no, jee_link_p10.jee_yr)) \
        | set(zip(jee_link_b10f.jee_app_no, jee_link_b10f.jee_yr))
    lj = jee[~pd.Series(list(zip(jee.application_no, jee.test_year)), index=jee.index).isin(claimed_jee_keys)]
    claimed_neet_keys = set(zip(neet_link.neet_app_no, neet_link.neet_yr)) \
        | set(zip(neet_link_p10.neet_app_no, neet_link_p10.neet_yr))
    ln = neet[~pd.Series(list(zip(neet.application_no, neet.test_year)), index=neet.index).isin(claimed_neet_keys)]
    ent_cols = ["exam", "test_year", "application_no", "norm_name", "norm_father", "dob", "avanti_id"]
    ln = ln.copy(); ln["avanti_id"] = ln["avanti_id"] if "avanti_id" in ln else pd.NA
    entrance = pd.concat([lj.assign(exam="jee")[ent_cols], ln.assign(exam="neet")[ent_cols]], ignore_index=True)
    entrance["student_key"] = [_ent_key(n, f, d, ex, yr, ap, aid)
                               for n, f, d, ex, yr, ap, aid in
                               zip(entrance.norm_name, entrance.norm_father, entrance.dob,
                                   entrance.exam, entrance.test_year, entrance.application_no,
                                   entrance.avanti_id)]
    entrance_students = entrance.groupby("student_key", as_index=False).agg(cohort_year=("test_year", "min"))
    entrance_students["cohort_year_source"] = "entrance"

    # ── map every JEE / NEET record to its student_key ─────────────────────────
    jmap = pd.concat([
        pd.DataFrame({"student_key": "b12:" + jee_link.yr12 + ":" + jee_link.roll12,
                      "jee_test_year": jee_link.jee_yr, "jee_application_no": jee_link.jee_app_no,
                      "jee_link_source": jee_link.jee_src}),
        jee_link_p10.rename(columns={"jee_yr": "jee_test_year", "jee_app_no": "jee_application_no",
                                     "jee_src": "jee_link_source"}),
        jee_link_b10f.rename(columns={"jee_yr": "jee_test_year", "jee_app_no": "jee_application_no",
                                      "jee_src": "jee_link_source"}),
        pd.DataFrame({"student_key": entrance[entrance.exam == "jee"].student_key,
                      "jee_test_year": entrance[entrance.exam == "jee"].test_year,
                      "jee_application_no": entrance[entrance.exam == "jee"].application_no,
                      "jee_link_source": "entrance_identity"}),
    ], ignore_index=True)
    nmap = pd.concat([
        pd.DataFrame({"student_key": "b12:" + neet_link.yr12 + ":" + neet_link.roll12,
                      "neet_test_year": neet_link.neet_yr, "neet_application_no": neet_link.neet_app_no,
                      "neet_link_source": neet_link.neet_src}),
        neet_link_p10.rename(columns={"neet_yr": "neet_test_year", "neet_app_no": "neet_application_no",
                                      "neet_src": "neet_link_source"}),
        pd.DataFrame({"student_key": entrance[entrance.exam == "neet"].student_key,
                      "neet_test_year": entrance[entrance.exam == "neet"].test_year,
                      "neet_application_no": entrance[entrance.exam == "neet"].application_no,
                      "neet_link_source": "entrance_identity"}),
    ], ignore_index=True)

    # ── attempts: one row per (student_key, attempt_year) ──────────────────────
    au = pd.concat([
        pd.DataFrame({"student_key": jmap.student_key, "yr": jmap.jee_test_year,
                      "jee_app": jmap.jee_application_no, "jee_src": jmap.jee_link_source,
                      "neet_app": pd.NA, "neet_src": pd.NA}),
        pd.DataFrame({"student_key": nmap.student_key, "yr": nmap.neet_test_year,
                      "jee_app": pd.NA, "jee_src": pd.NA,
                      "neet_app": nmap.neet_application_no, "neet_src": nmap.neet_link_source}),
    ], ignore_index=True)
    attempts = au.groupby(["student_key", "yr"], as_index=False).agg(
        jee_application_no=("jee_app", "max"), jee_link_source=("jee_src", "max"),
        neet_application_no=("neet_app", "max"), neet_link_source=("neet_src", "max"))
    attempts = attempts.rename(columns={"yr": "attempt_year"})

    # ── per-student identity (name / dob / parents / direct avanti id) ─────────
    idc_cols = ["student_key", "src", "norm_name", "norm_father", "norm_mother", "dob", "avanti_id"]

    def _idc(df, key, src, has_dob=True, avanti_col=None):
        out = pd.DataFrame({
            "student_key": key, "src": src,
            "norm_name": df["norm_name"].values, "norm_father": df["norm_father"].values,
            "norm_mother": df["norm_mother"].values,
            "dob": df["dob"].values if has_dob else pd.NA,
            "avanti_id": df[avanti_col].values if avanti_col else pd.NA,
        })
        return out[idc_cols]

    # Attach the (yr10, roll10)→Avanti-id crosswalk. roll10x is deduped to one row per
    # pair, so a left merge is 1:1 (no row multiplication) and its keys are all non-null,
    # so a b10-less row (null yr10/roll10) can't spuriously match.
    def _x10(df):
        return df.merge(roll10x.rename(columns={"avanti_id": "x10_id"}),
                        on=["yr10", "roll10"], how="left")

    idc_b12 = _idc(b12, "b12:" + b12.yr12 + ":" + b12.roll12, "b12", has_dob=False)
    b10l = (b10_link.merge(b10, on=["yr10", "roll10"])
            .merge(p25[["roll_10th", "avanti_student_id"]], left_on="roll10", right_on="roll_10th", how="left"))
    b10l = _x10(b10l)
    idc_b10l = _idc(b10l, "b12:" + b10l.yr12 + ":" + b10l.roll12, "b10", avanti_col="avanti_student_id")
    no12b = no12[["roll_10th"]].drop_duplicates().merge(b10[b10.yr10 == "2022"], left_on="roll_10th", right_on="roll10")
    no12b = _x10(no12b)
    idc_no12 = _idc(no12b, "b10:2022:" + no12b.roll_10th, "b10")
    frx = _x10(fr)
    idc_fr = _idc(frx, "b10:" + frx.yr10 + ":" + frx.roll10, "b10")

    # 10th-score crosswalk id kept in a SEPARATE, LOWER-priority channel — NOT the pri-1
    # direct tier. Even after name-corroboration (see _corroborate_roll10x) it feeds a
    # fill-only tier so it can never override an exact name+DOB match; it only fills where
    # name/DOB (and fuzzy) found nothing, or breaks an ambiguous tie. See _match_fk tier 5.
    x10_contrib = pd.concat([
        pd.DataFrame({"student_key": "b12:" + b10l.yr12 + ":" + b10l.roll12, "roll10_avanti_id": b10l.x10_id}),
        pd.DataFrame({"student_key": "b10:2022:" + no12b.roll_10th,          "roll10_avanti_id": no12b.x10_id}),
        pd.DataFrame({"student_key": "b10:" + frx.yr10 + ":" + frx.roll10,   "roll10_avanti_id": frx.x10_id}),
    ], ignore_index=True)
    x10_contrib = x10_contrib[_ne(x10_contrib.roll10_avanti_id)].drop_duplicates("student_key")
    jmj = jmap.merge(jee, left_on=["jee_application_no", "jee_test_year"], right_on=["application_no", "test_year"])
    idc_jee = _idc(jmj, jmj.student_key, "jee", avanti_col="avanti_id")
    nmj = nmap.merge(neet, left_on=["neet_application_no", "neet_test_year"], right_on=["application_no", "test_year"])
    idc_neet = _idc(nmj, nmj.student_key, "neet", avanti_col="avanti_id")
    id_contrib = pd.concat([idc_b12, idc_b10l, idc_no12, idc_fr, idc_jee, idc_neet], ignore_index=True)

    keys = pd.Index(id_contrib.student_key.unique(), name="student_key")
    sid = pd.DataFrame(index=keys)
    sid["norm_name"]  = _coalesce_by_source(id_contrib, "norm_name", ["b12", "b10", "jee", "neet"])
    sid["norm_father"] = _coalesce_by_source(id_contrib, "norm_father", ["b12", "b10", "jee", "neet"])
    sid["dob"] = _coalesce_by_source(id_contrib, "dob", ["b10", "jee", "neet"], is_date=True)
    sid["source_avanti_student_id"] = _coalesce_by_source(id_contrib, "avanti_id", ["jee", "neet", "b10"])
    sid = sid.reset_index()
    sid = sid.merge(x10_contrib, on="student_key", how="left")  # fill-only crosswalk id

    # ── Avanti FK (priority: direct id → name+dob → name+dob-swapped → fuzzy → crosswalk)
    fk_resolved = _match_fk(sid, avanti, all_ids)

    # ── student master (disjoint spine keys → concat) ──────────────────────────
    master_cols = ["student_key", "cohort_year", "cohort_year_source",
                   "board_12th_exam_year", "board_12th_roll_number",
                   "board_10th_exam_year", "board_10th_roll_number", "board_10th_link_source"]
    master = pd.concat([spine_12th, spine_poojita_b10, spine_b10_frontier, entrance_students],
                       ignore_index=True)
    for c in master_cols:
        if c not in master:
            master[c] = pd.NA
    master = master[master_cols].drop_duplicates("student_key")

    # ── NCST (selection test): attach to resolved students, seed Avanti-linked orphans ──
    ncst_key, ncst_seed_master, ncst_seed_fk = _resolve_ncst(
        ncst, ncst_aid, sid, avanti_ncst, all_ids, fk_resolved)
    # seeded orphans join the spine as brand-new students (disjoint ncst:* keys)
    master = pd.concat([master, ncst_seed_master[master_cols]], ignore_index=True) \
               .drop_duplicates("student_key")
    fk_resolved = pd.concat([fk_resolved, ncst_seed_fk], ignore_index=True) \
                    .drop_duplicates("student_key")

    # attach FK + explode to attempts (+ NCST sitting, student-level)
    spine = master.merge(fk_resolved, on="student_key", how="left") \
                  .merge(attempts, on="student_key", how="left") \
                  .merge(ncst_key, on="student_key", how="left")
    spine["jee_test_year"]  = spine.attempt_year.where(spine.jee_application_no.notna())
    spine["neet_test_year"] = spine.attempt_year.where(spine.neet_application_no.notna())
    return spine


def _match_fk(sid: pd.DataFrame, avanti: pd.DataFrame, all_ids: set) -> pd.DataFrame:
    # Direct id validated against the FULL pk universe (a production-supplied
    # student_id may sit under a non-JNV label); name/DOB matched against the
    # tighter JNV-grade-12 `avanti` frame to avoid false positives.
    cand_cols = ["student_key", "fk", "pri", "conf", "cnt"]

    direct = sid[_ne(sid.source_avanti_student_id) & sid.source_avanti_student_id.isin(all_ids)].copy()
    direct = pd.DataFrame({"student_key": direct.student_key, "fk": direct.source_avanti_student_id,
                           "pri": 1, "conf": "direct_student_id", "cnt": 1})

    def _name_match(right_dob_col, pri, conf):
        m = sid[sid.norm_name.notna() & sid.dob.notna()].merge(
            avanti[["pk_student_id", "norm_name", right_dob_col]],
            left_on=["norm_name", "dob"], right_on=["norm_name", right_dob_col])
        g = m.groupby("student_key").agg(cnt=("pk_student_id", "nunique"),
                                         cand=("pk_student_id", "first")).reset_index()
        return pd.DataFrame({"student_key": g.student_key,
                             "fk": g.cand.where(g.cnt == 1), "pri": pri, "conf": conf, "cnt": g.cnt})

    nd  = _name_match("dob", 2, "name_dob")
    nds = _name_match("dob_swapped", 3, "name_dob_swapped")

    # ── fuzzy tier (LAST RESORT): exact-DOB block + token-Jaccard on name ──────
    # Only for student_keys still unresolved by direct / name_dob / name_dob_swapped.
    # DOB-blocked → tiny candidate set per name → low false-positive risk. Keeps
    # the same cnt==1 unambiguous discipline (>1 distinct pk ⇒ FK withheld). See
    # the _fuzzy_ok note above for what it does and doesn't catch.
    resolved = set(pd.concat([direct, nd, nds]).loc[lambda d: d.fk.notna(), "student_key"])
    fsid = sid[sid.norm_name.notna() & sid.dob.notna() & ~sid.student_key.isin(resolved)]
    fm = fsid.merge(avanti[["pk_student_id", "norm_name", "dob"]], on="dob", suffixes=("", "_av"))
    fm = fm[[_fuzzy_ok(n, a) for n, a in zip(fm.norm_name, fm.norm_name_av)]]
    fg = fm.groupby("student_key").agg(cnt=("pk_student_id", "nunique"),
                                       cand=("pk_student_id", "first")).reset_index()
    fz = pd.DataFrame({"student_key": fg.student_key, "fk": fg.cand.where(fg.cnt == 1),
                       "pri": 4, "conf": "name_dob_fuzzy", "cnt": fg.cnt})

    # ── 10th-score crosswalk tier (pri 5, LOWEST — fill-only) ──────────────────
    # Trusted BELOW every name/DOB tier: the sheet is name-corroborated upstream
    # (_corroborate_roll10x drops rows whose board name disagrees with the id), but it can
    # still be row-misaligned, so it only fills where nothing else matched or breaks an
    # ambiguous tie — it can never override an exact name+DOB match. Validated vs all_ids.
    x10 = pd.DataFrame(columns=cand_cols)
    if "roll10_avanti_id" in sid:
        xr = sid[_ne(sid.roll10_avanti_id) & sid.roll10_avanti_id.isin(all_ids)]
        x10 = pd.DataFrame({"student_key": xr.student_key, "fk": xr.roll10_avanti_id,
                            "pri": 5, "conf": "roll10_crosswalk", "cnt": 1})

    cand = pd.concat([direct[cand_cols], nd[cand_cols], nds[cand_cols], fz[cand_cols], x10[cand_cols]],
                     ignore_index=True)
    # prefer candidates with a real fk (fk-present first), then lowest priority.
    cand["fk_isnull"] = cand.fk.isna()
    cand = cand.sort_values(["student_key", "fk_isnull", "pri"]).drop_duplicates("student_key", keep="first")
    cand["match_confidence"] = cand.conf.where(cand.fk.notna(),
                                               other=pd.Series("ambiguous", index=cand.index).where(cand.cnt > 1))
    return cand.rename(columns={"fk": "fk_avanti_student_id", "cnt": "match_count"})[
        ["student_key", "fk_avanti_student_id", "match_confidence", "match_count"]]


def _enrich(spine: pd.DataFrame, marks: dict) -> pd.DataFrame:
    df = (spine
          .merge(marks["b10_marks"], on=["board_10th_exam_year", "board_10th_roll_number"], how="left")
          .merge(marks["b12_marks"], on=["board_12th_exam_year", "board_12th_roll_number"], how="left")
          .merge(marks["jee_results"], on=["jee_test_year", "jee_application_no"], how="left")
          .merge(marks["neet_results"], on=["neet_test_year", "neet_application_no"], how="left")
          .merge(marks["program_lookup"], on="fk_avanti_student_id", how="left"))

    # Stage-availability flags — STUDENT-LEVEL (true if the student has that stage in
    # ANY of their attempt-year rows), broadcast across the student's rows so a single
    # row is enough to filter on (e.g. WHERE has_10th_data AND has_12th_data AND
    # (has_jee_mains_data OR has_neet_data)).
    flags = {
        "has_ncst_data":      df["ncst_test_year"].notna(),
        "has_10th_data":      df["board_10th_exam_year"].notna(),
        "has_12th_data":      df["board_12th_exam_year"].notna(),
        "has_jee_mains_data": df["jee_application_no"].notna(),
        "has_jee_adv_data":   df[["jee_adv_all_india_rank", "jee_adv_category_rank",
                                  "jee_adv_prep_category_rank"]].notna().any(axis=1),
        "has_neet_data":      df["neet_application_no"].notna(),
    }
    for col, s in flags.items():
        df[col] = s.astype(int).groupby(df["student_key"]).transform("max").astype(bool)

    for c in FINAL_COLS:
        if c not in df:
            df[c] = pd.NA
    return df[FINAL_COLS]


# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    from google.cloud import bigquery
    from google.cloud.bigquery import LoadJobConfig, WriteDisposition
    from google.cloud.exceptions import NotFound

    parser = argparse.ArgumentParser(
        description="Build jnv_student_outcome_mapping. Default rebuilds ALL cohorts in one pass; "
                    "--year refreshes just one cohort idempotently.")
    parser.add_argument("--year", default=None,
                        help="refresh only this cohort_year (idempotent delete+insert). "
                             "Omit to rebuild the whole table.")
    args = parser.parse_args()
    year = str(args.year) if args.year else None

    for f in (POOJITA, TENTH_SCORE, JEE_2025_RAW.local_path, JEE_2024_RAW.local_path, NEET_2024_RAW.local_path):
        if not f.exists():
            print(f"ERROR: reference file not found: {f}")
            sys.exit(1)

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print("Reading reference sheets (local Excel) ...")
    refs = _read_refs()
    print("Reading source frames from BigQuery (aggregated) ...")
    src = _read_sources(client)
    avanti, all_ids, id_names, avanti_ncst = _read_avanti(client)
    prod = _read_prod_fk(client)
    marks = _read_marks(client)
    ncst = _read_ncst(client)
    ncst_aid = _read_ncst_avanti_id()

    # Name-corroborate the 10th-score crosswalk against dim ids (no new BQ query — reuses
    # the id×name frame from _read_avanti) so a row-misaligned sheet row can't inject a
    # wrong link. Feeds the fill-only crosswalk tier in _match_fk.
    refs["roll10x"] = _corroborate_roll10x(refs["roll10x"], src["b10"], id_names)

    # Resolve the entire cross-year identity universe ONCE; slice afterwards.
    print(f"\nResolving student identities (pandas) ...")
    out = _enrich(_resolve(src, refs, avanti, prod, all_ids, ncst, ncst_aid, avanti_ncst), marks)

    if year is None:
        print(f"\nFull rebuild → avantifellows.external_data_sources.jnv_student_outcome_mapping: {len(out):,} rows, {out.student_key.nunique():,} students")
        client.load_table_from_dataframe(
            out, "avantifellows.external_data_sources.jnv_student_outcome_mapping",
            job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
        ).result()
    else:
        out = out[out.cohort_year == year]
        print(f"\nRefreshing cohort {year} → avantifellows.external_data_sources.jnv_student_outcome_mapping: {len(out):,} rows, "
              f"{out.student_key.nunique():,} students")
        # create fresh if table is absent / old schema; else idempotent delete+insert.
        try:
            cols = {f.name for f in client.get_table("avantifellows.external_data_sources.jnv_student_outcome_mapping").schema}
            new_schema = {"cohort_year", "student_key"} <= cols
        except NotFound:
            new_schema = False
        if not new_schema:
            print("  (table absent or old schema — creating fresh with just this cohort)")
            client.load_table_from_dataframe(
                out, "avantifellows.external_data_sources.jnv_student_outcome_mapping",
                job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
            ).result()
        else:
            client.query(f"DELETE FROM `avantifellows.external_data_sources.jnv_student_outcome_mapping` WHERE cohort_year = '{year}'").result()
            # force df → existing table schema so an all-null column can't drift the type.
            client.load_table_from_dataframe(
                out, "avantifellows.external_data_sources.jnv_student_outcome_mapping",
                job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_APPEND,
                                         schema=client.get_table("avantifellows.external_data_sources.jnv_student_outcome_mapping").schema),
            ).result()

    # coverage summary (all cohorts in the table)
    summary_sql = f"""
        SELECT cohort_year,
            COUNT(*)                                  AS total_rows,
            COUNT(DISTINCT student_key)               AS students,
            COUNTIF(ncst_test_year IS NOT NULL)       AS has_ncst,
            COUNTIF(board_10th_exam_year IS NOT NULL) AS has_b10,
            COUNTIF(board_12th_exam_year IS NOT NULL) AS has_b12,
            COUNTIF(jee_test_year  IS NOT NULL)       AS has_jee,
            COUNTIF(neet_test_year IS NOT NULL)       AS has_neet,
            COUNTIF(fk_avanti_student_id IS NOT NULL) AS has_fk
        FROM `avantifellows.external_data_sources.jnv_student_outcome_mapping` GROUP BY 1 ORDER BY cohort_year
    """
    print(f"\n{'cohort':<7} {'rows':>8} {'students':>9} {'ncst':>7} {'b10':>8} {'b12':>8} "
          f"{'jee':>8} {'neet':>8} {'fk':>8}")
    print("-" * 78)
    for r in client.query(summary_sql).result():
        print(f"  {r.cohort_year:<5}  {r.total_rows:>8,}  {r.students:>9,}  {r.has_ncst:>7,}  {r.has_b10:>8,}  "
              f"{r.has_b12:>8,}  {r.has_jee:>8,}  {r.has_neet:>8,}  {r.has_fk:>8,}")
    print("\nDone.")


if __name__ == "__main__":
    main()
