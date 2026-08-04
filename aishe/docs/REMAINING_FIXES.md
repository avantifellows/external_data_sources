# AISHE — the four remaining table failures

Written to be picked up cold. Everything here was measured, not assumed; where an
earlier diagnosis in this repo turned out to be wrong that is called out, because
two of them were.

State as of 2026-08-05: **42,597 rows, 12 years, 7 of them with nothing
outstanding.** `docs/INGEST_AUDIT.md` is generated — run
`scripts/audit_coverage.py` after any build to refresh it.

## Ground rules (do not skip)

1. **Never register a `(year, table)` pair that fails its reconciliation.** The
   checks are the only thing making this table trustworthy. `sources.py` carries a
   measured delta and a named cause for every pair left out.
2. **Never widen a tolerance to make a check pass.** A source discrepancy gets a
   registered, evidenced exception (`PUBLISHER_ROUNDING`,
   `INDEPENDENTLY_ROUNDED`), never an epsilon.
3. **Before blaming the parser, check whether the gap equals a whole level or a
   whole published sub-total.** This is the trap that cost the most time: 2015-16
   Table 34 was logged as a −638,114 parse bug when the parse was perfect and the
   *anchor* was wrong. See `PROGRAMME_CUT_EXCLUDES_LEVELS` in `clean_aishe.py`.
4. **Reconciliation checks sums, not labels.** A mangled state or discipline *name*
   passes every total check. `_check_state_labels` covers the state cuts; there is
   no equivalent for disciplines or programmes yet.
5. Verify with `.venv/bin/python scripts/clean_aishe.py` — it runs every check and
   fails the build rather than writing a bad parquet.

## Do these as separate commits, in this order

### 1. (2016-17, T34) — off by −1,992 Total

Cheapest of the four and the same class as the 2018-19 fix that already landed.

- Anchor: Table 33's Grand Total. This edition's T34 **does** include diplomas, so
  compare against the full Grand Total (unlike 2015-16 — see rule 3).
- Measured: Male −854, Female −1,138, Total −1,992 against 4,398,169 / 4,554,917 /
  8,953,086. A ~0.02% shortfall, so a handful of rows.
- 2018-19's identical symptom was rows printing fewer than three figures (a blank
  gender cell, or no out-turn at all). `_sparse_row` handles the shapes seen so
  far; this edition evidently has one it rejects.
- Start here:
  ```bash
  .venv/bin/python - <<'EOF'
  import sys, io, contextlib; sys.path.insert(0,'scripts')
  import pdfplumber, parse_report_pdf as P
  from sources import PDF_REPORTS, T34
  with pdfplumber.open(PDF_REPORTS['2016-17']) as pdf:
      for pno in P._find_pages(pdf, T34[1], '2016-17'):
          with contextlib.redirect_stdout(io.StringIO()):
              kept, skipped, totals = P._three_col_rows(pdf.pages[pno], "x",
                                                        join_wrapped=True)
          print(f"p{pno+1}: kept={len(kept)}")
          for s in skipped: print("   skipped:", repr(s))
  EOF
  ```
  Anything in `skipped` that is a real programme row is the bug. That is exactly
  how 2018-19's −51 was found.
- Register `("2016-17", T34)` in `PDF_TABLES` only once `clean_aishe.py` passes.

### 2. (2017-18, T34) — off by −7,328 Male

Same class, more of it. Its own Grand Total is the anchor (4,323,271 Male). Use the
same diagnostic. Worth doing straight after #1 — likely the same root cause.

### 3. (2017-18, T12) — off by **+38,652** Male

Note the sign: we are reading **too much**, so a row is being counted twice or a
subject row is being taken as a discipline.

- Table 12 nests subjects under disciplines and only discipline rows are kept,
  identified by their left-margin x position. This edition indents the
  discipline/subject columns differently from the other three.
- The margin is measured across **all** of the table's pages
  (`discipline_rows`) — check what it resolves to here versus 2018-19.
- Cross-check available: UG enrolment has no published anchor for this year, but
  the disciplines must sum to the table's own Grand Total row.

### 4. (2016-17, T35) and (2017-18, T35) — a one-row vertical offset

**The note that used to be in `sources.py` was wrong** — these are not "ranked
lists". Rendering the page disproved it. They are the ordinary discipline/subject
hierarchy, the same shape as Table 12. The real defect is a constant **one-row
offset between the label column and the value columns**, so pdfplumber's line
banding pairs every label with the *next* row's figures:

```
'Journalism & Mass Communication'            <- its figures went to the line below
'Social Work 2831 2372 5203'                 <- Social Work's label + Journalism's figures
'Fashion Technology 2573 2567 5140'          <- + Social Work's figures
'Grand Total 314264395 33137378 645638463'   <- last data row merged into the total
```

That merge is where the impossible "published Grand Total" of 314,264,395 comes
from — so **the anchor has to be fixed before the rows are.**

- **Fix direction:** pair the k-th label with the k-th value-triple by rank down
  the page, instead of trusting line banding. A constant offset is precisely what
  banding cannot survive. Count labels and value-triples first and only rank-pair
  when the two agree — a wrapped label would otherwise shift everything.
- **Real anchor, already confirmed against the page:** this table's Grand Total
  equals Table 33's Under Graduate level — 3,142,649 Male for 2016-17.
- **Do NOT transcribe these from the rendered image.** It freezes the figures,
  breaks on the next edition, and leaves ~46 rows checked only against a total read
  by the same fallible eye. Every other number in this table reconciles against a
  machine-read published total.
- **Highest-risk change of the four.** It touches `_lines`, and `CLAUDE.md` records
  that a previous rework of that banding regressed other pages. Re-run the full
  build afterwards and confirm all seven currently-clean years still pass.

## Not attempted at all: 2012-13 → 2014-15, tables 12/33/34/35

Twelve `(year, table)` pairs. Those three years currently contribute only the
social cut (Tables 14/15). Nothing is known to be wrong with them — they have
simply never been registered. Do them one at a time, after the four above, and
expect the same per-edition layout drift.

## Also open

- **GER / GPI time series** (`raw/aishe_timeseries_*.pdf`) — both parsed and
  verified, 2011-12 → 2021-22. Its own table, its own PR. GPI is **not** derivable
  from GER: checked all 33 cells, and published GPI runs up to 0.055 below
  female-GER/male-GER, so both series must be stored.
- **2023-24 Table 35** — that edition publishes no UG-discipline out-turn table at
  all. Nothing to fix; the audit records it so it is not mistaken for a gap.
