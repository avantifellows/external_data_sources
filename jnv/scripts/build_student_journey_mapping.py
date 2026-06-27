#!/usr/bin/env python3
"""
Build jnv_student_journey_mapping: a unified cross-table student identity table
for JNV students across board_10th, board_12th, JEE, and NEET.

Grain: (board_12th_roll_number, board_12th_exam_year, jee_test_year, neet_test_year)
       — retakers get additional rows (different test_year on same board_12th anchor).

Linkage priority:
  board_12th → board_10th:
    1. roll_number_10th column (board_12th 2025 only)
    2. Poojita 2024 sheet  (2024 cohort, source of truth)
    3. Name + year match   (fallback)

  board_12th → JEE / NEET:
    1. Poojita 2024 sheet  (2024 cohort)
    2. Name + state match  (all cohorts, unambiguous only)

  Avanti FK:
    1. direct_student_id   (JEE 2025 avanti_studentid, NEET student_id, Poojita 2025 avanti_id)
    2. name + DOB          (from board_10th — richest identity source)

Usage:
    python3 scripts/build_student_journey_mapping.py
"""

import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_PROJECT, BQ_DATASET, BQ_LOCATION

_EDS  = f"`{BQ_PROJECT}.{BQ_DATASET}`"
_DIM  = f"`{BQ_PROJECT}.production_dbt_final.dim_student`"
_DIMH = f"`{BQ_PROJECT}.production_dbt_final.dim_student_historical`"
_OUT  = f"{BQ_PROJECT}.{BQ_DATASET}.jnv_student_journey_mapping"

_POOJITA = (
    Path(__file__).resolve().parent.parent
    / "raw" / "mapping_files"
    / "12th & 10 Marks Mapping (Poojita Data).xlsx"
)
_JEE_2025_RAW = (
    Path(__file__).resolve().parent.parent
    / "raw" / "jee_mains"
    / "JEE 2025 - All JNV Candidates.xlsx"
)


def _upload_reference_tables(client) -> tuple[str, str, str]:
    """
    Upload Poojita 2024, Poojita 2025, and JEE 2025 avanti_studentid mapping
    to temp BQ tables. Returns (tmp24, tmp25, tmp_jee25_avanti).
    """
    ts = int(time.time())
    tmp24            = f"{BQ_PROJECT}.{BQ_DATASET}._tmp_poojita_24_{ts}"
    tmp25            = f"{BQ_PROJECT}.{BQ_DATASET}._tmp_poojita_25_{ts}"
    tmp_jee25_avanti = f"{BQ_PROJECT}.{BQ_DATASET}._tmp_jee25_avanti_{ts}"

    from google.cloud.bigquery import LoadJobConfig, WriteDisposition

    # ── Poojita 2024 sheet ─────────────────────────────────────────────────────
    df24 = pd.read_excel(_POOJITA, sheet_name="Mapped Data (2024 Students)", dtype=str)
    df24 = df24.rename(columns={
        "JEE application No":  "jee_app_no",
        "NEET Application No": "neet_app_no",
        "10th Roll No":        "roll_10th",
        "12th Roll No":        "roll_12th",
    })[["jee_app_no", "neet_app_no", "roll_10th", "roll_12th"]].copy()
    for col in df24.columns:
        df24[col] = df24[col].str.strip().replace("nan", pd.NA)
    df24 = df24[df24[["jee_app_no", "neet_app_no", "roll_10th", "roll_12th"]].notna().any(axis=1)]
    client.load_table_from_dataframe(
        df24, tmp24,
        job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
    ).result()
    print(f"  Uploaded Poojita 2024: {len(df24):,} rows → {tmp24}")

    # ── Poojita 2025 sheet ─────────────────────────────────────────────────────
    df25 = pd.read_excel(_POOJITA, sheet_name="Mapped Data (2025 Students)", dtype=str)
    df25 = df25.rename(columns={
        "Avanti Student ID": "avanti_student_id",
        "10th Roll Number":  "roll_10th",
    })[["avanti_student_id", "roll_10th"]].copy()
    for col in df25.columns:
        df25[col] = df25[col].str.strip().replace("nan", pd.NA)
    df25 = df25[df25["avanti_student_id"].notna() & df25["roll_10th"].notna()]
    client.load_table_from_dataframe(
        df25, tmp25,
        job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
    ).result()
    print(f"  Uploaded Poojita 2025: {len(df25):,} rows → {tmp25}")

    # ── JEE 2025 avanti_studentid → application_no mapping ────────────────────
    # The All JNV Candidates file carries avanti_studentid for all 12,103 rows;
    # we use this for direct FK matching without adding it as a permanent JEE column.
    df_jee25 = pd.read_excel(
        _JEE_2025_RAW,
        sheet_name="JEE 2025 - All JNV Candidates",
        usecols=["JEEApplicationNumber", "avanti_studentid"],
        dtype=str,
    )
    df_jee25 = df_jee25.rename(columns={
        "JEEApplicationNumber": "application_no",
        "avanti_studentid":     "avanti_student_id",
    })
    for col in df_jee25.columns:
        df_jee25[col] = df_jee25[col].str.strip().replace("nan", pd.NA)
    df_jee25 = df_jee25[df_jee25["avanti_student_id"].notna() & df_jee25["application_no"].notna()]
    client.load_table_from_dataframe(
        df_jee25, tmp_jee25_avanti,
        job_config=LoadJobConfig(write_disposition=WriteDisposition.WRITE_TRUNCATE),
    ).result()
    print(f"  Uploaded JEE 2025 avanti_studentid map: {len(df_jee25):,} rows → {tmp_jee25_avanti}")

    return tmp24, tmp25, tmp_jee25_avanti


