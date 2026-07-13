#!/usr/bin/env python3
"""
Enrich the four JNV source tables with the resolved Avanti foreign key from
`jnv_student_outcome_mapping`. Adds three columns to each table:
    fk_avanti_student_id, match_confidence, match_count

⚠️ fk_avanti_student_id semantics: it is `pk_student_id` for MOST students, but for
   students who have NO pk_student_id in dim_student (only an apaar_id — mostly JNV
   NVS), it holds their `apaar_id` instead. To join back to dim_student, match on
   `COALESCE(pk_student_id, apaar_id) = fk_avanti_student_id`, NOT pk_student_id alone.

Keyed back on each table's own grain:
    jnv_fact_jee_results        (test_year, application_no) → (jee_test_year,  jee_application_no)
    jnv_fact_neet_results       (test_year, application_no) → (neet_test_year, neet_application_no)
    jnv_fact_board_results_10th (exam_year, roll_number)    → (board_10th_exam_year, board_10th_roll_number)
    jnv_fact_board_results_12th (exam_year, roll_number)    → (board_12th_exam_year, board_12th_roll_number)

Safety: the lookup deduplicates on `student_key` and only assigns when a source
key maps to EXACTLY ONE student (HAVING COUNT(DISTINCT student_key)=1) — so a
roll/app contested across two resolved students gets NULL rather than a guess.
The fk/confidence/count are carried as-is (fk may be NULL with
match_confidence='ambiguous' when the student matched >1 Avanti record).

Idempotent: CREATE OR REPLACE re-derives the columns each run (drops prior copies
via SELECT * EXCEPT).

⚠️ RUN ORDER: load_bq.py → build_student_journey_mapping.py → add_avanti_fk.py
   `load_bq.py` WRITE_TRUNCATEs these tables, so re-run this AFTER any reload or
   the fk columns disappear. No circularity: the mapping reads names/rolls/apps,
   never the fk written here.

Usage:
    python3 scripts/add_avanti_fk.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import BQ_PROJECT, BQ_DATASET, BQ_LOCATION

_MAP   = f"{BQ_PROJECT}.{BQ_DATASET}.jnv_student_outcome_mapping"
_ADDED = ["fk_avanti_student_id", "match_confidence", "match_count"]
# Legacy/aliased columns from earlier runs — always stripped, never re-added.
_LEGACY = ["fk_match_confidence", "fk_match_count"]

# table -> (src_year_col, src_key_col, map_year_col, map_key_col)
TABLES = {
    "jnv_fact_jee_results":        ("test_year", "application_no", "jee_test_year",        "jee_application_no"),
    "jnv_fact_neet_results":       ("test_year", "application_no", "neet_test_year",       "neet_application_no"),
    "jnv_fact_board_results_10th": ("exam_year", "roll_number",    "board_10th_exam_year", "board_10th_roll_number"),
    "jnv_fact_board_results_12th": ("exam_year", "roll_number",    "board_12th_exam_year", "board_12th_roll_number"),
}


def main() -> None:
    from google.cloud import bigquery

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print(f"Enriching JNV source tables with Avanti FK from {_MAP}\n")
    for tbl, (syr, skey, myr, mkey) in TABLES.items():
        tid = f"{BQ_PROJECT}.{BQ_DATASET}.{tbl}"

        # Drop any prior copies of the added columns (and legacy fk_match_* from
        # earlier runs) so the rebuild is idempotent and leaves no stale columns.
        existing = {f.name for f in client.get_table(tid).schema}
        drop = [c for c in _ADDED + _LEGACY if c in existing]
        except_clause = f" EXCEPT({', '.join(drop)})" if drop else ""

        sql = f"""
        CREATE OR REPLACE TABLE `{tid}` AS
        SELECT t.*{except_clause},
               m.fk_avanti_student_id, m.match_confidence, m.match_count
        FROM `{tid}` t
        LEFT JOIN (
            SELECT {myr} AS k1, {mkey} AS k2,
                   ANY_VALUE(fk_avanti_student_id) AS fk_avanti_student_id,
                   ANY_VALUE(match_confidence)     AS match_confidence,
                   ANY_VALUE(match_count)          AS match_count
            FROM `{_MAP}`
            WHERE {mkey} IS NOT NULL
            GROUP BY 1, 2
            HAVING COUNT(DISTINCT student_key) = 1
        ) m
          ON CAST(t.{syr} AS STRING) = m.k1
         AND CAST(t.{skey} AS STRING) = m.k2
        """
        client.query(sql).result()

        # Coverage report
        row = list(client.query(f"""
            SELECT COUNT(*) n,
                   COUNTIF(fk_avanti_student_id IS NOT NULL) fk,
                   COUNT(DISTINCT IF(fk_avanti_student_id IS NOT NULL, fk_avanti_student_id, NULL)) distinct_fk
            FROM `{tid}`""").result())[0]
        verb = "added" if not drop else "refreshed"
        print(f"  ✓ {tbl:<30} {verb}: {row.n:,} rows, "
              f"{row.fk:,} with fk ({row.distinct_fk:,} distinct students)")

    print("\nDone. Columns added: " + ", ".join(_ADDED))


if __name__ == "__main__":
    main()
