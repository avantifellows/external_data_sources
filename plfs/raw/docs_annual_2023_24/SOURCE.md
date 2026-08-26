# PLFS 2023-24 technical documents

Pulled 2026-08-26 from MoSPI's microdata portal, catalog 213
(<https://microdata.gov.in/NADA/index.php/catalog/213/related-materials>).

**Why this folder did not exist until now.** The 2023-24 acquisition took only the Nesstar bundle and
the portal's download guide — see `gs://avantifellows-external-data/plfs/raw/213 - PLFS_July23-June24/`,
which holds `DDI-IND-CSO-PLFS-2023-24.Nesstar`, `Guide to dowdload microdata.pdf` and an installer, and
no technical documents. Every other release has a `docs_*` folder; this one had none, so the release's
own weight rule could not be checked against its own README. It has now been checked and matches
`_combined()` in `scripts/weights.py`: `MULT/100` if `NSS=NSC` else `MULT/200`, then divided by
`NO_QTR` ("count of contributing sector x state x stratum x substratum in 4 quarters").

**Complete set, all eight files, is on GCS:**
`gs://avantifellows-external-data/plfs/raw/docs_annual_2023_24/`

**Two files are deliberately NOT in git:** `2_1_Instruction_manual_PLFS_Vol_I.pdf` (1,848,924 bytes) and
`2_2_Instruction_Manual_PLFS_Vol-II.pdf` (997,906 bytes). Both are **byte-identical** (sha1 `096fba6c40e6…`
and `89117060f8a4…`) to `docs_calendar_2024/InstructionManual_VolI_2024.pdf` and `…VolII_2024.pdf`
already tracked here — MoSPI reused the same manuals — so committing them again would add 2.8 MB of
duplicate. They are on GCS under this release's path for provenance.

| file | bytes | why it matters |
|---|---|---|
| `1_README.docx` | 27,917 | the weight rule for this release; the file that was missing |
| `3_1_Estimation_Procedure_PLFS.pdf` | 542,687 | release-specific sample design. Contains ZERO mentions of calibration, post-stratification, benchmarking, projection or control totals — checked, because that absence is what the level of the weighted total turns on |
| `Data_LayoutPLFS_2023-24.xlsx` | 56,677 | column offsets, for verifying the parser |
| `District_codes_PLFS_Panel_4_202324_2024.xlsx` | 29,510 | district codes for panel 4 |
| `NMDS_2dot0_PLFS_final_upd.docx` | 33,277 | national metadata structure |
| `Note_on_Updated_Instruction_for_PLFS_2023-24.pdf` | 545,720 | no weight changes, but records the urban frame code moving to **2017-22 UFS-18** (from UFS-15 and UFS-17) — the one documented mechanism found for the weighted total drifting across releases |
