#!/usr/bin/env python3
"""
Build the finished UDISE+ DSP tables in BigQuery from the raw staging tables.

    udise_dsp_staging.profile_data_{1,2}_<year>   ─┐
                                                   ├─▶ external_data_sources.udise_dim_school_dsp
    udise_dsp_staging.enrolment_data_{1,2}_<year> ─┴─▶ external_data_sources.udise_fact_enrolment_dsp

Run scripts/dsp_stage.py first. This script is pure SQL generation: nothing is
read onto this machine, because the enrolment melt turns ~12 GB of CSV into
hundreds of millions of rows and BigQuery is where that belongs.

Why SQL and not a clean parquet in GCS, which is the convention for every other
source in this repo: the clean layer here cannot round-trip through a laptop. The
generated SQL is committed and printed, so the tables stay fully regenerable and
auditable — that is the property the parquet convention exists to protect.

Usage:
  python3 scripts/dsp_build_bq.py --print-sql          # generate, print, run nothing
  python3 scripts/dsp_build_bq.py --dim
  python3 scripts/dsp_build_bq.py --fact
  python3 scripts/dsp_build_bq.py                      # both
  python3 scripts/dsp_build_bq.py --validate
  python3 scripts/dsp_build_bq.py --drop-staging       # after the tables check out
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (
    BQ_DATASET,
    BQ_LOCATION,
    BQ_PROJECT,
    DSP_STAGING_DATASET,
    DSP_YEARS,
    ROOT,
    dsp_staging_table,
)

LAYOUTS_JSON = ROOT / "schemas" / "dsp_layouts.json"
CODEMAPS = ROOT / "codemaps"

DIM_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.udise_dim_school_dsp"
FACT_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.udise_fact_enrolment_dsp"

CLASS_KEYS = ["cpp"] + [f"c{n}" for n in range(1, 13)]
CLASS_LEVEL = {"cpp": "PP", **{f"c{n}": str(n) for n in range(1, 13)}}
CLASS_ORDER = {"cpp": 0, **{f"c{n}": n for n in range(1, 13)}}

# `_b` folds transgender students into boys in every edition that has no separate
# `_t` column — the 2024-25 codebook says so outright ("Boys +Transgenders"). The
# 2025-26 edition adds `c1_t`…`c12_t` and drops that remark, so there `_b` is boys
# alone. The gender VALUE carries that distinction rather than a footnote, because
# a footnote is not present in the query that gets the ratio wrong.
GENDER_WITH_T = {"b": "boys", "g": "girls", "t": "transgender"}
GENDER_WITHOUT_T = {"b": "boys_incl_transgender", "g": "girls"}


def sql_str(value) -> str:
    if value is None or value == "":
        return "NULL"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def read_codemap(name: str) -> list[dict]:
    with (CODEMAPS / name).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def layouts() -> dict[str, list[str]]:
    if not LAYOUTS_JSON.exists():
        raise SystemExit(f"missing {LAYOUTS_JSON}; run scripts/dsp_stage.py first")
    return json.loads(LAYOUTS_JSON.read_text())


def cols(lay: dict[str, list[str]], year: str, group: str) -> list[str]:
    key = f"{year}/{group}"
    if key not in lay:
        raise SystemExit(f"{key} is not staged; run scripts/dsp_stage.py --years {year} --groups {group}")
    return lay[key]


def values_cte(name: str, columns: list[str], rows: list[list]) -> str:
    """An inline VALUES table — keeps the small codemaps in the committed SQL
    rather than in yet another BigQuery table nobody remembers to refresh."""
    body = ",\n    ".join("(" + ", ".join(sql_str(v) for v in r) + ")" for r in rows)
    return f"{name} AS (\n  SELECT * FROM UNNEST([\n    STRUCT<{', '.join(f'{c} STRING' for c in columns)}>\n    {body}\n  ])\n)"


# ─── dim: one row per school per year ────────────────────────────────────────

def _pick(available: list[str], source: str, cast: str | None, alias: str, prefix: str = "") -> str:
    """Emit `<prefix><source> AS alias` if that column exists this year, else a
    typed NULL. This is what lets five editions with different column sets UNION."""
    if source in available:
        ref = f"{prefix}{source}"
        expr = f"SAFE_CAST({ref} AS {cast})" if cast else ref
    else:
        expr = f"CAST(NULL AS {cast or 'STRING'})"
    return f"{expr} AS {alias}"


# (source column, cast, output alias). A source column absent from a given year's
# layout becomes a typed NULL, which is what lets five editions UNION cleanly.
DIM_FIELDS: list[tuple[str, str | None, str]] = [
    # geography
    ("block", None, "block"),
    ("lgd_urban_local_body_name", None, "lgd_urban_local_body_name"),
    ("lgd_ward_name", None, "lgd_ward_name"),
    ("lgd_vill_name", None, "lgd_vill_name"),
    ("lgd_vill_panchayat_name", None, "lgd_vill_panchayat_name"),
    ("lgd_block_name", None, "lgd_block_name"),
    ("assembly", None, "assembly_constituency"),          # 2020-21 only
    ("parliamentary", None, "parliamentary_constituency"),  # 2020-21 only
    ("city", None, "city"),                                # 2020-21 only
    ("municipality", None, "municipality"),                # 2020-21 only
    ("panchyat", None, "gram_panchayat"),                  # sic, 2020-21 only
    ("pincode", None, "pincode"),
    # school characteristics
    ("lowclass", "INT64", "lowest_class"),
    ("highclass", "INT64", "highest_class"),
    ("special_school_for_cwsn", None, "special_school_for_cwsn"),
    ("shift_school", None, "shift_school"),
    ("resi_type", None, "resi_type_code"),
    ("minority_school", None, "minority_school"),
    ("medium_instr1", None, "medium_instr1_code"),
    ("medium_of_instr2", None, "medium_instr2_code"),
    ("medium_of_instr3", None, "medium_instr3_code"),
    ("medium_of_instr4", None, "medium_instr4_code"),
    ("aff_board_sec", None, "aff_board_sec_code"),
    ("aff_board_hsec", None, "aff_board_hsec_code"),
    ("approachable_road", None, "approachable_road"),
    ("pre_primary", None, "pre_primary"),
    ("cwsn_sch_type", None, "cwsn_school_type_code"),       # 2025-26 only
    # anganwadi / pre-school
    ("anganwadi_yn", None, "anganwadi_yn"),                 # 2022-23 on
    ("anganwadi_premises", None, "anganwadi_premises"),     # 2020-21 only
    ("anganwadi_boys", "INT64", "anganwadi_boys"),          # 2020-21 only
    ("anganwadi_girls", "INT64", "anganwadi_girls"),        # 2020-21 only
    ("anganwadi_worker", "INT64", "anganwadi_workers"),     # 2020-21 only
    ("same_sch_b", "INT64", "class1_preschool_same_school_b"),
    ("same_sch_g", "INT64", "class1_preschool_same_school_g"),
    ("other_sch_b", "INT64", "class1_preschool_other_school_b"),
    ("other_sch_g", "INT64", "class1_preschool_other_school_g"),
    ("anganwadi_ecce_b", "INT64", "class1_preschool_anganwadi_b"),
    ("anganwadi_ecce_g", "INT64", "class1_preschool_anganwadi_g"),
    # instruction time
    ("avg_instr_days", "INT64", "avg_instr_days"),          # 2022-23 on
    ("instr_days_pr", "INT64", "instr_days_primary"),       # 2020-21 only
    ("instr_days_up", "INT64", "instr_days_upper_primary"),
    ("instr_days_sec", "INT64", "instr_days_secondary"),
    ("instr_days_hsec", "INT64", "instr_days_higher_secondary"),
    ("avg_school_hrs_student_pr", "NUMERIC", "avg_school_hrs_student_primary"),
    ("avg_school_hrs_student_up", "NUMERIC", "avg_school_hrs_student_upper_primary"),
    ("avg_school_hrs_student_sec", "NUMERIC", "avg_school_hrs_student_secondary"),
    ("avg_school_hrs_student_hsec", "NUMERIC", "avg_school_hrs_student_higher_secondary"),
    ("avg_school_hrs_teacher_pr", "NUMERIC", "avg_school_hrs_teacher_primary"),
    ("avg_school_hrs_teacher_up", "NUMERIC", "avg_school_hrs_teacher_upper_primary"),
    ("avg_school_hrs_teacher_sec", "NUMERIC", "avg_school_hrs_teacher_secondary"),
    ("avg_school_hrs_teacher_hsec", "NUMERIC", "avg_school_hrs_teacher_higher_secondary"),
    ("cce_yn", None, "cce_yn"),                             # 2022-23 on
    ("cce_pr", None, "cce_primary"),                        # 2020-21 only
    ("cce_up", None, "cce_upper_primary"),
    ("cce_sec", None, "cce_secondary"),
    ("cce_hsec", None, "cce_higher_secondary"),
    # recognition history (2020-21 only, except estd_year which 2025-26 revives)
    ("year_of_recognition_pr", None, "year_of_recognition_primary"),
    ("year_of_recognition_up", None, "year_of_recognition_upper_primary"),
    ("year_of_recognition_sec", None, "year_of_recognition_secondary"),
    ("year_of_recognition_hsec", None, "year_of_recognition_higher_secondary"),
    # 2025-26 additions
    ("rte_25p_admission_yn", None, "rte_25pc_admission_yn"),
    ("certified_fit_india_yn", None, "certified_fit_india_yn"),
    ("is_nsqf", None, "is_nsqf"),
    ("prevoc_yn", None, "prevocational_yn"),
    ("stc_yn", None, "special_training_centre_yn"),
    ("smdc_pta_yn", None, "smdc_pta_yn"),
    ("smdc_pta_meeting", "INT64", "smdc_pta_meetings"),
    ("remedial_tch_enrol", "INT64", "remedial_teaching_enrolment"),
    ("learner_holistic_rptcard_yn", None, "holistic_report_card_yn"),
    # profile_2: entitlements, oversight, grants
    ("balavatika_located_yn", None, "balavatika_located_yn"),   # 2022-23 on
    ("special_training", None, "special_training"),
    ("material_training", None, "supplementary_material"),
    ("text_books_received", None, "textbooks_received"),        # 2020-21 only
    ("free_text_books_pr", None, "free_textbooks_primary"),
    ("free_uniform_pr", None, "free_uniform_primary"),
    ("free_text_books_up", None, "free_textbooks_upper_primary"),
    ("free_uniform_up", None, "free_uniform_upper_primary"),
    ("transport_pr", None, "free_transport_primary"),           # 2020-21 only
    ("transport_up", None, "free_transport_upper_primary"),     # 2020-21 only
    ("acad_inspections", "INT64", "academic_inspections"),
    ("crc_coordinator", "INT64", "crc_coordinator_visits"),
    ("block_level_officers", "INT64", "block_officer_visits"),
    ("district_officers", "INT64", "district_officer_visits"),
    ("smc_exists", None, "smc_exists"),
    ("smc_smdc_same", None, "smc_smdc_same"),
    ("smc_smdc_meetings", "INT64", "smc_smdc_meetings"),        # 2022-23 on
    ("smdc_constituted", None, "smdc_constituted"),             # 2020-21 only
    ("grants_receipt", "NUMERIC", "grants_receipt"),
    ("grants_expenditure", "NUMERIC", "grants_expenditure"),
]

# 2020-21 profile_2 columns 20-45 are deliberately NOT published. The CSV header
# names them rte_ews_c0_b … rte_ews_c12_g, but the 2020-21 codebook says positions
# 20-37 are rte_bld_* ("RTE students who have received building, equipment") and
# only 38-45 are rte_ews_c9…c12. Header and codebook disagree about what 26 columns
# of numbers mean, so neither reading is publishable. rte_pvt_c0…c8 (positions 2-19)
# are unambiguous — both agree — and are summed into rte_private_unaided_students.
RTE_PVT_SUM_2020_21 = (
    "("
    + " + ".join(
        f"IFNULL(SAFE_CAST(rte_pvt_c{n}_{g} AS INT64), 0)"
        for n in range(0, 9)
        for g in ("b", "g")
    )
    + ")"
)


def dim_year_sql(lay: dict[str, list[str]], year: str) -> str:
    p1 = cols(lay, year, "profile_data_1")
    p2 = cols(lay, year, "profile_data_2")
    available = p1 + p2

    parts = [
        f"    {sql_str(year)} AS academic_year",
        f"    {int(year[:4])} AS academic_year_start",
        "    p1.pseudocode",
        # 2020-21 publishes state and district in Title Case, every later edition in
        # UPPER. Normalising here is what makes a five-year panel joinable at all.
        "    UPPER(TRIM(p1.state)) AS state",
        "    UPPER(TRIM(p1.district)) AS district",
        "    p1.rural_urban AS rural_urban_code",
        "    ru.label AS rural_urban",
        "    p1.school_category AS school_category_code",
        "    sc.label AS school_category",
        "    p1.school_type AS school_type_code",
        "    st.label AS school_type",
        # `managment` is misspelt at source in every edition. Renamed here, once.
        "    p1.managment AS management_code",
        "    mg.label AS management",
        "    mg.broad_group AS management_group",
        "    p1.resi_school AS resi_school_code",
        "    rs.label AS resi_school",
        # 2020-21 calls it year_of_establishment, 2025-26 revives it as estd_year,
        # and 2022-23..2024-25 drop it entirely. One output column either way.
        "    " + _pick(p1, "year_of_establishment", None, "year_of_establishment", "p1.")
        if "year_of_establishment" in p1
        else "    " + _pick(p1, "estd_year", None, "year_of_establishment", "p1."),
    ]
    for source, cast, alias in DIM_FIELDS:
        prefix = "p2." if source in p2 else "p1."
        parts.append("    " + _pick(available, source, cast, alias, prefix))
    parts.append(
        f"    {RTE_PVT_SUM_2020_21 if 'rte_pvt_c0_b' in p2 else 'CAST(NULL AS INT64)'}"
        " AS rte_private_unaided_students"
    )

    return (
        "  SELECT\n"
        + ",\n".join(parts)
        + f"\n  FROM `{dsp_staging_table(year, 'profile_data_1')}` p1"
        + f"\n  LEFT JOIN `{dsp_staging_table(year, 'profile_data_2')}` p2"
        + "\n    ON p2.pseudocode = p1.pseudocode"
        + "\n  LEFT JOIN rural_urban_map ru ON ru.code = p1.rural_urban"
        + "\n  LEFT JOIN school_category_map sc ON sc.code = p1.school_category"
        + "\n  LEFT JOIN school_type_map st ON st.code = p1.school_type"
        + "\n  LEFT JOIN management_map mg ON mg.code = p1.managment"
        + "\n  LEFT JOIN resi_school_map rs ON rs.code = p1.resi_school"
    )


def dim_sql(lay: dict[str, list[str]], years: list[str]) -> str:
    maps = [
        values_cte("rural_urban_map", ["code", "label"],
                   [[r["code"], r["label"]] for r in read_codemap("dsp_rural_urban.csv")]),
        values_cte("school_category_map", ["code", "label"],
                   [[r["code"], r["label"]] for r in read_codemap("dsp_school_category.csv")]),
        values_cte("school_type_map", ["code", "label"],
                   [[r["code"], r["label"]] for r in read_codemap("dsp_school_type.csv")]),
        values_cte("management_map", ["code", "label", "broad_group"],
                   [[r["code"], r["label"], r["broad_group"]] for r in read_codemap("dsp_management.csv")]),
        values_cte("resi_school_map", ["code", "label"],
                   [[r["code"], r["label"]] for r in read_codemap("dsp_resi_school.csv")]),
    ]
    body = "\n  UNION ALL\n".join(dim_year_sql(lay, y) for y in years)
    return (
        f"CREATE OR REPLACE TABLE `{DIM_TABLE}`\n"
        "PARTITION BY RANGE_BUCKET(academic_year_start, GENERATE_ARRAY(2015, 2050, 1))\n"
        "CLUSTER BY state, management_code, school_category_code, rural_urban_code\n"
        "OPTIONS (description = 'UDISE+ DSP school directory, one row per school per academic year. "
        "Keyed on the pseudonymised `pseudocode`, which joins to udise_fact_enrolment_dsp within a year "
        "but CANNOT be linked to any real school. Built by udise/scripts/dsp_build_bq.py.')\n"
        f"AS\nWITH\n" + ",\n".join(maps) + "\n" + body + "\n"
    )


# ─── fact: enrolment, melted long ────────────────────────────────────────────

def item_map_rows() -> list[list]:
    rows = [[r["item_group"], r["item_id"], r["dimension"], r["label"]]
            for r in read_codemap("dsp_item_group.csv")]
    # item_group=8 is the age cut, documented in the codebook only as
    # "Age id (2 to 22)" with no id-to-age table. We do NOT invent one: the id is
    # carried through verbatim and labelled as an id, not as an age in years.
    rows.append(["8", None, "age", None])
    return rows


def age_map_rows() -> list[list]:
    return [[r["item_id"], r["age_years"]] for r in read_codemap("dsp_age_item_id.csv")]


def desc_map_rows() -> list[list]:
    # Rows whose item_desc is bracketed (currently only "<blank>") are documentation,
    # not mappings — they record what an unmapped source value means and why it stays
    # unmapped. They must not reach the SQL, or they would map something.
    return [[r["item_desc"], r["item_group"], r["item_id"], r["dimension"], r["label"]]
            for r in read_codemap("dsp_item_desc_2020_21.csv")
            if not r["item_desc"].startswith("<")]


def melt_sql(lay: dict[str, list[str]], year: str, group: str) -> str:
    columns = cols(lay, year, group)
    count_cols = [c for c in columns if c.split("_")[0] in CLASS_KEYS and c.split("_")[-1] in ("b", "g", "t")]
    if not count_cols:
        raise SystemExit(f"{year}/{group}: no class x gender columns found in {columns}")
    coded = "item_group" in columns
    cut = "age" if group == "enrolment_data_2" else "item_breakdown"

    select = [
        f"      {sql_str(year)} AS academic_year",
        f"      {int(year[:4])} AS academic_year_start",
        "      pseudocode",
        f"      {sql_str(cut)} AS cut",
        "      item_group" if coded else "      CAST(NULL AS STRING) AS item_group",
        "      item_id" if coded else "      CAST(NULL AS STRING) AS item_id",
        "      CAST(NULL AS STRING) AS item_source_label" if coded else "      item_desc AS item_source_label",
        "      SPLIT(col, '_')[OFFSET(0)] AS class_key",
        "      SPLIT(col, '_')[OFFSET(1)] AS gender_key",
        "      students",
    ]
    return (
        "    SELECT\n" + ",\n".join(select)
        + f"\n    FROM `{dsp_staging_table(year, group)}`"
        + f"\n    UNPIVOT (students FOR col IN ({', '.join(count_cols)}))"
        # Absence means zero. Dropping the zero cells is what keeps this table a
        # few hundred million rows instead of a few billion: most schools do not
        # teach most classes, and most items are zero in the classes they do teach.
        + "\n    WHERE students > 0"
    )


def fact_sql(lay: dict[str, list[str]], years: list[str]) -> str:
    melts = "\n    UNION ALL\n".join(
        melt_sql(lay, y, g) for y in years for g in ("enrolment_data_1", "enrolment_data_2")
    )
    class_rows = [[k, CLASS_LEVEL[k], str(CLASS_ORDER[k])] for k in CLASS_KEYS]
    gender_rows = (
        [[y, k, v] for y in years if f"{y}/enrolment_data_1" in lay
         for k, v in (GENDER_WITH_T if "cpp_t" in lay[f"{y}/enrolment_data_1"] else GENDER_WITHOUT_T).items()]
    )

    ctes = [
        values_cte("item_map", ["item_group", "item_id", "dimension", "label"], item_map_rows()),
        values_cte("desc_map", ["item_desc", "item_group", "item_id", "dimension", "label"], desc_map_rows()),
        values_cte("class_map", ["class_key", "class_level", "class_order"], class_rows),
        values_cte("age_map", ["item_id", "age_years"], age_map_rows()),
        values_cte("gender_map", ["academic_year", "gender_key", "gender"], gender_rows),
        "melted AS (\n" + melts + "\n  )",
    ]

    return (
        f"CREATE OR REPLACE TABLE `{FACT_TABLE}`\n"
        "PARTITION BY RANGE_BUCKET(academic_year_start, GENERATE_ARRAY(2015, 2050, 1))\n"
        "CLUSTER BY item_dimension, item_group, class_level, gender\n"
        "OPTIONS (description = 'UDISE+ DSP enrolment, one row per school x academic year x item x class x gender. "
        "Zero cells are NOT stored — absence means zero. `cut` separates the item breakdown (social category, "
        "religion, BPL, EWS, disability, repeaters) from the age distribution; never sum across cuts. "
        "Built by udise/scripts/dsp_build_bq.py.')\n"
        "AS\nWITH\n" + ",\n".join(ctes) + "\n"
        "SELECT\n"
        "  m.academic_year,\n"
        "  m.academic_year_start,\n"
        "  m.pseudocode,\n"
        "  m.cut,\n"
        "  COALESCE(m.item_group, d.item_group) AS item_group,\n"
        "  COALESCE(m.item_id, d.item_id) AS item_id,\n"
        "  COALESCE(d.dimension, i.dimension) AS item_dimension,\n"
        "  COALESCE(d.label, i.label) AS item_label,\n"
        "  m.item_source_label,\n"
        # age_years is DERIVED, not published: the source gives an opaque "Age id"
        # from 2022-23 on and words in 2020-21. codemaps/dsp_age_item_id.csv carries
        # the derivation and its evidence; raw item_id stays alongside so anyone can
        # re-derive it or disagree.
        "  CASE\n"
        "    WHEN m.cut != 'age' THEN NULL\n"
        "    WHEN m.item_id IS NOT NULL THEN SAFE_CAST(a.age_years AS INT64)\n"
        "    WHEN m.item_source_label = 'Age<5' THEN NULL\n"
        "    ELSE SAFE_CAST(REGEXP_EXTRACT(m.item_source_label, r'^Age([0-9]+)$') AS INT64)\n"
        "  END AS age_years,\n"
        "  c.class_level,\n"
        "  c.class_order,\n"
        "  g.gender,\n"
        "  m.students\n"
        "FROM melted m\n"
        "LEFT JOIN desc_map d ON d.item_desc = m.item_source_label\n"
        "LEFT JOIN age_map a ON m.cut = 'age' AND a.item_id = m.item_id\n"
        "LEFT JOIN item_map i ON i.item_group = m.item_group\n"
        "  AND (i.item_id = m.item_id OR (i.item_id IS NULL AND i.dimension = 'age'))\n"
        "JOIN class_map c ON c.class_key = m.class_key\n"
        "JOIN gender_map g ON g.academic_year = m.academic_year AND g.gender_key = m.gender_key\n"
    )


# ─── validation ──────────────────────────────────────────────────────────────

VALIDATE_SQL = f"""
-- One row per school per year in the dim, and no orphan schools in the fact.
SELECT 'dim rows per year' AS check_name, academic_year AS k,
       CAST(COUNT(*) AS STRING) AS v,
       CAST(COUNT(DISTINCT pseudocode) AS STRING) AS v2
