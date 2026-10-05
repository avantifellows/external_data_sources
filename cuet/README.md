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

- **`cuet_dim_merit_rules`** (33 rows: DU 25, BHU 8) — per rule: the papers
  as text and as JSON combinations, `max_score`, `prorated`,
  `needs_language`, and where the bulletin prints it (`source_ref`).
- **`cuet_dim_program_rules`** (685 rows: DU 334, BHU 351) — every course
  string of `ducuet_fact_cutoffs.program_name` / `bhuug_fact_cutoffs.program`
  → `rule_id`.

## Sources

| File | University | Where it's published |
|---|---|---|
| `du_ug_bulletin_2025.pdf` | DU | Bulletin of Information, UG 2025-26: a "Program Specific Eligibility" box per course — https://www.du.ac.in/uploads/07032025_UG-BOI_compressed.pdf |
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
- DU B.A. (Hons.) Bengali / Punjabi rank their generic combinations (no
  Bengali / Punjabi paper) last, only for seats left over; the table lists
  them as plain alternatives.
