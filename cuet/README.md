# cuet — CUET (UG) merit rules

Universities that admit on CUET (UG) publish ONE cutoff number per course,
but it is a sum: each course adds up its own CUET papers (each paper's
normalized score is out of 250). DU B.Sc. (Hons.) Physics counts Physics +
Chemistry + Maths (out of 750); DU B.A. (Hons.) Economics a language + Maths
+ two subjects (out of 1000); BHU B.A. English or Hindi + GAT (out of 500).
This source records those rules, read from each university's 2025 bulletin,
and maps every course string in the cutoff tables to its rule.

```
python3 scripts/build_clean.py      # fetches raw from GCS if missing; course strings from the cutoff facts on GCS
python3 scripts/upload_to_gcs.py    # raw bulletins + clean parquet to gs://avantifellows-external-data/cuet/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

## Tables

- **`cuet_dim_merit_rules`** (58 rows: DU 25, CUSB 13, BHU 8, Allahabad 7, Jamia 4, JNU 1) — per rule: the papers
  as text and as JSON combinations, `max_score`, `prorated`,
  `needs_language`, and where the bulletin prints it (`source_ref`).
- **`cuet_dim_program_rules`** (736 rows: DU 334, BHU 351, CUSB 23, JNU 10,
  Allahabad 9, Jamia 9) — every course string of the six cutoff facts'
  programme column → `rule_id`.

## Sources

| File | University | Where it's published |
|---|---|---|
| `du_ug_bulletin_2025.pdf` | DU | Bulletin of Information, UG 2025-26: a "Program Specific Eligibility" box per course — https://www.du.ac.in/uploads/07032025_UG-BOI_compressed.pdf |
| `allahabad_ug_guidelines_2025.pdf` | ALD | University of Allahabad, guidelines and eligibility criteria for UG programmes (merit papers per programme) — https://allduniv.ac.in/upload/file_collection/GuidelinesEligibilityRevised.pdf |
| `cusb_ug_eligibility_2025.pdf` | CUSB | Central University of South Bihar, Annexure I: CUET papers per UG programme — https://www.cusb.ac.in/images/2025/admission_25/ug/rev_intake.pdf |
| `jnu_admission_policy_2025.pdf` | JNU | Admission Policy 2025-26 (3.2: UG merit = CUET marks converted to 100); papers from the UG e-Prospectus (English + GAT) — https://www.jnu.ac.in/sites/default/files/admission/AdmissionPolicy2025-26.pdf |
| `jmi_prospectus_2025.pdf` | JMI | Jamia University Prospectus 2025-26, p. 139: one CUET paper per programme — https://admission.jmi.ac.in/application/assets/pdfFile/prospectus/UniversityProspectus/University_Prospectus_2025-2026.pdf |
| `bhu_ug_cuet_eligibility_2025.pdf` | BHU | UG programmes and CUET subjects 2025 (19 numbered entries) — https://www.bhu.ac.in/Images/files/BHU_UG_CUET_Program_Course_Eligibility_Criteria_2025.pdf |

The rules themselves are code (`scripts/rules.py`), transcribed by hand from
those documents with the page / entry number on every rule.

## What to know before querying

- **A rule is a set of alternatives**; a course takes the student's best
  combination. Slots: `L` any language, `B` any domain subject, `G` GAT, or a
  list of paper ids.
- **Proration is an assumption.** Where one course mixes 3- and 4-paper
  combinations (DU B.A. Program, B.Com, Journalism), DU says only that
  "appropriate proration will be done". `prorated` marks those rules; the
  predictor scales the smaller combination up (x 4/3, x 2).
- **The build fails** if a cutoff refresh brings a course string with no rule,
  if a rule goes unused, or if any cutoff is above its rule's `max_score`
  (the check that caught nothing in 2025 but would catch a wrong rule).
- **A rule's printed scale can be a rescaling.** `max_score` is the scale
  the university prints (JNU: 100); `papers_max` is the raw paper total
  (JNU: 500). Everywhere else they are equal.
- **A missing paper can count 0.** `missing_counts_zero` (Allahabad): a
  student who didn't take a counted paper is scored 0 for it, not ruled out.
  DU and BHU rules need every paper of a combination.
- DU B.A. (Hons.) Bengali / Punjabi rank their generic combinations (no
  Bengali / Punjabi paper) last, only for seats left over; the table lists
  them as plain alternatives.
