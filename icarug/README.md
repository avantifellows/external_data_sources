# icarug — ICAR-UG (CUET) counselling cutoffs

ICAR admits to B.Sc. (Hons.) Agriculture, Horticulture, Forestry,
B.Tech. Agricultural Engineering / Food / Dairy, B.F.Sc. and others at 72
agricultural universities through the ICAR-UG counselling on the CUET (UG)
score. This pipeline turns ICAR's 2025 cut-off list (five rounds, First to
Mop-up) into `external_data_sources.icarug_fact_cutoffs` (see
`schemas/icarug_fact_cutoffs.yaml`).

```
python3 scripts/build_clean.py      # fetches raw from GCS if missing, builds + checks against the PDF
python3 scripts/upload_to_gcs.py    # raw PDF + CSV + clean parquet to gs://avantifellows-external-data/icarug/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

Raw: ICAR's PDF (watermarked, exported from a spreadsheet) and the team's
CSV extraction of it. The build uses the CSV and fails unless every number
matches the PDF in order; the PDF prints 425 rows twice where a row crosses
a page break, and only those are skipped. Needs `pdftotext` (poppler).

## What to know before querying

- **Compare on marks, not ranks.** `marks_start` (lowest CUET marks, three
  subjects, of 750) is the cutoff. The same ICAR rank appears with
  different marks, so the ranks are not one list: ICAR ranks subject
  streams separately and the file doesn't say which stream a row is.
- **Home state is who got the seat**, not a quota: allotment is on the
  all-India ICAR-UG merit. A seat's cutoff is MIN(marks_start) over home
  states (and rounds, for the loosest).
- **UPS** is ICAR's under-privileged-states category.
- Labels are cleaned (course "Nutural" -> "Natural"; university display
  names with city, spellings fixed); the printed text stays in `*_raw`.
