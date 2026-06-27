#!/usr/bin/env python3
"""
Build (or refresh) the jnv_student_id_mapping table in BigQuery.

For each JNV fact table that contains per-student data, this script tries to
identify the corresponding Avanti student via dim_student / dim_student_historical
and writes the result to:

    avantifellows.external_data_sources.jnv_student_id_mapping

Matching strategy per table:

  jnv_fact_jee_results
      name_dob — UPPER-trimmed full name + DOB (format: DDMMYYYY)

  jnv_fact_neet_results
      direct_student_id — jnv.student_id = dim.pk_student_id (when populated)
      name_dob          — fallback for rows without a direct student_id

  jnv_fact_board_results_10th
      name_dob_parent   — name + DOB + (father OR mother name matches)
      name_dob          — name + DOB only (when parent names don't agree)
      name_dob_swapped  — name + DOB with day/month swapped (DD/MM transposition in dim_student)
      name_dob_year_off — name + DOB, exam_year ± 1 (grade 12 year entered incorrectly)
      name_fuzzy_dob    — exact DOB + edit distance ≤ 2 on name (spelling variants/typos)
      Scoped to JNV CoE/Nodal students in grade 12, academic years 2023-2024 to 2026-2027.
      DOB format in source: DDMMYYYY (no separator, e.g. "31032007")

  jnv_fact_board_results_12th
      roll10_chain      — 2025 only: follow roll_number_10th → 10th mapping
      name_parent_only  — name + (father OR mother) name; no DOB (DOB is NULL
                          in all source files for this table)

`match_count` records how many distinct Avanti students matched. Values > 1
mean the match is ambiguous — fk_avanti_student_id is set to NULL for those
rows so they never silently mislead downstream queries.

After reviewing match quality, add the FK column to the fact tables using
add_fk_to_fact_tables.py (to be written once mapping quality is confirmed).

Usage:
    python3 scripts/build_student_id_mapping.py

Prerequisites:
    pip install google-cloud-bigquery  (already in requirements.txt)
    Application Default Credentials with bigquery.jobs.create + read access
    to avantifellows.production_dbt_final and write access to
    avantifellows.external_data_sources.
"""

from google.cloud import bigquery

from sources import BQ_DATASET, BQ_LOCATION, BQ_PROJECT

_DIM_DATASET = "production_dbt_final"
_DIM_STUDENT = f"`{BQ_PROJECT}.{_DIM_DATASET}.dim_student`"
_DIM_STUDENT_HIST = f"`{BQ_PROJECT}.{_DIM_DATASET}.dim_student_historical`"

_MAPPING_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.jnv_student_id_mapping"
_EDS = f"{BQ_PROJECT}.{BQ_DATASET}"

# ── SQL helpers ────────────────────────────────────────────────────────────────

def _norm(col: str) -> str:
    """Uppercase + collapse whitespace."""
    return f"UPPER(TRIM(REGEXP_REPLACE({col}, r'\\s+', ' ')))"


def _parse_dob(col: str) -> str:
    """
    Try common Indian DOB string formats.
    Board 10th source uses DDMMYYYY (no separator) — that format is listed first
    so it wins when multiple might match.
    """
    fmts = [
        "%d%m%Y",    # DDMMYYYY — board results 10th
        "%d-%m-%Y",  # DD-MM-YYYY — JEE / NEET (most common)
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%d %m %Y",
    ]
    attempts = "\n        ".join(f"SAFE.PARSE_DATE('{f}', {col})," for f in fmts)
    return f"COALESCE(\n        {attempts}\n        NULL\n    )"


# ── Main SQL ───────────────────────────────────────────────────────────────────

