# cusbug — Central University of South Bihar UG admission (CUET) cut-offs

CUSB (Gaya, Bihar) admits to 23 UG programmes on CUET-UG: 5-year integrated
UG-PG programmes, B.A./B.Sc. B.Ed., BA/BBA LLB, B.Sc. Agriculture and
D.Pharm. This pipeline turns its six 2025-26 cut-off announcements (and a
round-1 corrigendum) into `external_data_sources.cusbug_fact_cutoffs`.

```
python3 scripts/build_clean.py      # fetches raw + transcription from GCS if missing; parses; checks
python3 scripts/upload_to_gcs.py
python3 scripts/load_bq.py
```

## What to know before querying

- **The score is the sum of the programme's CUET papers** (Annexure I,
  `raw/ug_rev_intake.pdf`): GAT + one subject (of 500) or a single paper (of
  250). CUSB issued a clarification (`ug_clearification_1.pdf`, 28 Jul 2025)
  because students were adding all their papers: only the specified ones
  count. Rules per programme: `../cuet` (`CUSB_*`).
- **Rounds 2-6 print only the cells that re-opened**; a missing cell means no
  seats that round. Loosest cut-off = MIN(cutoff) over rounds.
- **"All"** = all registered candidates (`all_admitted`).
- Rounds 3 and 6 and the corrigendum are scans, transcribed by eye
  (`extraction = 'manual'`). Round 6's heading misprints "FIRST (6th)"; its
  text says sixth round.
- The page's "provisionally admitted" lists name students and are not
  downloaded.

## Quality gates

Round 1 must parse all 23 programmes (152 printed values + 1 corrigendum
cell, reconciled against the PDF); no duplicates; scores 0-500.
