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
TEACHER_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.udise_fact_teacher_dsp"
FACILITY_TABLE = f"{BQ_PROJECT}.{BQ_DATASET}.udise_fact_facility_dsp"

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


def assert_layouts_match_staging(lay: dict[str, list[str]]) -> None:
    """Fail if BigQuery holds a staging table this layouts file does not know about.

    dsp_stage.py writes dsp_layouts.json as it goes, so a build kicked off while
    staging is still running reads a stale file — and the year-selection below then
    drops that edition WITHOUT SAYING ANYTHING. That is exactly how a facility build
    silently shipped four editions instead of five. Waiting on the BigQuery table
    count is not enough; the two have to agree.
    """
    listing = subprocess.run(
        ["bq", f"--project_id={BQ_PROJECT}", "ls", "--max_results=200",
         f"{BQ_PROJECT}:{DSP_STAGING_DATASET}"],
        capture_output=True, text=True,
    )
    if listing.returncode != 0:
        return  # staging already dropped; nothing to cross-check
    staged = set()
    for line in listing.stdout.splitlines()[2:]:
        name = line.split()[0] if line.split() else ""
        if "_20" not in name:
            continue
        group, _, year = name.rpartition("_20")
        staged.add(f"20{year.replace('_', '-')}/{group}")
    unknown = sorted(staged - set(lay))
    if unknown:
        raise SystemExit(
            "dsp_layouts.json is stale — these are staged in BigQuery but absent from it:\n  "
            + "\n  ".join(unknown)
            + "\nIs dsp_stage.py still running? Let it finish, then re-run this build."
        )


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


# ─── teacher and facility: one wide row per school per year ──────────────────
#
# Both are the same shape as the dim — one row per (academic_year, pseudocode) —
# and are built by the same generic path: pick each field if the edition publishes
# it, emit a typed NULL if it does not, UNION the editions. They are separate
# tables from the dim because they answer separate questions (staffing; physical
# plant), and each is wide enough that folding them in would make the school
# directory unreadable.

# (source column, cast, output alias). Same convention as DIM_FIELDS.
TEACHER_FIELDS: list[tuple[str, str | None, str]] = [
    # headcount and sex. `transgender` is a real third count here, unlike the
    # enrolment file where it is folded into the boys column before 2025-26.
    ("total_tch", "INT64", "teachers_total"),
    ("male", "INT64", "teachers_male"),
    ("female", "INT64", "teachers_female"),
    ("transgender", "INT64", "teachers_transgender"),
    # social category of the teaching staff — 2022-23 onward only
    ("gen_tch", "INT64", "teachers_general"),
    ("sc_tch", "INT64", "teachers_sc"),
    ("st_tch", "INT64", "teachers_st"),
    ("obc_tch", "INT64", "teachers_obc"),
    # terms of employment
    ("regular", "INT64", "teachers_regular"),
    ("contract", "INT64", "teachers_contract"),
    ("part_time", "INT64", "teachers_part_time"),
    # highest academic qualification
    ("below_graduate", "INT64", "teachers_below_graduate"),
    ("graduate", "INT64", "teachers_graduate"),
    ("post_graduate_and_above", "INT64", "teachers_post_graduate_plus"),
    # highest PROFESSIONAL (teaching) qualification — a different axis from the
    # academic one above; the two sets each sum to roughly total_teachers.
    ("diploma_certificate", "INT64", "qual_diploma_certificate"),
    ("bachelor_of_ee", "INT64", "qual_bachelor_elementary_ed"),
    ("bed_equivalent", "INT64", "qual_bed_equivalent"),
    ("med_equivalent", "INT64", "qual_med_equivalent"),
    ("diploma_special_edu", "INT64", "qual_diploma_special_ed"),
    ("pursuing_rpc", "INT64", "qual_pursuing_course"),
    ("diploma_ele_edu", "INT64", "qual_diploma_elementary_ed"),
    ("early_childhood_tch", "INT64", "qual_early_childhood"),
    ("bed_nursery", "INT64", "qual_bed_nursery"),
    ("other", "INT64", "qual_other"),
    ("none", "INT64", "qual_none"),
    # training
    ("trained_comp", "INT64", "teachers_trained_computer"),
    ("trained_cwsn", "INT64", "teachers_trained_cwsn"),
    ("teacher_received_service_training", "INT64", "teachers_received_service_training"),
    ("teacher_involve_non_training_assignment", "INT64", "teachers_non_training_assignment"),
    ("teachers_aged_above_55", "INT64", "teachers_aged_above_55"),
    # which stage each teacher is assigned to teach
    ("class_taught_pr", "INT64", "class_taught_primary"),
    ("class_taught_upr", "INT64", "class_taught_upper_primary"),
    ("class_taught_pr_upr", "INT64", "class_taught_primary_and_upper_primary"),
    ("class_taught_sec_only", "INT64", "class_taught_secondary_only"),
    ("class_taught_hsec_only", "INT64", "class_taught_higher_secondary_only"),
    ("class_taught_upr_sec", "INT64", "class_taught_upper_primary_and_secondary"),
    ("class_taught_sec_hsec", "INT64", "class_taught_secondary_and_higher_secondary"),
    ("class_taugt_pre_primary_only", "INT64", "class_taught_pre_primary_only"),
    ("class_taught_pr_and_pre_pri", "INT64", "class_taught_pre_primary_and_primary"),
]