_BUILD_SQL = f"""
CREATE OR REPLACE TABLE `{_MAPPING_TABLE}`
OPTIONS (description = 'Maps each JNV fact-table row to an Avanti pk_student_id. Built by build_student_id_mapping.py.')
AS

-- ── 1. Unified student pool (deduped across all academic years) ──────────────
WITH raw_students AS (
    SELECT pk_student_id, student_full_name, date_of_birth, father_name, mother_name
    FROM {_DIM_STUDENT}
    UNION ALL
    SELECT pk_student_id, student_full_name, date_of_birth, father_name, mother_name
    FROM {_DIM_STUDENT_HIST}
),
student_pool AS (
    SELECT DISTINCT
        pk_student_id,
        {_norm('student_full_name')}          AS norm_name,
        date_of_birth,
        {_norm('COALESCE(father_name, "")')}  AS norm_father,
        {_norm('COALESCE(mother_name, "")')}  AS norm_mother
    FROM raw_students
    WHERE student_full_name IS NOT NULL
      AND date_of_birth IS NOT NULL
),

-- ── 2. JEE: match on name + DOB ──────────────────────────────────────────────
jee_students AS (
    SELECT DISTINCT
        'jnv_fact_jee_results'                 AS source_table,
        CONCAT(test_year, '_', application_no) AS source_grain_key,
        {_norm('student_full_name')}           AS norm_name,
        {_parse_dob('dob')}                    AS parsed_dob
    FROM `{_EDS}.jnv_fact_jee_results`
    WHERE student_full_name IS NOT NULL
),
jee_matched AS (
    SELECT
        j.source_table,
        j.source_grain_key,
        COUNT(DISTINCT s.pk_student_id)  AS match_count,
        ANY_VALUE(s.pk_student_id)       AS fk_avanti_student_id,
        'name_dob'                       AS match_confidence
    FROM jee_students j
    JOIN student_pool s
        ON  j.norm_name  = s.norm_name
        AND j.parsed_dob = s.date_of_birth
    GROUP BY 1, 2
),

-- ── 3. NEET: direct student_id first, then name + DOB fallback ───────────────
neet_students AS (
    SELECT DISTINCT
        'jnv_fact_neet_results'                AS source_table,
        CONCAT(test_year, '_', application_no) AS source_grain_key,
        student_id,
        {_norm('student_full_name')}           AS norm_name,
        {_parse_dob('dob')}                    AS parsed_dob
    FROM `{_EDS}.jnv_fact_neet_results`
    WHERE student_full_name IS NOT NULL
),
neet_direct AS (
    SELECT
        n.source_table,
        n.source_grain_key,
        1                    AS match_count,
        n.student_id         AS fk_avanti_student_id,
        'direct_student_id'  AS match_confidence
    FROM neet_students n
    JOIN student_pool s ON n.student_id = s.pk_student_id
    WHERE n.student_id IS NOT NULL
),
neet_name_dob AS (
    SELECT
        n.source_table,
        n.source_grain_key,
        COUNT(DISTINCT s.pk_student_id)  AS match_count,
        ANY_VALUE(s.pk_student_id)       AS fk_avanti_student_id,
        'name_dob'                       AS match_confidence
    FROM neet_students n
    LEFT JOIN neet_direct d USING (source_table, source_grain_key)
    JOIN student_pool s
        ON  n.norm_name  = s.norm_name
        AND n.parsed_dob = s.date_of_birth
    WHERE d.source_grain_key IS NULL
    GROUP BY 1, 2
),
neet_matched AS (
    SELECT * FROM neet_direct
    UNION ALL SELECT * FROM neet_name_dob
),

-- ── 4. Board 10th: four-pass matching ───────────────────────────────────────
--
--   Pass 1 (name_dob / name_dob_parent): exact name + DOB.
--     Confidence escalates to name_dob_parent when a parent name also agrees.
--   Pass 2 (name_dob_swapped): name + DOB with day/month swapped on the
--     Avanti side — covers a systematic DD/MM transposition in dim_student.
--   Pass 3 (name_dob_year_off): exact name + DOB but exam_year ± 1 — covers
--     cases where the grade 12 year was entered incorrectly in Avanti.
--   Pass 4 (name_fuzzy_dob): exact DOB + edit distance ≤ 2 on the name —
--     recovers spelling variants and single-character typos.
--
--   Each pass only touches rows not already resolved by prior passes.
--   Academic years scoped to current JNV CoE/Nodal cohorts in grade 12:
--   2023-2024, 2024-2025, 2025-2026, 2026-2027.
--   exam_year = grade-12 academic year end − 2  (e.g. 2025-2026 → 2024).

board_10th_avanti AS (
    SELECT DISTINCT pk_student_id, date_of_birth, academic_year,
        {_norm('student_full_name')}          AS norm_name,
        {_norm('COALESCE(father_name, "")')}  AS norm_father,
        {_norm('COALESCE(mother_name, "")')}  AS norm_mother,
        CAST(CAST(RIGHT(academic_year, 4) AS INT64) - 2 AS STRING) AS expected_exam_year,
        SAFE.DATE(
            EXTRACT(YEAR  FROM date_of_birth),
            EXTRACT(DAY   FROM date_of_birth),
            EXTRACT(MONTH FROM date_of_birth)
        ) AS dob_swapped
    FROM {_DIM_STUDENT}
    WHERE (LOWER(COALESCE(student_school, '')) LIKE '%jnv%'
        OR LOWER(COALESCE(student_school, '')) LIKE '%navodaya%')
      AND student_grade = 12
      AND academic_year IN ('2023-2024', '2024-2025', '2025-2026', '2026-2027')
      AND student_full_name IS NOT NULL
      AND date_of_birth IS NOT NULL
    UNION ALL
    SELECT DISTINCT pk_student_id, date_of_birth, academic_year,
        {_norm('student_full_name')}          AS norm_name,
        {_norm('COALESCE(father_name, "")')}  AS norm_father,
        {_norm('COALESCE(mother_name, "")')}  AS norm_mother,
        CAST(CAST(RIGHT(academic_year, 4) AS INT64) - 2 AS STRING) AS expected_exam_year,
        SAFE.DATE(
            EXTRACT(YEAR  FROM date_of_birth),
            EXTRACT(DAY   FROM date_of_birth),
            EXTRACT(MONTH FROM date_of_birth)
        ) AS dob_swapped
    FROM {_DIM_STUDENT_HIST}
    WHERE (LOWER(COALESCE(student_school, '')) LIKE '%jnv%'
        OR LOWER(COALESCE(student_school, '')) LIKE '%navodaya%')
      AND student_grade = 12
      AND academic_year IN ('2023-2024', '2024-2025', '2025-2026', '2026-2027')
      AND student_full_name IS NOT NULL
      AND date_of_birth IS NOT NULL
),
board_10th_src AS (
    SELECT DISTINCT
        exam_year,
        CONCAT(exam_year, '_', roll_number)    AS source_grain_key,
        roll_number,
        {_norm('student_name')}                AS norm_name,
        SAFE.PARSE_DATE('%d%m%Y', LPAD(date_of_birth, 8, '0')) AS parsed_dob,
        {_norm('COALESCE(father_name, "")')}   AS norm_father,
        {_norm('COALESCE(mother_name, "")')}   AS norm_mother
    FROM `{_EDS}.jnv_fact_board_results_10th`
    WHERE student_name IS NOT NULL
),

-- Pass 1: exact name + DOB (with parent-name confidence escalation)
board_10th_p1 AS (
    SELECT
        'jnv_fact_board_results_10th'    AS source_table,
        b.source_grain_key,
        COUNT(DISTINCT a.pk_student_id)  AS match_count,
        ANY_VALUE(a.pk_student_id)       AS fk_avanti_student_id,
        CASE
            WHEN LOGICAL_OR(
                (b.norm_father != '' AND b.norm_father = a.norm_father)
                OR (b.norm_mother != '' AND b.norm_mother = a.norm_mother)
            ) THEN 'name_dob_parent'
            ELSE 'name_dob'
        END AS match_confidence
    FROM board_10th_src b
    JOIN board_10th_avanti a
        ON  a.norm_name          = b.norm_name
        AND a.date_of_birth      = b.parsed_dob
        AND a.expected_exam_year = b.exam_year
    GROUP BY 1, 2
),

-- Pass 2: name + swapped DOB
board_10th_p2 AS (
    SELECT
        'jnv_fact_board_results_10th'    AS source_table,
        b.source_grain_key,
        COUNT(DISTINCT a.pk_student_id)  AS match_count,
        ANY_VALUE(a.pk_student_id)       AS fk_avanti_student_id,
        'name_dob_swapped'               AS match_confidence
    FROM board_10th_src b
    LEFT JOIN board_10th_p1 p1 USING (source_grain_key)
    JOIN board_10th_avanti a
        ON  a.norm_name          = b.norm_name
        AND a.dob_swapped        = b.parsed_dob
        AND a.expected_exam_year = b.exam_year
    WHERE p1.source_grain_key IS NULL
    GROUP BY 1, 2
),

-- Pass 3: exact name + DOB, exam_year ± 1
board_10th_p3 AS (
    SELECT
        'jnv_fact_board_results_10th'    AS source_table,
        b.source_grain_key,
        COUNT(DISTINCT a.pk_student_id)  AS match_count,
        ANY_VALUE(a.pk_student_id)       AS fk_avanti_student_id,
        'name_dob_year_off'              AS match_confidence
    FROM board_10th_src b
    LEFT JOIN board_10th_p1 p1 USING (source_grain_key)
    LEFT JOIN board_10th_p2 p2 USING (source_grain_key)
    JOIN board_10th_avanti a
        ON  a.norm_name     = b.norm_name
        AND a.date_of_birth = b.parsed_dob
        AND CAST(a.expected_exam_year AS INT64)
            IN (CAST(b.exam_year AS INT64) - 1, CAST(b.exam_year AS INT64) + 1)
    WHERE p1.source_grain_key IS NULL AND p2.source_grain_key IS NULL
    GROUP BY 1, 2
),

-- Pass 4: exact DOB + fuzzy name (edit distance 1–2)
board_10th_p4 AS (
    SELECT
        'jnv_fact_board_results_10th'    AS source_table,
        b.source_grain_key,
        COUNT(DISTINCT a.pk_student_id)  AS match_count,
        ANY_VALUE(a.pk_student_id)       AS fk_avanti_student_id,
        'name_fuzzy_dob'                 AS match_confidence
    FROM board_10th_src b
    LEFT JOIN board_10th_p1 p1 USING (source_grain_key)
    LEFT JOIN board_10th_p2 p2 USING (source_grain_key)
    LEFT JOIN board_10th_p3 p3 USING (source_grain_key)
    JOIN board_10th_avanti a
        ON  a.date_of_birth      = b.parsed_dob
        AND a.expected_exam_year = b.exam_year
        AND EDIT_DISTANCE(a.norm_name, b.norm_name) BETWEEN 1 AND 2
    WHERE p1.source_grain_key IS NULL
      AND p2.source_grain_key IS NULL
      AND p3.source_grain_key IS NULL
    GROUP BY 1, 2
),

board_10th_matched AS (
    SELECT * FROM board_10th_p1
    UNION ALL SELECT * FROM board_10th_p2
    UNION ALL SELECT * FROM board_10th_p3
    UNION ALL SELECT * FROM board_10th_p4
),

-- ── 5. Board 12th: DOB is NULL in all source files ───────────────────────────
--
--   Strategy A (2025 only): chain via roll_number_10th to the 10th mapping.
--   The schema note says:
--       roll_number_10th = roll_number in board_results_10th for (exam_year - 2)
--
--   Strategy B (all years): match on name + (father OR mother) without DOB.
--   Confidence is lower — flagged as 'name_parent_only'.
--   Only unambiguous 1:1 matches are kept.

board_12th_students AS (
    SELECT DISTINCT
        'jnv_fact_board_results_12th'          AS source_table,
        CONCAT(exam_year, '_', roll_number)    AS source_grain_key,
        exam_year,
        roll_number,
        roll_number_10th,
        {_norm('student_name')}                AS norm_name,
        {_norm('COALESCE(father_name, "")')}   AS norm_father,
        {_norm('COALESCE(mother_name, "")')}   AS norm_mother
    FROM `{_EDS}.jnv_fact_board_results_12th`
    WHERE student_name IS NOT NULL
),

-- 5A. Chain via roll_number_10th (exam_year 2025 → looks up exam_year 2023 in 10th)
board_12th_chain AS (
    SELECT
        b12.source_table,
        b12.source_grain_key,
        m.match_count,
        m.fk_avanti_student_id,
        'roll10_chain'  AS match_confidence
    FROM board_12th_students b12
    JOIN board_10th_matched m
        ON  m.source_table      = 'jnv_fact_board_results_10th'
        AND m.source_grain_key  = CONCAT(
                CAST(CAST(b12.exam_year AS INT64) - 2 AS STRING),
                '_',
                b12.roll_number_10th
            )
    WHERE b12.roll_number_10th IS NOT NULL
      AND b12.roll_number_10th != ''
),

-- 5B. Name + parent names (no DOB). Pool for 12th has no DOB constraint.
student_pool_no_dob AS (
    SELECT DISTINCT
        pk_student_id,
        {_norm('student_full_name')}          AS norm_name,
        {_norm('COALESCE(father_name, "")')}  AS norm_father,
        {_norm('COALESCE(mother_name, "")')}  AS norm_mother
    FROM raw_students
    WHERE student_full_name IS NOT NULL
),
board_12th_name_parent AS (
    SELECT
        b.source_table,
        b.source_grain_key,
        COUNT(DISTINCT s.pk_student_id)  AS match_count,
        ANY_VALUE(s.pk_student_id)       AS fk_avanti_student_id,
        'name_parent_only'               AS match_confidence
    FROM board_12th_students b
    -- Skip rows already resolved by chain
    LEFT JOIN board_12th_chain c USING (source_table, source_grain_key)
    JOIN student_pool_no_dob s
        ON  b.norm_name   = s.norm_name
        AND (
            (b.norm_father != '' AND b.norm_father = s.norm_father)
            OR
            (b.norm_mother != '' AND b.norm_mother = s.norm_mother)
        )
    WHERE c.source_grain_key IS NULL
    GROUP BY 1, 2
),
board_12th_matched AS (
    SELECT * FROM board_12th_chain
    UNION ALL SELECT * FROM board_12th_name_parent
),

-- ── 6. Union all sources ─────────────────────────────────────────────────────
all_matched AS (
    SELECT * FROM jee_matched
    UNION ALL SELECT * FROM neet_matched
    UNION ALL SELECT * FROM board_10th_matched
    UNION ALL SELECT * FROM board_12th_matched
)

SELECT
    source_table,
    source_grain_key,
    -- NULL out ambiguous matches so they never silently mislead downstream queries
    CASE WHEN match_count = 1 THEN fk_avanti_student_id ELSE NULL END
        AS fk_avanti_student_id,
    match_confidence,
    match_count
FROM all_matched
"""

# ── Runner ─────────────────────────────────────────────────────────────────────

def build(client: bigquery.Client) -> None:
    print(f"Building {_MAPPING_TABLE} ...")
    job = client.query(_BUILD_SQL)
    job.result()

    summary_sql = f"""
    SELECT
        source_table,
        match_confidence,
        match_count > 1          AS is_ambiguous,
        COUNT(*)                 AS rows
    FROM `{_MAPPING_TABLE}`
    GROUP BY 1, 2, 3
    ORDER BY 1, 3, 2
    """
    rows = list(client.query(summary_sql).result())

    print(f"\n{'source_table':<40} {'confidence':<22} {'ambiguous':<10} {'rows':>8}")
    print("-" * 85)
    for r in rows:
        print(f"{r.source_table:<40} {r.match_confidence:<22} {str(r.is_ambiguous):<10} {r.rows:>8}")
    print(f"\nDone. Table written to {_MAPPING_TABLE}")


def main() -> None:
    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)
    build(client)


if __name__ == "__main__":
    main()
