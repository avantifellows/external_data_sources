# jamiaug — Jamia Millia Islamia UG admission (CUET) cut-offs

JMI fills nine UG programmes on CUET-UG (B.A. Hons. Turkish, Sanskrit,
French, Spanish, Hindi, Urdu, Korean; B.Sc. Hons. Applied Mathematics;
B.Sc. Multidisciplinary). Its other UG programmes use JMI's own entrance test
and are not here. This pipeline reads the category-wise cut-off table at the
end of each 2025-26 selection list into `external_data_sources.jamiaug_fact_cutoffs`.

```
python3 scripts/build_clean.py      # fetches raw from GCS if missing; pdfplumber
python3 scripts/upload_to_gcs.py
python3 scripts/load_bq.py
```

## What to know before querying

- **One paper per programme, out of 250** (Prospectus 2025-26 p. 139):
  General Test for six programmes, Hindi / Urdu / Mathematics for the others.
- **JMI's own categories**: GENERAL is open to all; MUSLIM, MUSLIM OBC/ST,
  MUSLIM WOMEN, JAMIA (JMI's internal students), PWD, Kashmiri Migrants and
  J&K candidates are JMI reservations. They do not map to the national
  UR/OBC/SC/ST/EWS scheme: never compare them with other universities'
  categories.
- **Loosest cut-off** = MIN(cutoff) over lists.
- The lists' candidate pages carry roll / registration / application
  numbers: kept private, not published.
