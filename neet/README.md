# neet

Everything NEET-UG in one place: the parsers, the matrix pipeline, and the loaders behind
the two BigQuery tables.

| table | rows | grain | answers |
|---|---|---|---|
| `neet_dim_marks_matrix_2026` | 370 | state × category | *what is the bar?* |
| `neet_fact_cutoffs` | 13,700 | college × category × round | *which colleges could I get?* |

## Layout — two parser families, one source

```
scrape/           OUR parsers — 9 scripts over official counselling PDFs
                  → per-college closing ranks → NEETUG.json → neet_fact_cutoffs
state_medical/    THEIR parsers (June handoff) — ~30 state_XX.py over state documents
mcc/              THEIR AIQ parsers — the national-quota side of the same handoff
matrix/           the 2026 minimum-marks matrix: 28 state builders + 7 parsers + docs
scripts/          build parquet → upload GCS → load BQ (the canonical loaders)
schemas/          column-level YAML for both tables
```

Two families deliberately coexist: they parse **different documents for the same states**,
and the matrix chose per state whichever survived audit — the choice is recorded per state
in `matrix/docs/NEET_2026_MATRIX_DECISIONS.md`. The cross-check caught real bugs (Punjab,
Maharashtra). The families' own standalone tables (`state_medical_fact_closing_ranks`,
`mcc_fact_closing_ranks`) are **not loaded** — they would duplicate `neet_fact_cutoffs`.

## Data — GCS only, never git

```
gs://avantifellows-external-data/neet/
  raw/         official PDFs, the ZMCH page-image register, NMC/DCI rosters, anchors
  extracted/   every parser family's output CSVs
  clean/       the two parquets that load to BQ
```

`scripts/sources.py` is the single source of truth for paths and targets. The `.gitignore`
enforces the data boundary across every subfolder.

## Method and provenance

`matrix/docs/NEET_2026_HOW_WE_BUILT_IT.md` — the methodology, readable top to bottom.
`matrix/docs/NEET_2026_MATRIX_DECISIONS.md` — the full per-state decision log.
The staff-facing report lives in data-assistant: `analysis/neet-cutoffs/`.
