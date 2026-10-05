# jnuug — JNU UG admission (CUET) cut-offs

JNU admits to ten B.A. (Hons.) foreign-language programmes on CUET-UG
(English 101 + General Aptitude Test 501). This pipeline turns its four 2025-26
merit lists into `external_data_sources.jnuug_fact_cutoffs`.

```
python3 scripts/build_clean.py      # fetches raw from GCS if missing; pdfplumber tables
python3 scripts/upload_to_gcs.py
python3 scripts/load_bq.py
```

## What to know before querying

- **Marks are out of 100**: English + GAT CUET marks (of 500) converted to 100
  (Admission Policy 2025-26, 3.2). A student's 400/500 is 80.
- **seat_code**: Code-I seats (80%) are for Class 12 passed in the year of
  admission or the year before; Code-II (20%) for everyone else. The two
  have separate cut-offs. Most school leavers are Code-I.
- **Loosest cut-off** = MIN(cutoff_marks) over lists, within a seat code.
- A blank cell in a list (no row) = no offer in that category that round.
- The defence / J&K / Covid-orphan supernumerary list is not included.