FROM `{DIM_TABLE}` GROUP BY 1, 2
UNION ALL
SELECT 'fact rows per year', academic_year, CAST(COUNT(*) AS STRING),
       CAST(COUNT(DISTINCT pseudocode) AS STRING)
FROM `{FACT_TABLE}` GROUP BY 1, 2
UNION ALL
-- The social-category items (item_group=1) partition total enrolment, so their sum
-- is the closest DSP analogue to the Report 4000 all-India total.
SELECT 'social category total', academic_year, CAST(SUM(students) AS STRING), NULL
FROM `{FACT_TABLE}` WHERE item_group = '1' GROUP BY 1, 2
UNION ALL
SELECT 'unmapped item rows', academic_year, CAST(COUNT(*) AS STRING), NULL
FROM `{FACT_TABLE}` WHERE item_dimension IS NULL GROUP BY 1, 2
UNION ALL
-- class_map and gender_map are inner joins in the build, so anything they failed to
-- match would vanish silently. These two rows make the surviving key sets visible:
-- 13 class levels every year, and the gender values the edition is supposed to have.
SELECT 'class levels present', academic_year, CAST(COUNT(DISTINCT class_level) AS STRING), NULL
FROM `{FACT_TABLE}` GROUP BY 1, 2
UNION ALL
SELECT 'gender values present', academic_year, STRING_AGG(DISTINCT gender ORDER BY gender), NULL
FROM `{FACT_TABLE}` GROUP BY 1, 2
UNION ALL
SELECT 'fact schools missing from dim', academic_year, CAST(COUNT(*) AS STRING), NULL
FROM (
  SELECT DISTINCT f.academic_year, f.pseudocode
  FROM `{FACT_TABLE}` f
  LEFT JOIN `{DIM_TABLE}` d
    ON d.academic_year = f.academic_year AND d.pseudocode = f.pseudocode
  WHERE d.pseudocode IS NULL
) GROUP BY 1, 2
ORDER BY check_name, k
"""


def bq_query(sql: str, dry_run: bool, label: str) -> None:
    out = Path(tempfile.gettempdir()) / f"udise_dsp_{label}.sql"
    out.write_text(sql)
    print(f"  SQL → {out}")
    if dry_run:
        return
    subprocess.run(
        ["bq", f"--project_id={BQ_PROJECT}", f"--location={BQ_LOCATION}", "query",
         "--use_legacy_sql=false", "--format=prettyjson", "--max_rows=200"],
        input=sql, text=True, check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default=",".join(DSP_YEARS))
    ap.add_argument("--dim", action="store_true")
    ap.add_argument("--fact", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--print-sql", action="store_true", help="write the SQL out and run nothing")
    ap.add_argument("--drop-staging", action="store_true")
    args = ap.parse_args()

    if args.drop_staging:
        print(f"dropping {BQ_PROJECT}:{DSP_STAGING_DATASET} and every table in it")
        subprocess.run(["bq", f"--project_id={BQ_PROJECT}", "rm", "-r", "-f", "-d",
                        f"{BQ_PROJECT}:{DSP_STAGING_DATASET}"], check=True)
        return

    years = [y.strip() for y in args.years.split(",") if y.strip()]
    lay = layouts()
    do_dim = args.dim or not (args.fact or args.validate)
    do_fact = args.fact or not (args.dim or args.validate)

    if do_dim:
        print(f"→ {DIM_TABLE}")
        bq_query(dim_sql(lay, years), args.print_sql, "dim_school")
    if do_fact:
        print(f"→ {FACT_TABLE}")
        bq_query(fact_sql(lay, years), args.print_sql, "fact_enrolment")
    # Validation reads BOTH finished tables, so it only makes sense after a full
    # build or when asked for explicitly — running it after `--dim` alone just fails
    # on a fact table that does not exist yet.
    if args.validate or (do_dim and do_fact):
        print("→ validation")
        bq_query(VALIDATE_SQL, args.print_sql, "validate")
    print("✓ done.")


if __name__ == "__main__":
    main()
