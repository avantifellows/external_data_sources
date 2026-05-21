-- NIRF engineering rollup by institution tier (IIT / NIT / IIIT / Other NIRF).
-- One row per tier for a given ranking_year. Placement/wage metrics are sparse
-- in nirf_fact_aggregate (populated only on the graduating-cohort academic_year,
-- and an institute reports up to 3 cohorts), so we dedupe to the LATEST cohort
-- per (institute_id, type) before summing — otherwise grads triple-count.
--
-- median wage = wage weighted by placed graduates (Σ salary*placed / Σ placed).
-- Parameterise the year with --parameter=yr:INT64:2022 ... or hardcode below.
WITH agg AS (
  SELECT *,
    CASE
      WHEN REGEXP_CONTAINS(UPPER(institute_name), r"INDIAN INSTITUTE OF TECHNOLOGY") THEN "IIT"
      WHEN REGEXP_CONTAINS(UPPER(institute_name), r"NATIONAL INSTITUTE OF TECHNOLOGY") THEN "NIT"
      WHEN REGEXP_CONTAINS(UPPER(institute_name), r"INDIAN INSTITUTE OF INFORMATION TECHNOLOGY") THEN "IIIT"
      ELSE "Other NIRF" END AS tier
  FROM `avantifellows.external_data_sources.nirf_fact_aggregate`
  WHERE ranking_category = "Engineering" AND ranking_year = @yr
),
latest AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY institute_id, type ORDER BY academic_year DESC) rn
  FROM agg WHERE students_placed IS NOT NULL
)
SELECT
  tier,
  COUNT(DISTINCT institute_id)                                      AS n_inst,
  ROUND(SUM(graduating_on_time))                                    AS graduates,
  ROUND(SUM(students_placed))                                       AS placed,
  ROUND(SUM(higher_studies_selected))                               AS higher_studies,
  ROUND(100 * SUM(students_placed) / SUM(graduating_on_time), 1)    AS placement_rate,
  ROUND(SUM(median_salary * students_placed) / SUM(students_placed)) AS wtd_median_salary
FROM latest WHERE rn = 1
GROUP BY tier;
