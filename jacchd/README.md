# jacchd — JAC Chandigarh cutoffs

The Joint Admission Committee, Chandigarh admits first-year B.E. / B.Arch
on the JEE Main rank at five institutes: CCET and CCA (Chandigarh
Administration), and Panjab University's UIET, Dr. S.S. Bhatnagar UICET
and UIET Hoshiarpur. This pipeline turns the 2026 round-wise opening and
closing ranks (Rounds 1-3, Special, SPOT) into
`external_data_sources.jacchd_fact_cutoffs` (see
`schemas/jacchd_fact_cutoffs.yaml`).

```
python3 scripts/build_clean.py      # fetches the raw sheet from GCS if missing, normalises
python3 scripts/upload_to_gcs.py    # raw + clean parquet to gs://avantifellows-external-data/jacchd/
python3 scripts/load_bq.py          # WRITE_TRUNCATE into BigQuery
```

Raw: the team's transcription of the JAC portal
(jacchd.admissions.nic.in) into a Google Sheet, exported as CSV. New
cycle: export the sheet, name it per `scripts/sources.py` (bump `YEAR`),
put it in `raw/`, run all three.

## What to know before querying

- **Three rank scales.** `rank_basis` is 'JEE Main Paper 1' (B.E.),
  'JEE Main Paper 2' (CCA's B.Arch), or 'category merit list': the
  Defence and Sports lists print positions in their own list (1-318,
  some decimal), not JEE ranks. Filter it before comparing.
- **Quotas differ by institute.** The Panjab University institutes admit
  on 'All India'; CCET and CCA split 'Home State' (Chandigarh) and
  'Other State'.
- **TFW is a seat pool**, split off the programme name into `tfw`. Only
  the EWS fee-waiver category sits on it.
- Categories are verbatim in `category_raw` (they name the institutes
  they apply to) and canonical in `category`.

Checks built in: unique grain, opening ≤ closing, known rounds /
institutes / quotas, every category mapped, TFW ⇔ EWS-TFW, merit-list
positions below 1000.
