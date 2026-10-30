# CLAUDE.md — acpmec/

Guidance for Claude Code when working inside the `acpmec/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

## What this folder is

Gujarat's 2026-27 institute lists for BDS, BAMS, BHMS, B.Sc. Nursing and the
allied health degrees, from medadmgujarat.org. One table,
`acpmec_dim_institutes`, one row per course x institute.

## The load-bearing facts

1. **Ownership comes from the committee's type column** (GOV / GIA / SFI),
   never from the name. GMERS colleges are societies; their type is what the
   list prints.
2. **`inst_label` is the committee's key** — the same code its last-rank
   PDFs use (`AP - GOV Ahmedabad`, `AAY - GQ`). Keep it verbatim.
3. **One institute, several rows** when it teaches several courses; nothing
   here says two rows are one campus.
4. **`intake = 0` is real** (BAMS/BHMS colleges denied or awaiting NCISM /
   NCH permission). `intake` null is a blank in the list (the OT file has no intake column;
   two optometry and one physiotherapy cell are blank).

## Refresh

`build_clean.py` asserts that each file's intake sums to the total the
committee prints, and the per-course institute counts. On a new cycle:
download the new lists (URLs pattern in `sources.py`), confirm the changes
are real, update `ACADEMIC_YEAR`, file names and `EXPECTED` in the same
commit. Never relax an assertion to make a build pass.
