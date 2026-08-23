# collegefees

Tuition, total institute fees and hostel/mess charges per college × course ×
seat-demographic — hand-collected (Amogh's team, Aug 2026) from each college's
own published fee structure, cleaned into one BQ table.

```
raw/college_fee_hostel_details_2025-26.csv     the sheet, archived verbatim
       │ scripts/build_clean.py     ← Demo_ID re-parse, waived-total repair,
       ▼                              annualisation, conflict policy
clean/collegefees_costs.parquet
       │ scripts/upload_to_gcs.py → gs://avantifellows-external-data/collegefees/
       │ scripts/load_bq.py       → avantifellows.external_data_sources.collegefees_fact_costs
```

## Provenance and verification

The sheet is the raw layer; the true originals are the college fee pages in
`source_url` (100% of JoSAA rows carry one; mostly 2025-26 documents, a few
2026-27). Spot-verified at intake, Aug 2026: **4 of 4 fetchable source
documents matched to the rupee** (IIT Delhi, NITK Surathkal, SLIET, NERIST —
tuition, first-term total, hostel/mess). One systematic transcription bug —
waived rows carrying the full total — is repaired by build_clean.py (223
rows), with `total_was_corrected` marking each.

## Coverage (honest)

| Counselling | Rows | Colleges | Status |
|---|---:|---:|---|
| JoSAA | 8,266 | 112 | effectively complete (110 of the 128 live JoSAA institutes) |
| KCET | 2,512 | 25 of 148 | PARTIAL — use per-college, never for "Karnataka average" |
| MHT-CET | 0 | 0 | dropped — the sheet's MHT-CET block was an unfilled template |

## Traps the clean layer already handles

- The sheet's Gender/Caste columns are scrambled on ~31% of rows; `Demo_ID`
  is authoritative and `category`/`is_female`/`is_pwd` are re-parsed from it.
- Fees are quoted per semester or per year depending on the college —
  `annual_total_fee` / `annual_hostel_mess_fee` normalise (semester × 2).
- The quoted figure is the FIRST term (admission-time one-off charges
  included). Later semesters are usually cheaper. Entry-year cost, not
  steady-state.
- SC/ST/PwD tuition waivers are seat-bucket rows, not footnotes: the same
  course at IIT Delhi is ₹1,22,400/sem (OPEN) and ₹22,400/sem (SC/ST/PwD).
  Income-based remissions (e.g. NITK's <₹1L/₹1-5L slabs) are NOT modelled —
  category defaults only.
