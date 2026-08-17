# CLAUDE.md — mcc/

Guidance for Claude Code working inside `mcc/`. See the
[top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions and
[`schemas/README.md`](schemas/README.md) for the domain primer.

## What this folder is

A light-parse ingestion pipeline for MCC (Medical Counselling Committee) All
India Quota cutoffs — national MBBS/BDS/Nursing closing NEET ranks. Medical
counterpart to [`josaa/`](../josaa/); national counterpart to
[`state_medical/`](../state_medical/). Built off the College DB
medical-national-ranks pipeline.

## mcc vs nmc — keep distinct

- **`mcc/`** (this folder) = MCC **counselling** outcomes: who was allotted a
  seat, at what NEET rank, in which quota/category. The cutoffs.
- **`nmc/`** = NMC **regulator** data: official seat matrix / college registry
  (stub today). Different authority, different grain. Do NOT merge them.

## The raw/domain split

Ships the **full AIQ allotment** — NOT govt-filtered. That's deliberate: the
neutral fact is everything MCC counsels (All India 15% + deemed + paid + NRI +
ESI + university quotas). College DB keeps the govt-scoped cut + institute_type
classification + Avanti tiers. `quota = 'All India'` recovers the govt AIQ pool.

| In this source (neutral allotment) | In College DB (not crossed over) |
|---|---|
| All quotas/courses, `category` + `is_pwd`, `allotted_count` | govt-only scope, `institute_type` (Central-AIIMS / State-Govt / …) |
| NEET AIR opening/closing | Avanti salary tiers, college bucketing |
| — | State-quota 85% seats → those go to `state_medical/` |

**Do not** add institute_type or Avanti tier columns here.

## Commands

See [README.md](README.md): `build_clean.py` → `upload_to_gcs.py --raw` →
`load_bq.py`. Each takes `--dry-run`.

## BQ output

| Table | Rows | Grain | Clustering |
|---|---:|---|---|
| `mcc_fact_closing_ranks` | ~3.1k | (institute, course, quota, category, is_pwd, year, round) | year, round, course, category |

Column docs: [`schemas/mcc_fact_closing_ranks.yaml`](schemas/mcc_fact_closing_ranks.yaml).

## Design calls worth knowing

- **Source is the full AIQ R1 file** (`closing_ranks_aiq_r1_2025.csv`, ~3.1k
  rows), NOT the govt-scoped `govt_medical_closing_ranks_*` (which adds Avanti
  institute_type). Picked the neutral one on purpose.
- **`alloted_category` is split** into `category` + `is_pwd` in build_clean —
  cleaner than carrying "Open PwD" strings.
- **year/round are stamped constants** from `sources.py` (this file is the
  2025-26 cycle, R1). When R2/R3 are unioned upstream, either bump the source
  file + constants or extend build_clean to read multiple round files and keep
  `round` per-row.
- **closing_rank is a NEET AIR.** Huge values for BDS/paid/deemed are normal.
- **WRITE_TRUNCATE, overwrite-in-place.**

## Pitfalls

- **Don't commit `raw/` or `clean/`.** GCS is canonical.
- **Don't confuse mcc with nmc.** Counselling vs regulator.
- **Don't drop the quota filter when someone asks for "govt medical cutoffs"** —
  that means `quota = 'All India'` here, not all rows.
- **Don't equality-match `institute`.**
