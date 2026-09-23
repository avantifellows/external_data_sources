# aiimsnursing — AIIMS B.Sc. (Hons.) Nursing seat allocation

AIIMS New Delhi allots B.Sc. (Hons.) Nursing seats at 18 AIIMS on the
AIIMS B.Sc. Nursing entrance overall rank. This pipeline parses the 2025
Round 1 and Round 2 result notifications (No. 117/2025, 132/2025) into
two tables (see `schemas/aiimsnursing_fact_cutoffs.yaml`):

- `aiimsnursing_fact_allotments`: every eligible candidate per round, in
  rank order: category, PwBD, outcome, institute and seat allotted.
  Roll numbers are dropped at parse time.
- `aiimsnursing_fact_cutoffs`: opening / closing rank per round,
  institute and seat category.

```
python3 scripts/build_clean.py      # fetches raw PDFs from GCS if missing, parses
python3 scripts/upload_to_gcs.py    # raw PDFs + clean parquet to gs://avantifellows-external-data/aiimsnursing/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

Needs `pdftotext` (poppler). New session: drop the round PDFs in `raw/`
under the names in `scripts/sources.py` (bump `YEAR`), run all three.

## What to know before querying

- Ranks are overall ranks for every category, so they compare across
  categories. A reserved-category candidate can be allotted a UR seat.
- Loosest closing per seat = MAX(closing_rank) over rounds.
- `outcome`: 'NR/NP' = did not register or fill choices (Round 1 only);
  'FCNA' = filled choices not available at that rank.
- Mangalagiri is printed "MANGLAGIRI"; kept verbatim.

Checks built in: every candidate line parses; ranks strictly increase;
per round, the parsed last rank of every seat category equals the table
AIIMS prints at the end of the PDF. The 2025 build also reproduced the
team's hand-made closing-rank sheet (98 rows) exactly.