# 2020-21 spells the headcount `total_teacher` and the computer-training count
# `total_teacher_trained_computer`; every later edition uses `total_tch` and
# `trained_comp`. Mapped to the same output column rather than published twice.
TEACHER_ALIASES = {
    "total_tch": "total_teacher",
    "trained_comp": "total_teacher_trained_computer",
}

FACILITY_FIELDS: list[tuple[str, str | None, str]] = [
    # building
    ("building_status", None, "building_status_code"),
    ("no_building_blocks", "INT64", "building_blocks"),
    ("pucca_building_blocks", "INT64", "pucca_building_blocks"),
    ("boundary_wall", None, "boundary_wall_code"),
    ("total_class_rooms", "INT64", "classrooms_total"),
    ("other_rooms", "INT64", "other_rooms"),
    ("classrooms_in_good_condition", "INT64", "classrooms_good_condition"),
    ("classrooms_needs_minor_repair", "INT64", "classrooms_need_minor_repair"),
    ("classrooms_needs_major_repair", "INT64", "classrooms_need_major_repair"),
    ("separate_room_for_hm", None, "separate_room_for_head_teacher"),
    # toilets — the counts most used for a girls'-access read
    ("total_boys_toilet", "INT64", "boys_toilets"),
    ("total_boys_func_toilet", "INT64", "boys_toilets_functional"),
    ("total_girls_toilet", "INT64", "girls_toilets"),
    ("total_girls_func_toilet", "INT64", "girls_toilets_functional"),
    ("total_boys_cwsn_toilet", "INT64", "boys_cwsn_toilets"),
    ("func_boys_cwsn_friendly", "INT64", "boys_cwsn_toilets_functional"),
    ("total_girls_cwsn_toilet", "INT64", "girls_cwsn_toilets"),
    ("func_girls_cwsn_friendly", "INT64", "girls_cwsn_toilets_functional"),
    ("urinal_boys", "INT64", "boys_urinals"),
    ("urinal_girls", "INT64", "girls_urinals"),
    ("handwash_near_toilet", None, "handwash_near_toilet"),
    # drinking water. 2020-21 publishes one available/functional pair; 2022-23 on
    # replaces it with a yes/no per source, so the two cannot be compared directly.
    ("drinking_water_available", None, "drinking_water_available"),
    ("drinking_water_functional", None, "drinking_water_functional"),
    ("hand_pump_yn", None, "water_hand_pump_yn"),
    ("well_prot_yn", None, "water_protected_well_yn"),
    ("tap_yn", None, "water_tap_yn"),
    ("othsrc_yn", None, "water_other_source_yn"),
    ("well_unprot_yn", None, "water_unprotected_well_yn"),
    ("pack_water_yn", None, "water_packaged_yn"),
    ("hand_pump_fun_yn", None, "water_hand_pump_functional_yn"),
    ("well_prot_fun_yn", None, "water_protected_well_functional_yn"),
    ("tap_fun_yn", None, "water_tap_functional_yn"),
    ("othsrc_fun_yn", None, "water_other_source_functional_yn"),
    ("well_unprot_fun_yn", None, "water_unprotected_well_functional_yn"),
    ("pack_water_fun_yn", None, "water_packaged_functional_yn"),
    ("rain_water_harvesting", None, "rain_water_harvesting"),
    ("handwash_facility_for_meal", None, "handwash_for_meal"),
    # utilities and amenities
    ("electricity_availability", None, "electricity_code"),
    ("solar_panel", None, "solar_panel"),
    ("library_availability", None, "library_available"),
    ("book_bank", None, "book_bank"),
    ("reading_corner", None, "reading_corner"),
    ("playground_available", None, "playground_available"),
    ("playground_alt_yn", None, "playground_alternative_yn"),
    ("medical_checkups", None, "medical_checkups"),
    ("availability_ramps", None, "ramps_available"),
    ("availability_of_handrails", None, "handrails_available"),
    ("furniture_availability", None, "furniture_code"),
    ("spl_educator_yn", None, "special_educator_code"),
    # laboratories — condition codes, 2022-23 onward
    ("phy_lab_cond", None, "physics_lab_code"),
    ("chem_lab_cond", None, "chemistry_lab_code"),
    ("bio_lab_cond", None, "biology_lab_code"),
    ("math_lab_cond", None, "maths_lab_code"),
    ("lang_lab_cond", None, "language_lab_code"),
    ("geo_lab_cond", None, "geography_lab_code"),
    ("home_sc_lab_cond", None, "home_science_lab_code"),
    ("psycho_lab_cond", None, "psychology_lab_code"),
    ("comp_lab_cond", None, "computer_lab_code"),
    ("comp_ict_lab_yn", None, "computer_ict_lab_yn"),
    ("ict_lab_yn", None, "ict_lab_samagra_yn"),
    ("ict_lab", None, "ict_lab"),
    # digital equipment — counts
    ("laptop", "INT64", "laptops"),
    ("tablet", "INT64", "tablets"),
    ("desktop", "INT64", "desktops"),
    ("digiboard", "INT64", "digital_boards"),
    ("teachdev_tot", "INT64", "teaching_devices"),
    ("server_tot", "INT64", "servers"),
    ("smart_class_tv_tot", "INT64", "smart_classrooms"),
    ("projector", "INT64", "projectors"),
    ("printer", "INT64", "printers"),
    ("internet", None, "internet"),
    ("dth", None, "dth"),
    # 2025-26 additions
    ("librarian_yn", None, "librarian_yn"),
    ("land_avl_yn", None, "land_available_yn"),
    ("kitchen_garden_yn", None, "kitchen_garden_yn"),
    ("staff_qtr_yn", None, "staff_quarters_yn"),
    ("tinkering_lab_yn", None, "tinkering_lab_yn"),
    ("boarding_pri_yn", None, "boarding_primary_yn"),
    ("boarding_upr_yn", None, "boarding_upper_primary_yn"),
    ("boarding_sec_yn", None, "boarding_secondary_yn"),
    ("boarding_hsec_yn", None, "boarding_higher_secondary_yn"),
    ("cyber_safety", "INT64", "students_oriented_cyber_safety"),
    ("psycho_social", "INT64", "students_trained_psychosocial"),
    ("enrichment_activities", None, "enrichment_activities_yn"),
    # safety file group — 2025-26 only. Folded in here rather than given its own
    # table: same grain, same subject (the school's physical and operational
    # environment), and 2025-26's facility file already carries cyber_safety and
    # psycho_social, so splitting would scatter one topic across two tables.
    ("sdmp_plan_yn", None, "disaster_mgmt_plan_yn"),
    ("struct_safaud_yn", None, "structural_safety_audit_yn"),
    ("nonstr_safaud_yn", None, "nonstructural_safety_audit_yn"),
    ("cctv_cam_yn", None, "cctv_yn"),
    ("fire_ext_yn", None, "fire_extinguisher_yn"),
    ("nodal_tch_yn", None, "safety_nodal_teacher_yn"),
    ("safty_trng_yn", None, "safety_training_yn"),
    ("dismgmt_taug_yn", None, "disaster_mgmt_taught_yn"),
    ("slfdef_grt_yn", None, "self_defence_offered_yn"),
    ("slfdef_trained", "INT64", "girls_trained_self_defence"),
    ("guide_display_yn", None, "safety_guidelines_displayed_yn"),
    ("tch_first_level_counsellor", None, "teacher_first_level_counsellor_yn"),
    ("safe_sec_audit", None, "safety_security_audit_yn"),
    ("teacher_displaying_photo", None, "teacher_photo_displayed_yn"),
    ("vidya_pravesh", None, "vidya_pravesh_yn"),
    ("stu_atndnc_yn", None, "student_attendance_tracked_yn"),
    ("tch_atndnc_yn", None, "teacher_attendance_tracked_yn"),
    ("sch_youth_club_yn", None, "youth_club_yn"),
    ("sch_eco_club_yn", None, "eco_club_yn"),
    ("tch_icard_yn", None, "teacher_id_card_yn"),
    ("self_cert_obtained_yn", None, "self_certification_yn"),
]

