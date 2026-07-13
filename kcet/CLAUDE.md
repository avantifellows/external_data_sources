# CLAUDE.md — kcet/

Guidance for Claude Code when working inside the `kcet/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

## What this folder is

An ingestion pipeline for KCET (Karnataka CET) engineering seat-allotment
cutoffs. Source data is KEA's official cutoff PDFs, parsed by `parse_KA_2025.py`
in the `avantifellows/futures-v2` repo and deposited into `kcet/raw/` as a CSV.

## Neutral-fact principle

This table carries only what KEA publishes plus one derived column:

| Stays in `kcet/` (neutral fact) | Stays in downstream enrichment |
|---|---|
| college_code, college_name, course_name_raw, course_name | canonical college_id, NIRF rank |
| category_code, closing_rank, domicile_pool | salary_tier, cutoff trends |
| year, round, state, cet_name, stream | |
| college_type (derived from KEA govt file) | |

`college_type` is an optional historical annotation from KEA's 2024
government-scope file. Explicit government wording in a KEA 2025 college name
can also establish `Govt`. Other unmatched codes remain `Unknown`; absence from
a partial government list is never treated as proof that a college is private.

## Category code system

Each `category_code` encodes **vertical** (reservation) + **horizontal**
(sub-group) in one compact string. GEN pool uses 28 codes, HK pool uses 25.

| Vertical prefix | Meaning |
|---|---|
| `1` | Cat 1 (SC/ST under old OBC list) |
| `2A`, `2B`, `3A`, `3B` | OBC sub-categories |
| `GM` | General Merit |
| `SC`, `ST` | Scheduled Caste / Tribe |
| `NRI`, `OPN`, `OTH` | Special seats |

Horizontal suffix (GEN pool): `G`=General, `K`=Kannada Medium, `R`=Rural, `P`=PWD.
HK pool appends `H`: `1H`, `2AH`, `GMH`, `SCH` …

## Pipeline commands

```bash
# Copy raw files from futures-v2 output into raw/
# Then:
python3 scripts/build_clean.py --dry-run   # validate
python3 scripts/build_clean.py             # write clean/kcet_fact_cutoffs.parquet
python3 scripts/upload_to_gcs.py
python3 scripts/load_bq.py
```

## BQ output

| Table | Rows | Grain | Clustering |
|---|---:|---|---|
| `kcet_fact_cutoffs` | 13,604 | (college_code, course_name, domicile_pool, category_code, year, round) | year, domicile_pool, college_type |

## Design decisions

- **Tall format.** The source PDF is wide (28 category columns per row). We
  unpivot into one row per non-null (college, course, category, rank) — easier
  to query and consistent with how JoSAA data is stored.
- **Only non-null ranks stored.** `--` in the PDF means no allotment; those
  are dropped. The table only contains rows where a seat was actually allotted.
- **Float closing_rank.** KEA publishes fractions including `.5`, `.25`, `.75`,
  and `.875`. Preserve the exact FLOAT; rounding changes source values.
- **Raw + normalized course labels.** `course_name_raw` preserves the minimally
  repaired source label; `course_name` normalizes extraction formatting only.
  Degree prefixes remain because the same college can publish prefixed and
  unprefixed programs with different cutoff series.
- **college_type join.** KEA's main cutoff PDF has no college_type column.
  Joined from the optional 2024 govt-scope file; unmatched = 'Unknown'.
- **Round 3, not Extended Round.** 2025 Extended Round not yet published as
  of ingestion. Re-run pipeline when KEA publishes it; update `round` accordingly.
- **WRITE_TRUNCATE.** Full replace on each pipeline run. Safe because the
  source PDFs are static once published.

## Pitfalls

- **Don't mix GEN and HK pools.** Always filter by `domicile_pool` first —
  they are separate merit lists with different category codes.
- **Don't erase degree prefixes.** `B TECH IN COMPUTER SCIENCE` and `COMPUTER
  SCIENCE` can be distinct seat buckets at one college.
- **Don't commit `raw/` or `clean/`.** `.gitignore` enforces this.