def _build_sql(tmp24: str, tmp25: str, tmp_jee25_avanti: str) -> str:
    return f"""
-- ── Source tables (one row per student per exam) ──────────────────────────────
WITH b12_raw AS (
    SELECT DISTINCT
        exam_year                                                                    AS yr12,
        roll_number                                                                  AS roll12,
        UPPER(TRIM(REGEXP_REPLACE(student_name,            r'\\s+', ' ')))         AS norm_name,
        UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' ')))        AS norm_father,
        UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' ')))        AS norm_mother,
        roll_number_10th
    FROM {_EDS}.jnv_fact_board_results_12th
    WHERE roll_number IS NOT NULL AND student_name IS NOT NULL
),
b12 AS (
    -- deduplicate (same roll can appear across subjects)
    SELECT yr12, roll12,
           ANY_VALUE(norm_name)   AS norm_name,
           ANY_VALUE(norm_father) AS norm_father,
           ANY_VALUE(norm_mother) AS norm_mother,
           ANY_VALUE(roll_number_10th) AS roll_number_10th
    FROM b12_raw
    GROUP BY 1, 2
),
b10 AS (
    SELECT DISTINCT
        exam_year                                                           AS yr10,
        roll_number                                                         AS roll10,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(student_name, r'\\s+', ' ')))) AS norm_name,
        ANY_VALUE(SAFE.PARSE_DATE('%d%m%Y', LPAD(date_of_birth, 8, '0'))) AS dob,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' ')))) AS norm_father,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' ')))) AS norm_mother
    FROM {_EDS}.jnv_fact_board_results_10th
    WHERE roll_number IS NOT NULL AND student_name IS NOT NULL
    GROUP BY 1, 2
),

-- ── Reference tables (must precede CTEs that join them) ───────────────────────
poojita24     AS (SELECT * FROM `{tmp24}`),
poojita25     AS (SELECT * FROM `{tmp25}`),
-- JEE 2025 avanti_studentid: not stored as a permanent JEE column; joined here for FK matching only
jee25_avanti  AS (SELECT * FROM `{tmp_jee25_avanti}`),

jee AS (
    SELECT DISTINCT
        test_year,
        application_no,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(student_full_name,''), r'\\s+', ' ')))) AS norm_name,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(student_state,    ''), r'\\s+', ' ')))) AS norm_state,
        ANY_VALUE(COALESCE(
            SAFE.PARSE_DATE('%d-%m-%Y', dob),
            SAFE.PARSE_DATE('%Y-%m-%d', dob),
            SAFE.PARSE_DATE('%d%m%Y',   dob)
        ))                                                                                    AS dob,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))))       AS norm_father,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))))       AS norm_mother,
        ANY_VALUE(j25.avanti_student_id)                                                      AS avanti_studentid
    FROM {_EDS}.jnv_fact_jee_results
    LEFT JOIN jee25_avanti j25 USING (application_no)
    WHERE application_no IS NOT NULL
    GROUP BY 1, 2
),
neet AS (
    SELECT DISTINCT
        test_year,
        application_no,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(student_full_name,''), r'\\s+', ' ')))) AS norm_name,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(student_state,    ''), r'\\s+', ' ')))) AS norm_state,
        ANY_VALUE(COALESCE(
            SAFE.PARSE_DATE('%d-%m-%Y', dob),
            SAFE.PARSE_DATE('%Y-%m-%d', dob),
            SAFE.PARSE_DATE('%d%m%Y',   dob)
        ))                                                                                    AS dob,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))))       AS norm_father,
        ANY_VALUE(UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))))       AS norm_mother,
        ANY_VALUE(student_id)                                                                 AS avanti_student_id
    FROM {_EDS}.jnv_fact_neet_results
    WHERE application_no IS NOT NULL
    GROUP BY 1, 2
),

-- ── board_12th → board_10th linking ───────────────────────────────────────────
-- Priority 1: direct roll_number_10th (2025 cohort only)
b10_link_direct AS (
    SELECT yr12, roll12, CAST(CAST(yr12 AS INT64)-2 AS STRING) AS yr10,
           roll_number_10th AS roll10, 'direct_roll' AS b10_src
    FROM b12
    WHERE yr12 = '2025' AND roll_number_10th IS NOT NULL AND roll_number_10th != ''
),
-- Priority 2: Poojita 2024 (2024 cohort)
b10_link_poojita AS (
    SELECT b12.yr12, b12.roll12, '2022' AS yr10, p.roll_10th AS roll10, 'poojita_2024' AS b10_src
    FROM b12
    JOIN poojita24 p ON p.roll_12th = b12.roll12
    WHERE b12.yr12 = '2024' AND p.roll_10th IS NOT NULL
),
-- Priority 3: name match fallback (all cohorts, unambiguous only)
b10_link_name_raw AS (
    SELECT b12.yr12, b12.roll12,
           CAST(CAST(b12.yr12 AS INT64)-2 AS STRING) AS yr10,
           b10.roll10,
           COUNT(*) OVER (PARTITION BY b12.roll12, b12.yr12) AS match_cnt
    FROM b12
    -- skip cohorts already handled above
    LEFT JOIN b10_link_direct  dir ON dir.roll12 = b12.roll12 AND dir.yr12 = b12.yr12
    LEFT JOIN b10_link_poojita poj ON poj.roll12 = b12.roll12 AND poj.yr12 = b12.yr12
    JOIN b10 ON b10.norm_name = b12.norm_name
             AND b10.yr10 = CAST(CAST(b12.yr12 AS INT64)-2 AS STRING)
    WHERE dir.roll12 IS NULL AND poj.roll12 IS NULL
),
b10_link_name AS (
    SELECT yr12, roll12, yr10, roll10, 'name_match' AS b10_src
    FROM b10_link_name_raw WHERE match_cnt = 1
),
-- Combine all b10 links (no overlap — each priority excludes the previous)
b10_link AS (
    SELECT * FROM b10_link_direct
    UNION ALL SELECT * FROM b10_link_poojita
    UNION ALL SELECT * FROM b10_link_name
),

-- ── board_12th → JEE linking ──────────────────────────────────────────────────
-- Priority 1: Poojita 2024
jee_link_poojita AS (
    SELECT b12.yr12, b12.roll12, '2024' AS jee_yr, p.jee_app_no, 'poojita_2024' AS jee_src
    FROM b12
    JOIN poojita24 p ON p.roll_12th = b12.roll12
    WHERE b12.yr12 = '2024' AND p.jee_app_no IS NOT NULL
),
-- Priority 2: name + father name match (unambiguous only, for all cohorts)
-- board_12th has 0 DOB but 100% father/mother name — use father name to disambiguate
jee_link_name_raw AS (
    SELECT b12.yr12, b12.roll12, jee.test_year AS jee_yr, jee.application_no AS jee_app_no,
           COUNT(*) OVER (PARTITION BY b12.roll12, b12.yr12, jee.test_year) AS match_cnt
    FROM b12
    LEFT JOIN jee_link_poojita poj ON poj.roll12 = b12.roll12 AND poj.yr12 = b12.yr12
    JOIN jee ON jee.norm_name   = b12.norm_name
            AND jee.norm_father = b12.norm_father
            AND CAST(jee.test_year AS INT64) BETWEEN CAST(b12.yr12 AS INT64)
                                                 AND CAST(b12.yr12 AS INT64) + 2
    WHERE poj.roll12 IS NULL AND jee.norm_name != '' AND b12.norm_father != ''
      AND jee.norm_father != ''
),
jee_link_name AS (
    SELECT yr12, roll12, jee_yr, jee_app_no, 'name_father_match' AS jee_src
    FROM jee_link_name_raw WHERE match_cnt = 1
),
jee_link AS (
    SELECT * FROM jee_link_poojita
    UNION ALL SELECT * FROM jee_link_name
),

-- ── board_12th → NEET linking ─────────────────────────────────────────────────
-- Priority 1: Poojita 2024
neet_link_poojita AS (
    SELECT b12.yr12, b12.roll12, '2024' AS neet_yr, p.neet_app_no, 'poojita_2024' AS neet_src
    FROM b12
    JOIN poojita24 p ON p.roll_12th = b12.roll12
    WHERE b12.yr12 = '2024' AND p.neet_app_no IS NOT NULL
),
-- Priority 2: name + father name match (unambiguous only)
neet_link_name_raw AS (
    SELECT b12.yr12, b12.roll12, neet.test_year AS neet_yr, neet.application_no AS neet_app_no,
           COUNT(*) OVER (PARTITION BY b12.roll12, b12.yr12, neet.test_year) AS match_cnt
    FROM b12
    LEFT JOIN neet_link_poojita poj ON poj.roll12 = b12.roll12 AND poj.yr12 = b12.yr12
    JOIN neet ON neet.norm_name   = b12.norm_name
             AND neet.norm_father = b12.norm_father
             AND CAST(neet.test_year AS INT64) BETWEEN CAST(b12.yr12 AS INT64)
                                                   AND CAST(b12.yr12 AS INT64) + 2
    WHERE poj.roll12 IS NULL AND neet.norm_name != '' AND b12.norm_father != ''
      AND neet.norm_father != ''
),
neet_link_name AS (
    SELECT yr12, roll12, neet_yr, neet_app_no, 'name_father_match' AS neet_src
    FROM neet_link_name_raw WHERE match_cnt = 1
),
neet_link AS (
    SELECT * FROM neet_link_poojita
    UNION ALL SELECT * FROM neet_link_name
),

-- ── Assemble one row per (b12_roll, b12_year, jee_year, neet_year) ────────────
-- Start from all JEE + NEET links; students with neither still get a row from b12
all_exam_links AS (
    -- JEE rows
    SELECT yr12, roll12, jee_yr, jee_app_no, jee_src, NULL AS neet_yr, NULL AS neet_app_no, NULL AS neet_src
    FROM jee_link
    UNION ALL
    -- NEET rows
    SELECT yr12, roll12, NULL, NULL, NULL, neet_yr, neet_app_no, neet_src
    FROM neet_link
),
-- Merge JEE and NEET rows for the same (roll12, yr12) into one row where test years match
exam_combined AS (
    SELECT yr12, roll12,
        jee_yr, jee_app_no, jee_src,
        neet_yr, neet_app_no, neet_src,
        -- merge JEE+NEET for same student same year into one row
        ROW_NUMBER() OVER (PARTITION BY yr12, roll12, COALESCE(jee_yr, neet_yr)
                           ORDER BY jee_app_no, neet_app_no) AS _rn
    FROM (
        SELECT yr12, roll12,
            MAX(CASE WHEN jee_app_no IS NOT NULL THEN jee_yr END)   AS jee_yr,
            MAX(jee_app_no)  AS jee_app_no,
            MAX(jee_src)     AS jee_src,
            MAX(CASE WHEN neet_app_no IS NOT NULL THEN neet_yr END) AS neet_yr,
            MAX(neet_app_no) AS neet_app_no,
            MAX(neet_src)    AS neet_src
        FROM all_exam_links
        GROUP BY yr12, roll12, COALESCE(jee_yr, neet_yr)
    )
),
-- b12 students with no JEE and no NEET also get a row
base AS (
    SELECT b12.yr12, b12.roll12,
        ec.jee_yr, ec.jee_app_no, ec.jee_src,
        ec.neet_yr, ec.neet_app_no, ec.neet_src
    FROM b12
    LEFT JOIN exam_combined ec ON ec.roll12 = b12.roll12 AND ec.yr12 = b12.yr12 AND ec._rn = 1
    -- for retakers: there are additional rows in exam_combined beyond _rn=1
    UNION ALL
    SELECT ec.yr12, ec.roll12, ec.jee_yr, ec.jee_app_no, ec.jee_src,
           ec.neet_yr, ec.neet_app_no, ec.neet_src
    FROM exam_combined ec
    WHERE ec._rn > 1
),

-- ── Enrich with identity fields ───────────────────────────────────────────────
enriched AS (
    SELECT
        base.yr12                                         AS board_12th_exam_year,
        base.roll12                                       AS board_12th_roll_number,
        b10_link.yr10                                     AS board_10th_exam_year,
        b10_link.roll10                                   AS board_10th_roll_number,
        b10_link.b10_src,
        base.jee_yr                                       AS jee_test_year,
        base.jee_app_no                                   AS jee_application_no,
        base.jee_src,
        base.neet_yr                                      AS neet_test_year,
        base.neet_app_no                                  AS neet_application_no,
        base.neet_src,
        -- best name: prefer b12 (always present), use JEE/NEET as fallback
        COALESCE(b12.norm_name, jee.norm_name, neet.norm_name)   AS norm_name,
        -- DOB: b10 is the gold standard (12th has no DOB), JEE/NEET as fallback
        COALESCE(b10.dob, jee.dob, neet.dob)                     AS dob,
        -- parent names: pool from b10 and JEE/NEET
        COALESCE(
            NULLIF(b10.norm_father, ''),
            NULLIF(jee.norm_father, ''),
            NULLIF(neet.norm_father, '')
        )                                                           AS norm_father,
        COALESCE(
            NULLIF(b10.norm_mother, ''),
            NULLIF(jee.norm_mother, ''),
            NULLIF(neet.norm_mother, '')
        )                                                           AS norm_mother,
        -- direct Avanti ID: JEE 2025 avanti_studentid, NEET student_id, Poojita 2025
        COALESCE(
            NULLIF(jee.avanti_studentid, ''),
            NULLIF(neet.avanti_student_id, ''),
            p25.avanti_student_id
        )                                                           AS source_avanti_student_id
    FROM base
    LEFT JOIN b12       ON b12.roll12  = base.roll12 AND b12.yr12 = base.yr12
    LEFT JOIN b10_link  ON b10_link.roll12 = base.roll12 AND b10_link.yr12 = base.yr12
    LEFT JOIN b10       ON b10.roll10  = b10_link.roll10 AND b10.yr10 = b10_link.yr10
    LEFT JOIN jee       ON jee.application_no = base.jee_app_no AND jee.test_year = base.jee_yr
    LEFT JOIN neet      ON neet.application_no = base.neet_app_no AND neet.test_year = base.neet_yr
    LEFT JOIN poojita25 p25 ON p25.roll_10th = b10_link.roll10
),

-- ── Avanti FK matching ────────────────────────────────────────────────────────
avanti AS (
    SELECT DISTINCT pk_student_id, date_of_birth,
        UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\\s+', ' ')))       AS norm_name,
        UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))) AS norm_father,
        UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))) AS norm_mother,
        SAFE.DATE(EXTRACT(YEAR FROM date_of_birth), EXTRACT(DAY FROM date_of_birth), EXTRACT(MONTH FROM date_of_birth)) AS dob_swapped
    FROM {_DIM}
    WHERE (LOWER(COALESCE(student_school,'')) LIKE '%jnv%'
        OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')
      AND student_grade = 12
      AND academic_year IN ('2021-2022','2022-2023','2023-2024','2024-2025','2025-2026','2026-2027')
      AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL
    UNION ALL
    SELECT DISTINCT pk_student_id, date_of_birth,
        UPPER(TRIM(REGEXP_REPLACE(student_full_name, r'\\s+', ' ')))       AS norm_name,
        UPPER(TRIM(REGEXP_REPLACE(COALESCE(father_name,''), r'\\s+', ' '))) AS norm_father,
        UPPER(TRIM(REGEXP_REPLACE(COALESCE(mother_name,''), r'\\s+', ' '))) AS norm_mother,
        SAFE.DATE(EXTRACT(YEAR FROM date_of_birth), EXTRACT(DAY FROM date_of_birth), EXTRACT(MONTH FROM date_of_birth)) AS dob_swapped
    FROM {_DIMH}
    WHERE (LOWER(COALESCE(student_school,'')) LIKE '%jnv%'
        OR LOWER(COALESCE(student_school,'')) LIKE '%navodaya%')
      AND student_grade = 12
      AND academic_year IN ('2021-2022','2022-2023','2023-2024','2024-2025','2025-2026','2026-2027')
      AND student_full_name IS NOT NULL AND date_of_birth IS NOT NULL
),
-- Pass 1: direct Avanti ID
fk_direct AS (
    SELECT e.board_12th_roll_number, e.board_12th_exam_year, e.jee_test_year, e.neet_test_year,
        e.source_avanti_student_id AS fk_avanti_student_id, 'direct_student_id' AS match_confidence, 1 AS match_count
    FROM enriched e
    WHERE e.source_avanti_student_id IS NOT NULL
      AND EXISTS (SELECT 1 FROM avanti a WHERE a.pk_student_id = e.source_avanti_student_id)
),
-- Pass 2: name + DOB exact (using b10 DOB)
fk_p2_raw AS (
    SELECT e.board_12th_roll_number, e.board_12th_exam_year, e.jee_test_year, e.neet_test_year,
        COUNT(DISTINCT a.pk_student_id) AS cnt, ANY_VALUE(a.pk_student_id) AS candidate_id
    FROM enriched e
    LEFT JOIN fk_direct fd ON fd.board_12th_roll_number = e.board_12th_roll_number
                           AND fd.board_12th_exam_year  = e.board_12th_exam_year
                           AND IFNULL(fd.jee_test_year, '')  = IFNULL(e.jee_test_year, '')
                           AND IFNULL(fd.neet_test_year, '') = IFNULL(e.neet_test_year, '')
    JOIN avanti a ON a.norm_name = e.norm_name AND a.date_of_birth = e.dob
    WHERE fd.board_12th_roll_number IS NULL AND e.norm_name IS NOT NULL AND e.dob IS NOT NULL
    GROUP BY 1, 2, 3, 4
),
fk_p2 AS (
    SELECT *, CASE WHEN cnt=1 THEN candidate_id ELSE NULL END AS fk_avanti_student_id,
        'name_dob' AS match_confidence, cnt AS match_count
    FROM fk_p2_raw
),
-- Pass 3: name + DOB swapped (DD/MM transposition)
fk_p3_raw AS (
    SELECT e.board_12th_roll_number, e.board_12th_exam_year, e.jee_test_year, e.neet_test_year,
        COUNT(DISTINCT a.pk_student_id) AS cnt, ANY_VALUE(a.pk_student_id) AS candidate_id
    FROM enriched e
    LEFT JOIN fk_direct fd ON fd.board_12th_roll_number = e.board_12th_roll_number
                           AND fd.board_12th_exam_year  = e.board_12th_exam_year
                           AND IFNULL(fd.jee_test_year, '')  = IFNULL(e.jee_test_year, '')
                           AND IFNULL(fd.neet_test_year, '') = IFNULL(e.neet_test_year, '')
    LEFT JOIN fk_p2 p2 ON p2.board_12th_roll_number = e.board_12th_roll_number
                       AND p2.board_12th_exam_year  = e.board_12th_exam_year
                       AND IFNULL(p2.jee_test_year, '')  = IFNULL(e.jee_test_year, '')
                       AND IFNULL(p2.neet_test_year, '') = IFNULL(e.neet_test_year, '')
    JOIN avanti a ON a.norm_name = e.norm_name AND a.dob_swapped = e.dob
    WHERE fd.board_12th_roll_number IS NULL AND p2.board_12th_roll_number IS NULL
      AND e.norm_name IS NOT NULL AND e.dob IS NOT NULL
    GROUP BY 1, 2, 3, 4
),
fk_p3 AS (
    SELECT *, CASE WHEN cnt=1 THEN candidate_id ELSE NULL END AS fk_avanti_student_id,
        'name_dob_swapped' AS match_confidence, cnt AS match_count
    FROM fk_p3_raw
),
-- Combine FK passes
fk_all AS (
    SELECT board_12th_roll_number, board_12th_exam_year, jee_test_year, neet_test_year,
        fk_avanti_student_id, match_confidence, match_count
    FROM fk_direct
    UNION ALL
    SELECT board_12th_roll_number, board_12th_exam_year, jee_test_year, neet_test_year,
        fk_avanti_student_id, match_confidence, match_count
    FROM fk_p2
    UNION ALL
    SELECT board_12th_roll_number, board_12th_exam_year, jee_test_year, neet_test_year,
        fk_avanti_student_id, match_confidence, match_count
    FROM fk_p3
)

-- ── Final output ──────────────────────────────────────────────────────────────
SELECT
    e.board_12th_exam_year,
    e.board_12th_roll_number,
    e.board_10th_exam_year,
    e.board_10th_roll_number,
    e.b10_src                AS board_10th_link_source,
    e.jee_test_year,
    e.jee_application_no,
    e.jee_src                AS jee_link_source,
    e.neet_test_year,
    e.neet_application_no,
    e.neet_src               AS neet_link_source,
    e.norm_name,
    e.dob,
    e.norm_father,
    e.norm_mother,
    e.source_avanti_student_id,
    fk.fk_avanti_student_id,
    fk.match_confidence,
    fk.match_count
FROM enriched e
LEFT JOIN fk_all fk
    ON  fk.board_12th_roll_number = e.board_12th_roll_number
    AND fk.board_12th_exam_year   = e.board_12th_exam_year
    AND IFNULL(fk.jee_test_year,  '') = IFNULL(e.jee_test_year,  '')
    AND IFNULL(fk.neet_test_year, '') = IFNULL(e.neet_test_year, '')
"""


