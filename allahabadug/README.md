# allahabadug — University of Allahabad UG admission (CUET) cut-offs

The University of Allahabad (Prayagraj) admits to its UG programmes on
CUET-UG, publishing one cut-off notice per programme per round: B.A. (9
rounds), B.Com (15), B.Sc. Biology (12), B.Sc. Maths (15), BBA-MBA (13),
Disaster Management & Environmental Studies (7), B.Voc. Software
Development (11), B.P.A. Music (6) and Family & Community Sciences. This
pipeline turns 90 of those notices into `external_data_sources.allahabadug_fact_cutoffs`
(see `schemas/allahabadug_fact_cutoffs.yaml`).

```
python3 scripts/build_clean.py      # fetches raw + transcription from GCS if missing, parses, checks
python3 scripts/upload_to_gcs.py    # raw notices + transcription + clean parquet to gs://avantifellows-external-data/allahabadug/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

## Sources

`scripts/sources.py` lists all 108 files downloaded on 2026-10-05 from the
2025 UG admission pages (Arts /p/692, Science /p/693, Commerce /p/694),
each with its URL and role: 70 text notices parsed, 20 transcribed by eye,
17 excluded (BFA: practical test; special-quota and named lists; a
verification schedule), plus the eligibility guideline.

## What to know before querying

- **Merit is out of 750**: best of Hindi / English + one domain subject
  (each programme has its own list) + General Test. A paper not taken
  counts 0 (not ineligible). The per-programme papers are in
  `../cuet` (`cuet_dim_merit_rules`, rules `ALD_*`).
- **Ranges**: "362 - 371" is the band admitted in that round; `cutoff` is
  the low end. "All" / "Last Candidate" -> `all_admitted`, `cutoff` NULL.
- **Loosest cut-off** for a programme and category = MIN(cutoff) over rounds
  within one `year`.
- **Year per row**: the 2026-27 cycle's first notices sit on the same
  pages. `DisasterEnvironmentalStudies--Notice_3rd.pdf` is a 2026 notice
  (its OBC/SC/ST cut-offs sit above 2025's 2nd round, impossible within
  one cycle); it is kept with year 2026.
- **Transcribed notices** (`extraction = 'manual'`): scanned pages (B.Voc.,
  Disaster Management round 1, Family & Community Sciences) and B.P.A.,
  whose notices print a different round for each category. Each row in
  `extracted/manual_transcriptions.csv` is one printed cell, read from the
  page image.
- **Named lists** (13 files, `has_names`) stay in the private bucket and
  are never published. Family & Community Sciences publishes named
  shortlists: only the one printed cut-off line (round 3, UR 63.09) is
  taken, nothing else.

## Quality gates

`build_clean.py` fails when a text notice yields no rows, programme or year;
on duplicate rows; on a cut-off outside 0-750. It prints any category whose
cut-off rises from one round to the next within a year. That check is what
showed the Disaster Management notice above belongs to 2026. Five buckets
were spot-checked against the PDFs (B.Sc. Bio R1 UR 519.28, B.A. R6 EWS
362-371, BBA-MBA R6 UR 464.20-472, B.Com R6 SC 276-278, Disaster R1 UR 450).
