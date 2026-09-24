# bhuug — BHU UG admission (CUET) cutoffs

Banaras Hindu University admits to its UG programmes (B.A., B.Sc., B.Com,
B.Voc, B.Tech, B.A. LL.B.) on CUET (UG), across its own faculties and its
admitted colleges in Varanasi. This pipeline turns the 2025 Round 1 and
Spot Round 2 allocation summaries into
`external_data_sources.bhuug_fact_cutoffs` (see
`schemas/bhuug_fact_cutoffs.yaml`).

```
python3 scripts/build_clean.py      # fetches raw from GCS if missing, builds + checks against the PDFs
python3 scripts/upload_to_gcs.py    # raw PDFs + CSV + clean parquet to gs://avantifellows-external-data/bhuug/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

Raw: BHU's two PDFs and the team's combined CSV. The build uses the CSV and
fails unless every row appears in its round's PDF, in order. Needs
`pdftotext` (poppler).

## What to know before querying

- **Scores are per-programme scales** (BHU's CUET-based merit score; B.A.
  up to ~374, B.Sc. ~637). Compare within one programme only.
- **BHU names its own units generically** ("Faculty of Arts"). `college`
  adds the university; `college_raw` / `unit` keep the printed text.
- **Fee types are separate seat pools**: paid / special fee course seats
  have their own (often lower) cutoffs. Filter `fee_type = 'regular'` for
  the ordinary seats.
- Only Round 1 and Spot Round 2 are in the source; the loosest cutoff here
  is MIN(min_score) over those two.