def main() -> None:
    from google.cloud import bigquery
    from google.cloud.bigquery import QueryJobConfig, WriteDisposition

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    if not _POOJITA.exists():
        print(f"ERROR: Poojita file not found: {_POOJITA}")
        sys.exit(1)

    print("Uploading reference sheets ...")
    tmp24, tmp25, tmp_jee25_avanti = _upload_reference_tables(client)

    try:
        sql = _build_sql(tmp24, tmp25, tmp_jee25_avanti)
        print(f"\nBuilding {_OUT} ...")
        job = client.query(
            sql,
            job_config=QueryJobConfig(
                destination=_OUT,
                write_disposition=WriteDisposition.WRITE_TRUNCATE,
                create_disposition="CREATE_IF_NEEDED",
            ),
        )
        job.result()

        tbl = client.get_table(_OUT)
        print(f"  ✓ {tbl.num_rows:,} rows written to {_OUT}")

        # Quick coverage summary
        summary_sql = f"""
        SELECT
            board_12th_exam_year,
            COUNT(*) AS total_rows,
            COUNTIF(board_10th_roll_number IS NOT NULL)  AS has_b10,
            COUNTIF(jee_application_no IS NOT NULL)      AS has_jee,
            COUNTIF(neet_application_no IS NOT NULL)     AS has_neet,
            COUNTIF(fk_avanti_student_id IS NOT NULL)    AS has_fk,
            COUNTIF(source_avanti_student_id IS NOT NULL) AS has_direct_id
        FROM `{_OUT}`
        GROUP BY 1 ORDER BY 1
        """
        print(f"\n{'yr12':<6} {'rows':>7} {'b10':>7} {'jee':>7} {'neet':>7} {'fk':>7} {'direct_id':>10}")
        print("-" * 58)
        for r in client.query(summary_sql).result():
            print(
                f"  {r.board_12th_exam_year:<4}"
                f"  {r.total_rows:>7,}"
                f"  {r.has_b10:>7,}"
                f"  {r.has_jee:>7,}"
                f"  {r.has_neet:>7,}"
                f"  {r.has_fk:>7,}"
                f"  {r.has_direct_id:>10,}"
            )

    finally:
        client.delete_table(tmp24, not_found_ok=True)
        client.delete_table(tmp25, not_found_ok=True)
        client.delete_table(tmp_jee25_avanti, not_found_ok=True)
        print("\nTemp tables cleaned up.")
        print("Done.")


if __name__ == "__main__":
    main()
