# CLAUDE.md — state_medical/

Guidance for Claude Code working inside `state_medical/`. See the
[top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions and
[`schemas/README.md`](schemas/README.md) for the domain primer.

## What this folder is

A light-parse / heavy-provenance ingestion pipeline for state-quota (~85%)
MBBS/BDS cutoffs, counselled by ~30 state authorities, harmonized across 32
states/UTs. The state-quota counterpart to [`mcc/`](../mcc/) (national AIQ).
Built off the College DB medical-state-counselling national consolidation.

## The raw/domain split — the sharpest call in this migration

The upstream national file is the most Avanti-derived of all the College DB
outputs. We ship a NEUTRAL PROJECTION and drop the modeling:

| Kept here (neutral published fact) | Dropped — stays in College DB (Avanti modeling) |
|---|---|
| `closing_rank` (native scale) | `air_unified` (estimated cross-state AIR) |
| `rank_space` (NEET AIR vs state-native), `conversion_method` | `neet_score_implied` |
| `category` (canonical) + `category_raw` | `tier` (salary tier) |
| `source_quality`, `is_estimated`, `round` | `multiplier_applied`, `estimated_R3_closing_rank`, `confidence` |

**The cost:** for ~25% of rows (`rank_space = 'state-native'`) there is no
cross-state-comparable number in this table — the AIR estimate that makes them
comparable is Avanti modeling and lives in College DB. This was a deliberate
neutrality call. If a future need wants the comparable AIR in BQ, treat it as a
SEPARATE derived table/source clearly marked as estimated — do NOT fold the
estimate back into this neutral fact.

**Do not** add tier, air_unified, or estimate columns here.

## Commands

See [README.md](README.md): `build_clean.py` → `upload_to_gcs.py --raw` →
`load_bq.py`. Each takes `--dry-run`.

## BQ output

| Table | Rows | Grain | Clustering |
|---|---:|---|---|
| `state_medical_fact_closing_ranks` | ~2.9k | (state, college, program, category, round) | state, program, category, year |

Column docs: [`schemas/state_medical_fact_closing_ranks.yaml`](schemas/state_medical_fact_closing_ranks.yaml).

## Design calls worth knowing

- **Source = the unified_AIR file, projected** — NOT the per-state files (22
  heterogeneous schemas) and NOT the normalized file (which lacks
  `conversion_method`, the column that documents each native scale). The
  unified file is the only one with the provenance we keep; we just drop its
  estimate columns.
- **`rank_space` is derived** from `conversion_method` ('native AIR' → 'NEET
  AIR', else 'state-native'). It's the single most important column for correct
  querying. Keep it.
- **`closing_rank` is rounded to INT** (upstream stored some as float). Scale
  varies by row — never compare across rank_space.
- **`state` is a 2-letter code**; `codemaps/state_code.csv` maps to full names.
- **WRITE_TRUNCATE, overwrite-in-place.**

## Pitfalls

- **Don't commit `raw/` or `clean/`.** GCS is canonical.
- **Don't ship or reintroduce the AIR estimate / tiers here.** Neutral only.
- **Don't compare `state-native` closing ranks across states**, or against AIR.
- **Don't cast `round` to INT** — it's free text ('R1+R2+R3', 'MopUp', …).
- **Don't equality-match `college`.**
