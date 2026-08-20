# Onboarding a new data source — the checklist

The end-to-end path for any new exam, survey, or dataset: from "we found a source"
to "it powers the predictor, answers questions in ask-avantifellows, and is openly
downloadable." Every step earned its place by a real failure; the parenthetical
lessons name them.

## Phase 1 — Source and intake

- [ ] **Verify the source is official.** Counselling authority, ministry, commission —
      not a coaching site or aggregator. Record the URL. (Chandigarh: a third-party
      claimed UR 588; the official register said 514.)
- [ ] **Archive every raw document** — PDF, XLSX, portal pull, page images. If a partner
      pipeline hands you extracted CSVs, archive those AND note that the original
      document is missing. Any file the pipeline reads must be recorded.
      (Six NEET states have tables whose source PDFs we never saved. The gap is now
      permanent and publicly admitted.)
- [ ] **PII review at intake, not at publish.** Which columns are person-identifying
      (name, roll, raw OCR lines that embed names)? Student-level org data (JNV,
      Dakshana, NVS, board results by student) is NEVER publishable — decide the
      shareability class now: open / open-after-scrub / internal-only.

## Phase 2 — Pipeline in external_data_sources

- [ ] **One folder per source**, same name as the GCS prefix and the BQ table prefix
      (`<source>_<fact|dim>_<thing>`). House shape: `scripts/` (sources.py,
      build_clean.py, upload_to_gcs.py, load_bq.py), `schemas/`, README, .gitignore.
- [ ] **Data never enters git.** .gitignore covers raw/ extracted/ clean/ AND any
      subfolder data dirs (source/, extracted_data/, *_out/). Check `git diff --cached`
      for data files before every commit. (A copy once dragged 62 MB of PDFs into the
      index; the staging check is what caught it.)
- [ ] **sources.py is the provenance registry**: every input file mapped to its GCS
      path and origin. Provenance is code, not prose.
- [ ] **Parse quirks are documented where they're handled** — column bleed, OCR
      rotation, mid-word wraps, the em-dash-means-no-admission convention.
- [ ] **Categories: preserve the raw code, add the canonical rollup, split sub-pools.**
      `category_raw` verbatim (part of the grain), `category` canonical, `sub_pool`
      for what the code encoded beyond caste. Never collapse silently.
- [ ] **Seat type is not college type.** Govt-ness is a property of the seat OR the
      college — model both, classify by official codes/rosters, never by name-matching
      (measured: fuzzy name matching fails in the dangerous direction).
- [ ] **Quality gates before load:**
      - row count reconciles with the source (14,910 = the exact non-empty cell count)
      - zero exact-duplicate rows (KCET shipped 1,066 for a year)
      - spot-verify 3-5 buckets against numbers you independently trust
      - year/round stamped PER ROW where vintages mix (the GUJCET two-streams lesson)

## Phase 3 — GCS and BigQuery

- [ ] **Stage raw/ + extracted/ + clean/ to `gs://avantifellows-external-data/<source>/`.**
      Raw goes up even when it feels redundant — it is what makes the pipeline
      reproducible by someone other than its author.
- [ ] **Load clean parquet to BQ** (`avantifellows.external_data_sources.*`,
      asia-south1, WRITE_TRUNCATE). Verify row count and 2-3 live queries after load.
- [ ] **Reproducibility check:** could the table be rebuilt from GCS + committed code
      on a clean machine? If inputs resolve only from someone's laptop, staging isn't
      done. (NEET's reproduce.py is the template: fetch → build → diff → PASS.)

## Phase 4 — data-assistant (ask-avantifellows)

- [ ] **Schema YAML in docs/schemas/**, house format: `claude_md_summary`, a
      gotcha-led description (the ways a query goes confidently wrong), `coverage`
      with enumerated periods, `core_columns`, example queries.
- [ ] **Validate against live BQ before committing:** documented columns == actual
      schema (none missing, none extra), every example query executed. Numbers in
      prose are query results, not recollection.
- [ ] **Registry row in CLAUDE.md**, alphabetical position.

## Phase 5 — Product surface (college-predictor)

Route by what the data is:
- **Cutoffs/admissions** → the predictor: data JSON generated FROM the clean
  parquet (app and warehouse must not drift), exam config, filters.
- **College info** → the college-info surface (see the college-tab branch).
- **Scholarships** → the scholarships flow.

- [ ] **Dropdown honesty:** every option reachable (returns rows), every data value
      inside the dropdown vocabulary, exact label==value where the filter compares
      raw. Test with the REAL submitted strings, not hand-written ones.
- [ ] **Offline filter test:** replicate getFilters exactly, sweep the full option
      grid, count dead combos.
- [ ] **Browser audit — non-negotiable.** Run the app, click through the new exam:
      form flow, every dropdown, expanded rows, one absurd input. Three sessions
      running, this step caught something offline checks missed every time
      (unreachable categories, a private college shown as govt, duplicate rows).
- [ ] **Site-visible changes go by PR; data refreshes and pipeline code go to main.**
      Check the deploy preview — it builds on case-sensitive Linux and has caught
      what a Mac cannot (Navbar vs navbar).

## Phase 6 — Open data (if shareable)

- [ ] **Publish via `open_data/publish.py` only** — publication is a deliberate act;
      the private bucket's permissions never change.
- [ ] Raw + extracted only. No processed/derived artifacts (projections and models
      are editorial work, not source data).
- [ ] PII columns dropped at publish, each drop recorded in the manifest.
- [ ] **Title convention `"<Group> — <What it is>"`** — the page groups on it. Human
      titles, sentence case, state spelled out. Multi-part documents zipped.
- [ ] Per-dataset `source` link (only URLs we actually hold), `category`
      (admissions / education-statistics), per-file year.
- [ ] Verify one anonymous download with zero credentials.

## Phase 7 — Close the loop

- [ ] README(s) updated; coverage/gaps stated honestly (blank-with-reason beats a
      plausible wrong number — the Mizoram 435-vs-335 lesson).
- [ ] Tell the team what shipped and where it lives.

---
*Born from the NEET/TNEA/KCET onboarding runs of Aug 2026. When a step feels
skippable, reread the lesson attached to it.*
