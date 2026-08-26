# Official MoSPI documentation for CMS-E

Everything here is published by MoSPI alongside the unit-level data at
[NADA catalog 255](https://microdata.gov.in/NADA/index.php/catalog/255).
Retrieved 2026-08-26.

| File | What it gives you |
|---|---|
| `Data_Layout_CMSE_2025.xlsx` | Fixed-width layout for all three files, plus the **state code → name** sheet (the only published geography lookup) |
| `CODEs for Blocks of Sch - CMS-Education.xlsx` | Every value label, by schedule block and item — the source for `codemaps/` |
| `README_CMSE_2025.docx` | Record lengths, join keys, and the `weight = mult / 100` rule |
| `Note_for_data_user - CMS-Education.docx` | MoSPI's scope caveats, including the instruction not to build population estimates from the auxiliary variables |
| `Survey methodology and estimation procedure - CMS-Education.pdf` | Sample design and estimation formulae |
| `ddi_255.xml` | DDI 2.5 codebook — 97 variables, 348 categories |

**Not in git:** `NSO Volume I & II_80 - CMSE.pdf` (2.15 MB) — the 113-page field
manual and the survey schedule itself. Over the repo's in-git size line, so it
lives at `gs://avantifellows-external-data/cmse/raw/docs/`. It is the source for
most of the interpretation notes in `../schemas/README.md`: the instruction to
value government in-kind support at zero (Note 12, p. C-21), the private-coaching
definition naming ALLEN/FIITJEE/Aakash (p. C-24), and the away-from-home
non-reporting codes (Note 10, p. C-16).

Fetch it with:

```bash
gsutil cp "gs://avantifellows-external-data/cmse/raw/docs/NSO Volume I & II_80 - CMSE.pdf" docs/
```
