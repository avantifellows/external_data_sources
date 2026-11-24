# CLAUDE.md — state_cet/

Guidance for Claude Code working inside `state_cet/`. See the
[top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions and
[`schemas/README.md`](schemas/README.md) for the domain primer.

## What this folder is

A light-parse ingestion pipeline for India's STATE engineering CET cutoffs
(MHT-CET, KCET, TNEA, EAMCET, WBJEE, KEAM, ACPC, BCECE, OJEE, …) — the
state-quota counterpart to [`josaa/`](../josaa/). 10 states, ~7.8k rows.
Built off the College DB `state-cet-scrape` consolidated output.

## The raw/domain split — and where it's blurrier than josaa

Unlike josaa (which ships JoSAA's untouched published table), the state-CET
consolidated file is **already curated** upstream. We ship it as-is but
document the curation loudly:

| In this source (ships the consolidated product) | In College DB `state-cet-scrape/` (not crossed over) |
|---|---|
| Govt-scope closing ranks/marks, 5-cat category, `rank_basis`, `source_url` | Original state category labels (GM/2A/SM/EZ/…) |
| `college_type` (Govt / State-Univ-Dept / Govt-Aided) | Private/deemed colleges (excluded by govt scope) |
| — | Per-round series; per-state "_all_cutoffs" raw files |
| — | Avanti salary tiers / stream-tier cutoffs / bucketing |

So three upstream curation choices are baked in: **govt-scope filter,
5-cat harmonization, closing=final-round.** This is a pragmatic call — the
consolidated file is the analyst-ready product tools will query. If a future
need wants truly raw (all categories with original labels, all college types,
per-round), that is a *separate, bigger* ingestion off the per-state
`_all_cutoffs` files — do it as its own table/source, don't retrofit here.

**Do not** add Avanti tier/bucketing columns here.

## Commands

See [README.md](README.md): `build_clean.py` → `upload_to_gcs.py --raw` →
`load_bq.py`. Each takes `--dry-run`.

## BQ output

| Table | Rows | Grain | Clustering |
|---|---:|---|---|
| `state_cet_fact_closing_ranks` | ~7.8k | (state, cet_name, stream, year, college_code, branch_code, quota, category, gender) | state, cet_name, year, category |

Column docs: [`schemas/state_cet_fact_closing_ranks.yaml`](schemas/state_cet_fact_closing_ranks.yaml).

## Design calls worth knowing

- **Rank scales differ per CET; some are mark-based.** `rank_basis` is the
  decoder; `*_mark` columns hold marks for mark-based CETs (TNEA), `*_rank`
  is NULL there. Never compare ranks across states blindly.
- **`round` is free-text, not an integer** (states describe their final
  allotment differently). `last_round_with_max` says which round the closing
  value came from. Don't try to cast `round` to INT.
- **college_name had embedded PDF newlines** — `build_clean.py` flattens them
  to single spaces. Names still drift across states; keyword-match.
- **WRITE_TRUNCATE, overwrite-in-place.** A refresh replaces the whole table.

## Pitfalls

- **Don't commit `raw/` or `clean/`.** `.gitignore` enforces it; GCS is canonical.
- **Don't present this as untouched source.** It's govt-scope + 5-cat +
  final-round curated. The schema says so — keep it honest.
- **Don't compare cutoffs across CETs without `rank_basis`.**
- **Don't equality-match `college_name`.**
