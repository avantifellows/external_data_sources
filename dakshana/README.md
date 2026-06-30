# Dakshana

Two Dakshana datasets, one folder, harmonised into BigQuery under `avantifellows.external_data_sources`:

| Table | What | Grain | ~Rows |
|---|---|---|---:|
| `dakshana_fact_ncst_results` | NCST selection test (2022–2025), Dakshana-curated | (test_year, roll_no) | ~49k |
| `dakshana_fact_reported_results` | Dakshana self-reported JEE-Main + NEET results | (test_year, exam, student) | ~371 (2025) |

> ⏸ `dakshana_fact_reported_results` is built & staged to GCS; **BQ load pending approval**.
> `dakshana_fact_ncst_results` is the established NCST pipeline (see `CLAUDE.md`). 2026+ NCST lives in
> [`../nvs/`](../nvs/), not here.

## Why this source exists

- **NCST results** — the Dakshana/ENF/Avanti-run selection test that fed the two-year IIT/NEET coaching
  programmes (2022–2025). Scores, coaching preferences, demographics per student per year.
- **Reported results** — Dakshana students are routinely **mis-attributed** in the warehouse: the
  `student_program='Dakshana CoE'` tag is patchy year-to-year, so a Dakshana student (e.g. at JNV
  Bengaluru Urban) often shows up as Nodal/NVS. Dakshana's own sheet names every Dakshana student + their
  CoE, so it is the **authoritative Dakshana attribution** — and it pins **which JNVs were Dakshana in a
  given year** (the footprint moves: Bundi/Kottayam/Lucknow were Dakshana in 2025, handed to Avanti from
  2026).

## Pipeline

```
raw/ (Dakshana sheets, gitignored)
   --clean_ncst.py-------------->  clean/ncst_clean.csv                       (NCST)
   --build_reported_results.py-->  clean/dakshana_fact_reported_results.parquet  (reported)
        │
        --upload_to_gcs.py [--raw]-->  gs://avantifellows-external-data/dakshana/{raw,clean}/
        --load_bq.py-------------->    avantifellows.external_data_sources.dakshana_fact_*
```

`sources.py` is the single config: both output tables live in `TABLES`, all raw artifacts in `RAW_FILES`.
The two tables have different shapes and `upload_to_gcs.py` handles both — NCST clean is a CSV (dtyped on
upload) staged from per-year Excel, reported clean is parquet staged from CSVs kept as-is.

- `scripts/clean_ncst.py` — codemap-driven NCST transform (see `CLAUDE.md` for the codemap architecture).
- `scripts/build_reported_results.py` — harmonise the JEE-Main + NEET sheets into one long table with an
  `exam` + `score_type` discriminator (JEE score is a percentile, NEET is raw marks — never mix).
- `scripts/upload_to_gcs.py` — `--raw` stages originals, default stages clean; `--table` to pick one,
  `--dry-run` to preview.
- `scripts/load_bq.py` — loads clean parquet → BQ (WRITE_TRUNCATE); `--table` / `--dry-run`.

## Linking to Avanti students

The reported sheets carry **name + CoE only** — no `student_id` / `application_no`. Attach to an Avanti
student by name (+ DoB) via the identity crosswalk, not by id.

**No production GCS/BQ writes without an explicit go** — clean artifacts are gitignored; load is
post-approval.
