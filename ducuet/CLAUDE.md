# CLAUDE.md — ducuet

Source-level orientation for the DU CUET cutoffs pipeline. Read the top-level
`../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

University of Delhi undergraduate admission minimum-allocation-scores,
CUET-based CSAS 2025-26 cycle. Upstream is 3 round-wise PDFs published by the
DU Admission Branch (`raw/*.pdf`, gitignored, no stable per-round URL — a
human downloads them once and uploads to GCS; after that `build_clean.py`
fetches from GCS itself). Light PDF parsing (pdfplumber), single build step
(no separate fetch script, unlike `moe/`), so this follows the `nmc/` "PDF
parse" shape, with the `tnea/`-style fetch-from-GCS-if-missing-locally
convention grafted into `build_clean.py` (see `fetch_raw()`).

## Layout

```
ducuet/
├── scripts/
│   ├── sources.py         # config + ROUNDS/RAW_FILENAMES/Table/RawFile registries (single source of truth)
│   ├── build_clean.py     # fetch_raw() pulls missing PDFs from GCS, then parses all 3, MIN per (college, program, category) -> clean/ducuet_fact_cutoffs.parquet
│   ├── upload_to_gcs.py   # raw PDFs (as-is) + clean fact -> gs://…/ducuet/{raw,clean}/
│   └── load_bq.py         # GCS clean/ -> avantifellows.external_data_sources.ducuet_fact_cutoffs
├── schemas/                # ducuet_fact_cutoffs.yaml + README.md ("in 60 seconds")
├── raw/                     # source round PDFs (gitignored; local cache — GCS is canonical)
└── clean/                   # parsed parquet (gitignored)
```

**GCS, not local `raw/`, is the canonical home for the 3 source PDFs.**
`build_clean.py`'s `fetch_raw()` downloads whatever's missing from
`raw/` from `gs://avantifellows-external-data/ducuet/raw/` before parsing —
mirroring `tnea/scripts/build_clean.py`'s pattern — so the build reproduces
from a clean clone. This only works once someone has run
`upload_to_gcs.py --raw-only` at least once for the current cycle's PDFs;
see "Refreshing for a new admission cycle" below.

**One long/tidy fact**, `ducuet_fact_cutoffs` — grain
`(college_name, program_name, category)`. `build_clean.py` parses each round
PDF into rows, keys them on a normalized `(college, program)` tuple
(lowercased, periods stripped), and for each category takes the MIN score
seen across whichever rounds published a non-blank value for that cell —
DU's rounds are NOT cumulative, so a later round can quote a lower score
than an earlier one for the same seat. Add/change the output table in
`scripts/sources.py` (the `TABLES` registry); the loader and uploader
iterate over it.

## Parsing gotchas

- **Two different table layouts across rounds.** Round 1 and Round 3 share
  one pdfplumber extraction shape where every real column is padded with 2
  blank merged-cell columns (`S.NO, ., ., COLLEGE, ., ., PROGRAM, ., ., UR,
  ., ., ...` — real data at indices 0, 3, 6, 9, 12, 15, 18, 21, 24). Round 2
  has no padding but more columns (UR, OBC-NCL, SC, ST, EWS, SIKH, PwBD, KM,
  SGC, ORPHAN×2) at indices 3/4/7/8/9/10/11/12/13/(15,18) — verified against
  both the two-row header and several data pages, since the header's own
  cell-merge pattern does NOT line up with the data rows' pattern (a header
  quirk, not a bug in the parser). `PARSERS` in `build_clean.py` dispatches
  on round number.
- **Program names split across a page break.** A long combination-subject
  program name can wrap onto the next PDF page as a *new* table row with a
  blank S.NO and blank college — pdfplumber sees it as two rows. Both
  parsers detect this shape (`sno` fails `.isdigit()`, `program` non-empty,
  `college` empty) and glue the text onto the previous row's program name
  rather than dropping it or leaving the name truncated (which would also
  break the cross-round join for that seat). Confirmed harmless when the
  row's values are all blank anyway — verified for the one case hit in this
  build (Atma Ram Sanatan Dharma College, Round 3, row 73).
- **Round 2 spells abbreviations with a trailing period; Round 1/3 don't.**
  `B.Sc. (Hons.) Botany` (R2) vs `B.Sc (Hons.) Botany` (R1/R3) — same seat.
  The join key strips periods and lowercases before matching; raw R2/R1/R3
  string equality misses ~1,000 of 1,528 Round 1 rows on this alone.
- **124 Round-2 program rows have no Round 1 (or Round 3) match even after
  normalizing.** These are combination-subject ("BA Program (X + Y)") seats
  that appear to have been opened, closed, or relabelled between rounds —
  verified by checking each unmatched key against every Round 1 row for that
  same college; most have a *similar but different* Round 1 combination
  (e.g. R1 has "Economics + Political Science" and "Economics + History"
  separately; R2 has "Economics + Community Science" for the same college —
  not a spelling variant of either). Deliberately kept as their own rows,
  not fuzzy-matched — see `schemas/README.md`.

## Refreshing for a new admission cycle

1. Download the new cycle's round PDFs from
   [admission.uod.ac.in](https://admission.uod.ac.in/) into `raw/`, matching
   the filenames `ROUNDS`/`RAW_FILENAMES` expect in `sources.py` (bump the
   year in the filename and in `sources.py`'s docstring/comments).
2. Re-check the column layout for each round PDF — confirm real-column
   indices haven't shifted (DU has changed the padding/column set between
   rounds within the same cycle before; re-verify against the header AND a
   few data rows, not just the header, per the gotcha above).
3. `build_clean.py --dry-run` → inspect row/program counts → `build_clean.py`
   → `upload_to_gcs.py` (uploads the new PDFs to GCS — the step that makes
   them fetchable for everyone else) → `load_bq.py`. Loads are
   `WRITE_TRUNCATE`.

## Don't

- Don't commit anything under `raw/` or `clean/` — gitignored data.
- Don't treat a later round's value as authoritative over an earlier
  round's for the same cell — always MIN, never "latest wins".
- Don't join rounds on exact-string `(college, program)` — normalize first.
- Don't fuzzy-match an unmatched Round 2/3 combination-subject program onto
  a similarly-worded Round 1 one; treat it as its own seat.
