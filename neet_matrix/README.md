# neet_matrix

NEET → BigQuery. **Two tables**: the minimum-marks matrix (the bar) and the per-college
closing ranks underneath it (the evidence).

| table | rows | grain | answers |
|---|---|---|---|
| `neet_dim_marks_matrix_2026` | 370 | state × category | *what is the bar?* |
| `neet_fact_cutoffs` | 13,700 | college × category × round | *which colleges could I get?* |

## The matrix

For each state/UT and category, the minimum NEET marks that realistically win a
**government** MBBS (B1a) / BDS (B1b) seat, plus B2b (the national qualifying floor).
370 rows = 37 tracks × 10 categories — all 36 states/UTs plus "All India" (the 15%
All-India-Quota track).

It answers **"what is the bar?"** — one floor per (state, category) — as against the
per-college closing ranks a college predictor needs.

## Pipeline

```
~30 official documents (state cutoff PDFs, allotment lists, merit lists,
and one admitted-student register published as 10 page images)
       │  parsers + builders live in futures-v2/neet/matrix_2026/
       ▼
neet_2026_matrix_all.csv
       │  scripts/build_parquet.py     (splits data_status, ints become nullable)
       ▼
clean/neet_marks_matrix_2026.parquet
       │  scripts/upload_to_gcs.py     (raw + extracted + clean)
       ▼
gs://avantifellows-external-data/neet_matrix/{raw,extracted,clean}/
       │  scripts/load_bq.py
       ▼
avantifellows.external_data_sources.neet_dim_marks_matrix_2026   (asia-south1)
```

`scripts/sources.py` is the single source of truth for paths, GCS URIs and the BQ targets.

## The fact table

```
public/data/NEETUG/NEETUG.json      (19 counselling extracts, 13,700 rows, all NEET AIR)
  +  raw/nmc-dci-roster-2025-26/    (NMC 819 MBBS + DCI 330 BDS colleges, official mgmt)
       │  scripts/build_fact_parquet.py
       ▼
clean/neet_fact_cutoffs.parquet  →  external_data_sources.neet_fact_cutoffs
```

Built from the same dataset that powers the college predictor, so the app and BigQuery
cannot drift apart.

**Seat type is not college type.** A government-quota SEAT can sit inside a PRIVATE
college — 283 such rows across 15 private colleges in Karnataka, 55 across 13 in Punjab.
Measured across the whole dataset, `seat_type='Government'` sits in a private college on
**62%** of its rows. A real Karnataka medical student reported this as a predictor bug.
Use `college_type` for "is this a government college", `seat_type` for "which pool".

`college_type` is **64% filled and never guessed** — NULL means unknown, not "not
government". It comes from the NMC/DCI rosters via three rungs (exact name, govt-by-
definition, token+state), recorded per row in `college_type_method`. Measured 96% against
rows whose source already carried the field; of the 185 disagreements, 153 are cases where
the *source* was wrong (it derived College Type from the seat type) and only 3 colleges
genuinely disagree — this classifier is right on all three. True accuracy ≈ 99.6%.

A wrong "Govt" would make a college look ~250 marks easier than it is with nothing about
the row looking broken, so fuzzy matching — measured at 87.5% with *every* error in that
direction — is deliberately not used.

`category` collapses 321 raw codes to 5, with everything else preserved in `sub_pool`
(pwd, rural, kannada-medium, home-univ, earmark...). **Filter `sub_pool=''` for base
floors.** Karnataka folds caste × language × region into one token (`2AKH` = 2A ×
Kannada-medium × Hyderabad-Karnataka); its grammar was derived from the data and verified
to decompose 50 of its 76 codes.

The matrix is **not** currently generated from this table — reproducing it in SQL needs a
govt flag at higher coverage than 64%, since unclassified private colleges leak into a
naive floor query and loosen it. Matrix for the bar; fact table to see behind it.

## Three GCS tiers

- **`raw/`** — the source documents themselves, including
  `raw/mizoram-zmch-2025-admitted/p1..p10.png` (ZMCH publishes its NMC admitted-student
  return as scans, not a table). Traceability only; never loaded to BQ. This tier is what
  makes the pipeline reproducible by someone other than its author.
- **`extracted/`** — parser output: per-college allotments, closings, and the 5,817-pair
  Odisha state-rank↔AIR bridge. Kept so a reviewer can diff a parse against its source PDF
  without re-running OCR.
- **`clean/`** — the deliverable parquet.

Raw, extracted and clean are **gitignored** — data lives in GCS, only code in git.

## Reading the table

`state` is a **track label, not a place**: "All India" is the 15% AIQ door, everything else
is that state's 85% domicile door. A student competes in both, and the two are not
comparable within a category. `source_round` matters for the same reason — round depth
differs by state, so a Round-1 state looks harsher than a mop-up state at identical reality.

`data_status` distinguishes a real cutoff from an absent one. `N_A_NO_QUOTA` means the state
does not run that category at all (Punjab/Haryana have no ST quota; Tamil Nadu has no EWS) —
those rows previously showed the qualifying floor, which read as a genuine cutoff.

Full method and per-state provenance:
`futures-v2/neet/matrix_2026/docs/NEET_2026_HOW_WE_BUILT_IT.md`
