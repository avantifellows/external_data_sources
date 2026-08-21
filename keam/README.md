# keam/

KEAM (Kerala Engineering Architecture Medical) counselling last ranks from
CEE Kerala — engineering 2025 + 2026 INCLUDING the live 2026 cycle, parsed
into one fact; architecture / B.Pharm / MBBS / allied PDFs archived verbatim
for later parsing. The Kerala counterpart to `wbjee/`, `tnea/`, `kcet/`.

## Pipeline shape

```
keam/raw/KEAM_<year>_<stream>_<phase>.pdf     18 PDFs + the 2 listing pages
       │  scripts/build_clean.py              parse the 5 engineering PDFs
       ▼
keam/clean/keam_fact_cutoffs.parquet          19,610 rows
       │  scripts/upload_to_gcs.py            raw + clean → GCS
       ▼
gs://avantifellows-external-data/keam/{raw,clean}/
       │  scripts/load_bq.py                  WRITE_TRUNCATE
       ▼
avantifellows.external_data_sources.keam_fact_cutoffs   (asia-south1)
```

**Single source of truth: [`scripts/sources.py`](scripts/sources.py).**

## Grain and quirks (the short version — schema YAML has the full story)

- One row per **phase × course × college × category**. KEAM publishes ONLY
  the closing (last) rank — no opening rank exists in the source.
- **Kerala's own category vocabulary**: SM (State Merit = open) + nine SEBC
  community columns (EZ/MU/BH/LA/DV/VK/BX/KN/KU) + SC/ST/EW, plus free-text
  sub-codes (FW fee-waiver, PD, YN, minority codes like MM, and 2026's new
  SD). `category_raw` is verbatim; `category` is the canonical 5-cat.
- **college_type**: CEE's own Type column — G (Govt AND Govt-Aided, Kerala
  collapses them) / S (self-financing). No name heuristics needed.
- 2026 has a **Trial** phase (CEE's mock allotment, new this year) — kept,
  scope on `phase` for real cutoffs. Engineering published through P2 as of
  2026-08-21; watch the last_rank page for later phases/stray rounds.
- Parser lesson: course tables spill across page breaks with no repeated
  header — the course must carry across pages or spilled rows orphan to
  course=None (a latent bug inherited from the futures-v2 parser, caught
  here by the zero-dupes assert).

## Fetch quirks

CEE 403s curl's default UA (send a browser UA) and keeps only the last two
cycles online — keam2023/keam2024 are gone, which is why raw/ is archived.

## Refresh drill (engineering P3 / stray rounds, or 2026 medical when it lands)

Add the file to `sources.py` RAW_FILES (+ ENGG_FILES if engineering), refetch
with a browser UA, rerun build → upload → load, then: data-assistant coverage
note, predictor build script, open-data publisher.
