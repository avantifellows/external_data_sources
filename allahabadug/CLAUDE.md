# CLAUDE.md — allahabadug

Source-level orientation for the University of Allahabad UG (CUET)
cut-offs pipeline. Read the top-level `../CLAUDE.md` first.

## Layout

```
allahabadug/
├── scripts/
│   ├── sources.py        # all 108 files: URL, role (text / manual / rules / excluded), has_names
│   ├── parse_notices.py  # one text notice -> programme, year, round, date, category rows
│   ├── build_clean.py    # text + manual transcription -> clean/allahabadug_fact_cutoffs.parquet
│   ├── upload_to_gcs.py
│   └── load_bq.py
├── schemas/allahabadug_fact_cutoffs.yaml
├── raw/        (gitignored; GCS canonical)
├── extracted/  (gitignored; manual_transcriptions.csv, GCS canonical)
└── clean/      (gitignored)
```

## Gotchas (handled in parse_notices.py / build_clean.py)

- Programme comes from the notice heading, never the file name
  ("BA_First Merit (1).pdf" is B.P.A. Music).
- Category labels wrap across lines, with the marks on the first line;
  fee dates/times sit on the same lines and are stripped first.
- A new notice that parses to nothing fails the build: fix the parser or
  set its role to 'manual' and transcribe it.
- Never transcribe names from the named lists; a printed cut-off line only.
