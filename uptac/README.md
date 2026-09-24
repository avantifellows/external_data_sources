# uptac — UPTAC (Uttar Pradesh) counselling OR-CR

UPTAC, run by AKTU, fills B.Tech seats at AKTU-affiliated and U.P.
government engineering colleges on the JEE Main rank, and B.Arch, BBA,
BCA, B.Des, MBA, MCA and lateral-entry seats on their own exams. This
pipeline turns UPTAC's public OR-CR "cut-off matrix"
(uptac.samarth.edu.in) — every round, programme and category of the 2026
counselling — into `external_data_sources.uptac_fact_cutoffs` (see
`schemas/uptac_fact_cutoffs.yaml`).

```
python3 scripts/fetch_pages.py      # 541 pages of 50 rows, 1 request/second -> raw/pages/
python3 scripts/build_clean.py      # parse + label -> clean/uptac_fact_cutoffs.parquet (fetches raw zip from GCS if missing)
python3 scripts/upload_to_gcs.py    # zipped pages + clean parquet -> gs://avantifellows-external-data/uptac/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

## What to know before querying

- **`rank_basis` first.** 'JEE Main rank' covers B.Tech rounds 1-4 and the
  special round's JEE seats. 'UPTAC round merit rank' rows (remark "UPTAC
  ROUND III/VI RANK") were filled on Class 12 marks, CUET, NATA or JEE
  Paper 2 on UPTAC's own list — a different scale, with the score in
  `min_score` / `max_score`.
- **Domicile.** Regular rounds are for U.P. candidates (passed 12th in U.P.
  or parents domiciled in U.P.); the special round opens open-category
  seats to everyone. Only GEN / TFW rows appear on JEE seats in the
  special round.
- **Categories** (UPTAC Information Brochure 2025-26 §5): parent OP / BC /
  SC / ST / EWS (all "from U.P."), sub-category NO / GL (female from U.P.,
  up to 20%) / FF (freedom fighters' dependants, 2%) / AF (defence
  personnel wards, 5%) / PH (divyangjan, 5%); TFW = tuition fee waiver.
  From round 2, unfilled sub-category seats convert to their parent.
- **"-" cells are kept** as rows with NULL ranks (`allotted = FALSE`):
  the seat exists, nobody was allotted it that round. 79% of rows.
- Seat pools in branch names (Shift I, FW, Self Finance, Collaboration /
  twinning) are split into columns; institute names get a readable
  `institute` (the site prints most in capitals) next to `institute_raw`.

Checks built in: 13 cells a row; Sr.No 1..N with no gap (a table that
changed mid-scrape fails); unique grain; opening ≤ closing; every category
code known.
