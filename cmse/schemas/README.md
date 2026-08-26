▶ NEXT: open the paired data-assistant PR (schema copies + analysis-intent block + regenerated CLAUDE.md).

# CMS-E schemas

| Table | Grain | Rows |
|---|---|---|
| [`cmse_fact_student`](cmse_fact_student.yaml) | one row per student | 59,417 |
| [`cmse_fact_household`](cmse_fact_household.yaml) | one row per surveyed household | 52,085 |

Join on `household_id`.

---

## CMS-E concepts in 60 seconds

**What it is.** The Comprehensive Modular Survey: Education — MoSPI's nationally
representative survey of **what Indian households spend on school education**.
Fielded April–June 2025 as part of the NSS 80th Round, by computer-assisted
personal interview, covering 2,384 villages and 1,982 urban blocks. It is a
one-shot cross-section: there is no earlier CMS-E and no panel.

**What "school education" means here.** Pre-primary (`enrolment_level_code` =
'15') through Class XII, plus diplomas at secondary and higher-secondary
equivalence. **No higher education at all.** That is the deliberate break from
the old NSS 75th-round education survey, which covered every level.

**What it does not have.** No learning outcomes — no marks, no test scores, no
attendance, no school quality. No stream: Class XI and XII carry a bare class
number with no science/commerce/arts marker, and nothing on aspiration or exam
registration. No income; consumption is the only welfare variable.

**Weights.** Every estimate needs them. `weight` = the published multiplier /
100, and it is the number of real students (or households) a row stands for.
`COUNT(*)` is a sample size. Rows in the same second-stage stratum within an FSU
share a weight, so the effective sample is well below the row count — a cut with
fewer than ~100 sampled rows is directional at best.

**The two cuts.** `cmse_fact_student.cut` separates students living in the
sampled household (`'resident'`, 57,742, full itemised expenditure) from students
who have left it to study elsewhere (`'away_from_home'`, 1,675, lump sums only).
Both are real students. The itemised `school_exp_*` and `coaching_exp_*` columns
are NULL on the away cut by design — never compare them across cuts.

---

## Four traps that change the numbers

**1. Government in-kind support is valued at zero, by instruction.** The field
manual tells enumerators that where the Government provides free books, uniforms
or tuition, *"no imputation will be made and value will be considered as zero"* —
while support from other households or non-government organisations **is**
imputed in. So the Rs 2,863/yr government-school figure is out-of-pocket *after*
government support, and the Rs 25,002 non-government figure is gross. Comparing
them directly compares a net number to a gross one. The asymmetry runs the other
way for NGO-supported students, whose support is imputed back in and makes them
look like higher spenders.

**2. Integrated coaching is invisible to the coaching columns.** The survey asks
"did you receive private coaching/tuition" as a *separate* question. A student at
an integrated junior college — Narayana, Sri Chaitanya, Deeksha — whose exam prep
*is* the school correctly answers **no**, and the whole fee lands in
`school_exp_course_fee`. The manual has zero occurrences of "integrated", "junior
college", "intermediate" or "residential school" across all 113 pages; the model
is not contemplated anywhere in the instrument.

Consequence: any coaching market built from `received_private_coaching` alone
materially undercounts Karnataka, Telangana, Tamil Nadu and Andhra Pradesh. To
catch integrated schooling *and* Kota-style residential coaching in one filter,
threshold on `total_education_expenditure`, not `coaching_expenditure`.

**3. Fee regulation, not demand, drives the state pattern.** Andhra Pradesh caps
private junior-college fees (Rs 15,000–17,500 tuition + Rs 20,000 permitted
tutorial fee for IIT/JEE/NEET coaching — a Rs 37,500 ceiling). Telangana's
equivalent bill was submitted in January 2025 and remains in Cabinet. The
microdata shows it plainly: AP's private Class XI–XII fee distribution truncates
at p90 = Rs 40,000 with 4.3% above Rs 50,000, while Telangana — the same
institutions, the neighbouring state — runs p90 = Rs 85,000 with 25.3% above
Rs 50,000. A uniform rupee threshold across states measures the regulatory
regime, not the market. Vary the threshold by state or you will conclude AP has
no integrated sector.

**4. Single-member hostel households invert per-capita rankings.** 141 Class XII
students are surveyed as their own one- or two-person household (block 3 Q6
exists for exactly this case). Their "household consumption" is one teenager's,
so `mpce_per_capita` ranks them spuriously high while `mpce` ranks them
spuriously low — enough to make the top per-capita decile show *lower* household
consumption than the ninth. Filter `is_student_hostel_household = FALSE` for any
distribution work; keep them for expenditure totals, where they are real
students.

---

## MPCE: rank with it, never level with it

`mpce` is collected in **five questions**. HCES uses a ~400-item schedule. The
gap is large and one-directional:

| | CMS-E 2025 | HCES 2023-24 published |
|---|---|---|
| Rural per-capita | Rs 2,938 | Rs 4,122 |
| Urban per-capita | Rs 4,975 | Rs 6,996 |

About 29% low against a survey taken a *year earlier*, so the true 2025 gap is
wider. This is short-recall aggregation bias, and it is exactly what MoSPI's note
to data users warns about.

**Deciles, quintiles and richer-vs-poorer orderings are sound.** Rupee
thresholds, consumption levels and poverty headcounts are not — for those use
[`hces_fact_household_master`](../../hces/schemas/hces_fact_household_master.yaml),
which is built for it and carries a derived income projection besides.

---

## Two columns renamed from the source

MoSPI's released CSV labels block 3 items 7 and 8 as
`any_member_attending_school` and `num_members_attending_school`. The Data Layout
is unambiguous that both are about **erstwhile** members — people who have *left*
the household to study. Only 1,273 households answer yes, against 34,468 that
actually contain a student.

They are `has_erstwhile_student` and `num_erstwhile_students` here. Taken at face
value the published names undercount by 27x.

---

## Reconciliation

`clean_cmse.py` refuses to write output unless all fourteen figures MoSPI
published in [PIB release 275295](https://archive.pib.gov.in/newsite/PrintRelease.aspx?relid=275295)
reproduce from the tables — enrolment shares by sector, fee-paying rates,
average spend by school type, coaching rates, and the funding-source split.
Every one currently matches to the published precision. If a future edit drifts,
the build fails rather than emitting unverified numbers.
