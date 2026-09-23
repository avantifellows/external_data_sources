# DU CUET cutoffs in 60 seconds

The University of Delhi allocates undergraduate seats across CUET-based CSAS
rounds. Each round, the Admission Branch publishes a PDF of that round's
**minimum allocation score** — the lowest CUET composite score that got
someone a seat — per (college, program, category). This table combines the
3 round PDFs published for 2025-26 into one fact.

## The one thing that will bite you: rounds are not cumulative

A later round can quote a **lower** score than an earlier round for the
exact same seat. Rounds reallocate that round's vacant seats against
whoever is still in the applicant pool — they are not a monotonic tightening
of one merit list. So there is no "the Round 3 number is final" shortcut:

```sql
-- WRONG: assumes round 3 is authoritative for every cell
SELECT * FROM ducuet_fact_cutoffs WHERE rounds_published LIKE '%3%'

-- RIGHT: this table already took MIN across whichever rounds published a
-- value for that (college, program, category) — just query it directly
SELECT * FROM ducuet_fact_cutoffs
WHERE college_name = 'Hindu College' AND program_name LIKE 'B.Sc%'
```

`rounds_published` tells you which of Round 1/2/3 actually had a non-blank
score for that cell, for traceability back to the source PDF — it is not
something you need to filter on to get the right number.

## A blank category means no seat, not a score of 0

If UR/OBC/SC/... is absent for a (college, program) across all 3 rounds, no
seat opened in that category in any round published. Absence ≠ 0 — don't
`COALESCE(min_allocation_score, 0)`.

## Program-name matching is normalized across rounds

Round 2's PDF consistently spells abbreviations with a trailing period that
Round 1 and Round 3 omit — e.g. `B.Sc. (Hons.) Botany` (Round 2) vs
`B.Sc (Hons.) Botany` (Round 1/3), same seat. Rows are joined across rounds
on `lower(college + program)` with periods stripped and whitespace
collapsed, not on exact string equality. `program_name` in the output keeps
the Round 1 (or earliest available) spelling for display.

## 124 program rows exist only from Round 2

After normalizing punctuation, 124 "BA Program (X + Y)" combination-subject
rows in Round 2 still have no matching Round 1 row for
the same college — not because of a typo, but because DU opens, closes, or
relabels some combination-subject seats between rounds (e.g. a college's
Round 1 offers "Economics + Political Science" and "Economics + History" as
separate seats; Round 2 offers "Economics + Community Science" for the same
college, a combination Round 1 never listed). These are kept as their own
`(college_name, program_name)` rows rather than fuzzy-matched onto a
similarly-worded Round 1 combination — a fuzzy match would silently
attribute one seat's cutoff to a different subject pairing.

## Categories in scope: UR, OBC, SC, ST, EWS, PwBD

These 6 are the categories Round 1 and Round 3 report, and the ones Round 2
also reports (as `OBC-NCL`, folded into `OBC` here). Round 2 additionally
publishes SIKH, KM, SGC, and ORPHAN (Female/Male) minority/special-category
columns that Round 1/3 don't — those are parsed during the build but
dropped from this fact, since a MIN "across the 3 rounds" is meaningless for
a category only one round even reports.

## Higher score = harder to get in

`min_allocation_score` is a CUET composite allocation score (not a rank) —
higher means a harder-to-clear seat, opposite of KCET/JoSAA-style rank
columns elsewhere in this repo.

## Reproducibility

The 3 source round PDFs and the clean parquet live under
`gs://avantifellows-external-data/ducuet/`. The parser is
[`scripts/build_clean.py`](../scripts/build_clean.py) in this folder.
