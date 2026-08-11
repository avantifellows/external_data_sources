# CLAUDE.md — gujcet/

Guidance for Claude Code when working inside the `gujcet/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

## What this folder is

An ingestion pipeline for Gujarat ACPC admission cutoffs across two streams.
Source data is ACPC's own closure PDFs, parsed by `state_GJ.py` in
[`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2)
(`state_cet/scrape/scripts/`).

## Neutral-fact principle

| Stays in `gujcet/` (neutral fact) | Stays in downstream enrichment |
|---|---|
| college_name, branch_name, institute_type_raw | canonical college_id, NIRF rank |
| category_raw, quota, closing_rank, closing_percentile | salary_tier, cutoff trends |
| year, round, state, cet_name, stream, rank_basis | cross-year comparisons |
| college_type (normalised from ACPC's INST_TYPE) | |
| category / sub_pool (decoded from category_raw) | |

`build_clean.py` **imports the parser's own** `classify_gj_college` and
`normalise_category` rather than reimplementing them — set `GJ_PARSER_DIR`.
Do not copy that logic in here; a second copy will drift (that is exactly what
happened with `state_MH_arch.py` keeping its own decoder).

## The load-bearing facts

1. **Two streams, two admission YEARS** — engineering 2025-26, pharmacy
   2024-25. Every query must scope on year+stream. This is the most likely
   source of a wrong answer from this table.
2. **Two metrics in opposite directions** — `closing_rank` (lower = harder) and
   `closing_percentile` (higher = harder, 0-100 composite). Correlation -0.96.
3. **`closing_rank` is FLOAT** — ACPC publishes tied ranks with `.5`
   (e.g. 36906.5), like KEA does for kcet. Never cast to INT.
4. **TFWS / ESM are horizontal pools**, carried in `sub_pool` over a decoded
   base `category`. Base-category aggregates need `sub_pool = ''`.
5. **PPP is NOT govt** (GIDC Navsari — GIDC land, privately run, private-level
   cutoffs) and **Auto IS govt** (IITRAM — state-funded autonomous). The
   equivalent bug in the UP NEET parser classified `[PPP]` as govt and leaked
   private ranks into govt floors; `build_clean.py` asserts against it.
6. **An absent category row means no admission**, not missing data. `VAC` /
   `------` / `******` cells produce no row.
7. **Home-State quota only.** The All-India (JEE-only) columns in the source
   PDFs are deliberately excluded.

## Scope

All institute types ship. Government scope is a **query**
(`college_type IN ('Govt','Govt-Aided','State-Univ-Dept')`), not a pipeline
decision — same as `kcet/` and `mhtcet/`. Do not add a govt-only filter here;
the college predictor needs private institutes too.

## Refresh

`build_clean.py` hard-asserts per-stream row and institute counts, the L.D.
College CSE OP anchor (closing_rank 646, read off page 3 of the engineering
PDF), and the no-PPP-in-govt invariant. These are designed to fail on a refresh:

1. Confirm the change is real — ACPC republished, or an upstream parser fix.
2. Update expected values **in the same commit** as the cause.
3. Never relax an assertion to make a build pass.

**On the pharmacy year:** a 2025-26 pharmacy file exists on the ACPC portal but
is Round-2 only and rank-only (no percentile column). Final-closure with a
percentile is the better source, so it is deliberately not used. If ACPC
publishes a 2025-26 *closure* PDF, that is the upgrade — note its layout is
long-format (one row per category), not the wide 19-column shape the current
parser expects.
