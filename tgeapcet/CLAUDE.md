# CLAUDE.md — tgeapcet/

Guidance for Claude Code when working inside the `tgeapcet/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

## What this folder is

An ingestion pipeline for TG-EAPCET (Telangana) degree-engineering admission
cutoffs. Source data is the Convener's own Last Rank Statement PDFs (First /
Second / Final Phase), parsed by `state_TG.py` in
[`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2)
(`state_cet/scrape/scripts/`).

## Neutral-fact principle

| Stays in `tgeapcet/` (neutral fact) | Stays in downstream enrichment |
|---|---|
| college_code, college_name, branch_name, institute_type_raw | canonical college_id, NIRF rank |
| category_raw, gender, quota, opening_rank, closing_rank | salary_tier, cutoff trends |
| year, round, state, cet_name, stream, rank_basis | cross-year comparisons |
| college_type (normalised from the PDF's College Type) | |

## Two PDF defects the upstream parser repairs

Both were found in review and both are fixed in `state_TG.py`, not here. If you
touch the parser, keep them fixed — each one silently corrupts closing ranks.

1. **Line-wrap position is unstable between phase files.** The same seat can be
   `ELECTRONICS AND COMMUNICATION ENGINEERING` in P1 and
   `ELECTRONICS AND COMMUNICATION\nENGINEERING` in P2. Grouping on the raw
   string splits one seat into two rows, so `MAX()` never sees the other phase.
   Some wraps also split a word mid-token (`MAHABUBABA\nD`), so collapsing
   whitespace to a single space is not enough — group on an all-whitespace-
   *stripped* key.

2. **Overlapping text runs garble institute names.** On some pages the PDF
   prints the name and the place at the same y-coordinate and pdfplumber
   interleaves them character by character:
   `EARTH SCIENCES` + `KOTHAGUDEM` → `KEAORTTHHA GSCUIDENEMCE)S`. 8 of 162
   colleges, 3 govt-scope. Repaired per `college_code` by picking the cleanest
   spelling.

## Anchors

`build_clean.py` asserts row counts, JNTUH/CSE/OC_BOYS = 1228, and a regression
guard on JNMB/ECE/BC_C_GIRLS = 147994 (that seat shipped as two rows, 147994
and 50629, before defect #1 was fixed). Expect these to fail on a genuine
refresh; update them in the same commit as the cause, never to make a build
pass.

## Grain

`(college_code, branch_code, category_raw, year)`. `category_raw` is
gender-bearing (`OC_BOYS` / `OC_GIRLS`), so `gender` is redundant *with* it and
is not a separate grain key — but it is still a column, because most consumers
filter on it directly.