# 2020-21 misspells the girls' urinal count. Fixed on the way out, as `managment`
# and `psuedocode` are.
FACILITY_ALIASES = {"urinal_girls": "urinla_girls"}


def wide_year_sql(lay, year: str, groups: list[str], fields, aliases: dict[str, str]) -> str:
    """One edition of a wide, one-row-per-school table, ready to UNION."""
    present: dict[str, str] = {}          # source column -> table alias holding it
    for i, group in enumerate(groups):
        if f"{year}/{group}" not in lay:  # a group not published this edition
            continue
        for c in cols(lay, year, group):
            present.setdefault(c, f"t{i}")

    parts = [
        f"    {sql_str(year)} AS academic_year",
        f"    {int(year[:4])} AS academic_year_start",
        "    t0.pseudocode",
    ]
    for source, cast, alias in fields:
        col = source if source in present else aliases.get(source, "")
        if col in present:
            parts.append("    " + _pick([col], col, cast, alias, present[col] + "."))
        else:
            parts.append(f"    CAST(NULL AS {cast or 'STRING'}) AS {alias}")

    staged = [g for g in groups if f"{year}/{g}" in lay]
    frm = f"\n  FROM `{dsp_staging_table(year, staged[0])}` t0"
    for g in staged[1:]:
        i = groups.index(g)
        frm += (f"\n  LEFT JOIN `{dsp_staging_table(year, g)}` t{i}"
                f"\n    ON t{i}.pseudocode = t0.pseudocode")
    return "  SELECT\n" + ",\n".join(parts) + frm


