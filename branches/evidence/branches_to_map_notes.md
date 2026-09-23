# Branch strings from our cutoff tables — for the branch sheet

**`branches_to_map.csv`** — the working sheet: 564 distinct branch strings
from our cutoff tables that are NOT yet in "branch - Branch" (matched after
normalizing case/punctuation and stripping quota markers). One row per
distinct string; `exams` lists everywhere it appears. Fill
`maps_to_branch_id` (existing parent id, or a new one). Rows sort by our
`suggested_primary_branch` guess so same-family strings sit together — the
guess is keyword-based, trust but verify. Only 16 rows have no guess.

**`branches_from_cutoff_tables.csv`** — the evidence: all 1,594 per-exam
rows including the 872 already covered by the sheet (with their matched
branch_id), row/college counts per exam. NEW rows first.

Notes:
- **AP-EAPCET codes are expanded to full names** from the official EAPCET
  course list (all 73 codes resolved — incl. QC = Quantum Computing at
  AUCE and CSED = CSE-DevOps at Mohan Babu). The raw 3-letter code stays
  in `branch_raw`; the legend lives in the pipeline repo as
  `apeapcet/branch_codes.csv`.
- **The OJEE text corruption is fixed at the source** (the PDF overprinted
  institute names into programme text at 8 institutes) — these rows now
  carry clean names; nothing here needs skipping.
- `branch_clean` strips seat-quota suffixes — "(TFW)", "(SS)", "(SSC)" —
  which are seat types, not branches.
- Sources: JoSAA (2016-25), KCET, MHT-CET, TG-EAPCET, AP-EAPCET, GUJCET,
  TNEA, WBJEE (2021-26), KEAM, OJEE, CLAT, NEET programs, college-fees sheet.
