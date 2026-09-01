# CLAUDE.md — CMS-E

Orientation for Claude Code working in this source. Read the top-level
`../CLAUDE.md` first for cross-cutting repo conventions.

## What this is

MoSPI's Comprehensive Modular Survey: Education (CMS-E), NSS 80th Round,
April–June 2025. Household expenditure on **school education only**, plus the
household roster that shows who is **not enrolled at all**. Unit-level microdata:
three CSVs in, three BigQuery tables out.

Shape: heavy local parse (like `plfs/`) + GCS staging (like `nirf/`).

## The pipeline

```
raw/*.csv  ──clean_cmse.py──▶  clean/*.parquet  ──upload_to_gcs.py──▶  GCS  ──load_bq.py──▶  BQ
```

`scripts/sources.py` is the single source of truth — GCS paths, BQ identifiers,
table definitions, and every official code list. Change a decode there, not in
the transform.

## What the transform actually owns

`clean_cmse.py` is not a pass-through. It does seven things that matter, and
each exists because the raw data is wrong or misleading without it:

1. **Derives `state_code`.** The raw files have no state column — it is the
   first 2 digits of `nss_region`. Without this there is no state-level analysis
   at all, which is half the point of the table.
2. **Renames two MoSPI columns that say the opposite of what they mean.**
   `any_member_attending_school` / `num_members_attending_school` are about
   *erstwhile* members who have left the household, not members attending
   school. 1,273 households vs 34,468 that actually contain a student — a 27x
   undercount if read literally. See `MISNAMED` in the transform.
3. **Applies `weight = mult / 100`**, per MoSPI's own README.
4. **Separates a true zero from an unknown.** "No expenditure incurred" is a
   surveyed zero and is stored as `0`. "Not known" stays NULL. On the away cut
   the reporting-status codes also encode "free tuition" and "free boarding",
   which are zeros, not blanks.
5. **Unifies two different expenditure schemas.** Resident students get a
   five-way itemisation (block 5); students living away get lump sums (block 4).
   Both land in the same table with a `cut` discriminator and a common set of
   roll-up columns. Itemised columns are NULL on the away cut by design.
6. **Derives `unallocated_expenditure`** — how much an away student's lump sum
   exceeds its named parts. For a residential coaching package that residual is
   where the unseparable coaching fee sits.
7. **Reconciles against 14 published MoSPI figures and refuses to write if any
   drifts.** This is the guard rail; do not weaken it. If a change is genuinely
   correct and moves a number, update the expected value *and say why in the
   commit message*.
8. **Emits `cmse_fact_person` — the roster, enrolled or not.** `cmse_fact_student`
   holds only enrolled students, so "who is not in school" cannot be asked of it.
   The roster can. Two things make it safe, and both are asserted rather than
   assumed: it is filtered on MoSPI's own enrolment gate (`currently_enrolled_school`),
   whose blanks are exactly the under-3s the question was never put to — so the
   denominator is right by construction — and its enrolled half must be *exactly, as
   a row set*, the student table's `resident` cut. That second check is its whole
   reconciliation, because MoSPI publishes no out-of-school figure for CMS-E.
   `scripts/check_person_guards.py` breaks each of those guards on purpose and fails
   if any of them waves it through — run it after touching the roster. Its second
   case is the one to understand: an enrolled half with the *same row count* as the
   student table but two different people in it, which a count check would pass.

## Non-obvious things you will get wrong

Full detail in `schemas/README.md`. The short list:

- **Government in-kind support is valued at zero by instruction** (free books,
  uniforms, tuition). Non-government support IS imputed in. The government-school
  spend figure is net; the private one is gross. They are not comparable as-is.
- **Integrated coaching does not appear in the coaching columns.** Narayana,
  Sri Chaitanya, Deeksha — exam prep bundled into the junior-college fee, so the
  household answers "no private coaching" and the money lands in
  `school_exp_course_fee`. The 113-page manual never mentions the model. Threshold
  on `total_education_expenditure` to catch it.
- **State fee regulation confounds any uniform rupee threshold.** AP caps junior
  college fees at ~Rs 37,500; Telangana does not. A Rs 50,000 cut-off finds
  Telangana and misses AP entirely, for regulatory reasons, not market ones.
- **`is_student_hostel_household` must be filtered out of per-capita work.**
  Single-member hostel "households" invert the top decile.
- **`mpce` ranks, it does not level.** Five questions vs HCES's ~400 items, and
  ~29% low against HCES. Use `hces_fact_household_master` for rupee thresholds
  and poverty work.
- **`enrolment_level_code = '15'` is pre-primary, not post-XII.** Sorting on the
  code puts the youngest children last. Use `enrolment_stage`.
- **Nothing on stream or aspiration.** Class XI/XII carry a bare class number —
  no science/commerce/arts. Zero hits in the manual. Do not invent a proxy
  without saying so.
- **An out-of-school rate is only defined up to age 17.** Filter `is_school_age` on
  `cmse_fact_person`. Above 17 this survey cannot separate "not in school" from "in
  a degree programme": the 18-24 band reads 95.8% not-enrolled, which is a fact
  about the instrument, not about those people. And 3-5 is not a compulsory-schooling
  gap (46.2%, because pre-primary is optional), so a blended 3-17 rate mixes two
  different things — report by band, or restrict to 6-17.

## Don'ts

- Don't publish population totals, sex ratios, or religion/social-group
  distributions of Indian households from this survey. MoSPI's note to data users
  says the auxiliary variables exist to disaggregate education spend, full stop.
  **`cmse_fact_person` makes this easy to get wrong** — a person-level roster turns
  every one of those into a one-line query, and they stay wrong. It licenses a RATE
  WITHIN A CELL ("what share of ST 15-17s in Bihar are out of school"), never a
  count of people.
- Don't add derived analysis columns to the fact tables. Rollups and segment
  definitions (the "integrated signature", spend tiers) are analysis SQL and
  belong in the data-assistant analysis-intent catalog, not here.
- Don't commit anything under `raw/` or `clean/`. Both are gitignored; the bytes
  live in GCS.
- Don't hand-edit `codemaps/*.csv` — regenerate with `build_codemaps.py` from the
  official xlsx in `docs/`.

## Re-running

Idempotent end to end. `load_bq.py` is WRITE_TRUNCATE and iterates `S.TABLES`, so
adding a table means adding it there and nowhere else. There is no schedule and
no successor round announced — this runs on demand.