def wide_table_sql(lay, years: list[str], table: str, groups: list[str], fields,
                   aliases: dict[str, str], cluster: str, description: str) -> str:
    usable = [y for y in years if any(f"{y}/{g}" in lay for g in groups)]
    if not usable:
        raise SystemExit(f"no staged groups {groups} for years {years}")
    # Say which editions are going in. A build that quietly covers fewer years than
    # asked for looks identical to a correct one in the row counts.
    skipped = [y for y in years if y not in usable]
    print(f"    editions: {', '.join(usable)}"
          + (f"   SKIPPED (not staged): {', '.join(skipped)}" if skipped else ""))
    body = "\n  UNION ALL\n".join(wide_year_sql(lay, y, groups, fields, aliases) for y in usable)
    return (
        f"CREATE OR REPLACE TABLE `{table}`\n"
        "PARTITION BY RANGE_BUCKET(academic_year_start, GENERATE_ARRAY(2015, 2050, 1))\n"
        f"CLUSTER BY {cluster}\n"
        f"OPTIONS (description = '{description}')\n"
        f"AS\n{body}\n"
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
SELECT 'teacher rows per year', academic_year, CAST(COUNT(*) AS STRING),
       CAST(COUNT(DISTINCT pseudocode) AS STRING)
FROM `{TEACHER_TABLE}` GROUP BY 1, 2
UNION ALL
SELECT 'teachers total', academic_year, CAST(SUM(teachers_total) AS STRING), NULL
FROM `{TEACHER_TABLE}` GROUP BY 1, 2
UNION ALL
SELECT 'facility rows per year', academic_year, CAST(COUNT(*) AS STRING),
       CAST(COUNT(DISTINCT pseudocode) AS STRING)
FROM `{FACILITY_TABLE}` GROUP BY 1, 2
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
    ap.add_argument("--teacher", action="store_true")
    ap.add_argument("--facility", action="store_true")
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
    assert_layouts_match_staging(lay)
    picked = args.dim or args.fact or args.teacher or args.facility or args.validate
    do_dim = args.dim or not picked
    do_fact = args.fact or not picked
    do_teacher = args.teacher or not picked
    do_facility = args.facility or not picked

    if do_dim:
        print(f"→ {DIM_TABLE}")
        bq_query(dim_sql(lay, years), args.print_sql, "dim_school")
    if do_fact:
        print(f"→ {FACT_TABLE}")
        bq_query(fact_sql(lay, years), args.print_sql, "fact_enrolment")
    if do_teacher:
        print(f"→ {TEACHER_TABLE}")
        bq_query(wide_table_sql(
            lay, years, TEACHER_TABLE, ["teacher_data"], TEACHER_FIELDS, TEACHER_ALIASES,
            "pseudocode",
            "UDISE+ DSP teacher counts, one row per school per academic year. Joins to "
            "udise_dim_school_dsp on (academic_year, pseudocode). Academic and professional "
            "qualification are two separate axes that each total the staff - do not add them "
            "together. Built by udise/scripts/dsp_build_bq.py."), args.print_sql, "fact_teacher")
    if do_facility:
        print(f"→ {FACILITY_TABLE}")
        bq_query(wide_table_sql(
            lay, years, FACILITY_TABLE, ["facility_data", "safety"], FACILITY_FIELDS,
            FACILITY_ALIASES, "pseudocode",
            "UDISE+ DSP school facilities and safety, one row per school per academic year. "
            "Joins to udise_dim_school_dsp on (academic_year, pseudocode). 9 = Not Applicable "
            "and No = 2 (not 0) throughout. Column coverage varies sharply by edition - see the "
            "schema YAML. Built by udise/scripts/dsp_build_bq.py."), args.print_sql, "fact_facility")
    # Validation reads BOTH finished tables, so it only makes sense after a full
    # build or when asked for explicitly — running it after `--dim` alone just fails
    # on a fact table that does not exist yet.
    if args.validate or (do_dim and do_fact and do_teacher and do_facility):
        print("→ validation")
        bq_query(VALIDATE_SQL, args.print_sql, "validate")
    print("✓ done.")


if __name__ == "__main__":
    main()
