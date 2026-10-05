# CLAUDE.md — cuet

Source-level orientation for the CUET (UG) merit-rules pipeline. Read the
top-level `../CLAUDE.md` for cross-cutting repo conventions first.

## What this source is

Which CUET papers each university course adds up into its merit score, from
the DU and BHU 2025 bulletins, mapped onto the course strings of the
`ducuet` and `bhuug` cutoff facts. Raw = the bulletins (gitignored; GCS
canonical). The rules are code in `scripts/rules.py`.

## Layout

```
cuet/
├── scripts/
│   ├── sources.py        # RAW_FILES, CUTOFF_SOURCES (whose course strings get rules), TABLES
│   ├── rules.py          # the rules (with bulletin page) + course-string -> rule patterns
│   ├── build_clean.py    # -> clean/cuet_dim_merit_rules.parquet, cuet_dim_program_rules.parquet
│   ├── upload_to_gcs.py  # raw + clean -> gs://…/cuet/{raw,clean}/
│   └── load_bq.py        # GCS clean/ -> BigQuery (WRITE_TRUNCATE)
├── schemas/
├── raw/     (gitignored)
└── clean/   (gitignored)
```

## Adding a university

1. Archive its bulletin in `raw/` and `RAW_FILES`.
2. Add its cutoff fact to `CUTOFF_SOURCES` (program + score columns).
3. Add its rules (`RULES`, with page refs) and a course -> rule function in
   `RULE_OF`. The build lists every course left without a rule.

## Gotchas

- The college-predictor reads these tables (scripts/build_cuet_2025.py);
  change a rule here, rebuild there.
- Proration for mixed-size combinations is our reading of DU's "appropriate
  proration", not a published formula.
