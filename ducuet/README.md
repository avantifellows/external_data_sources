# ducuet

University of Delhi (DU) undergraduate admission cutoffs — CUET-based CSAS
2025-26 allocation, minimum allocation score per (college, program, category)
→ BigQuery.

One row per (college, program, category), holding the MIN minimum-allocation
score across the 3 published allocation rounds. Light PDF parse (pdfplumber
over 3 University-published PDFs), then parsed parquet → GCS → BQ.

**Source:** University of Delhi Admission Branch, *Undergraduate Admissions
2025-26* round-wise "Minimum Allocation Score" bulletins,
[admission.uod.ac.in](https://admission.uod.ac.in/). One PDF per allocation
round (Round 1, 2, 3 — 2025-26 cycle). Not redistributed via a stable URL per
round; see *Raw data* below.

## Pipeline at a glance

```
DU Admission Branch round-wise PDFs        (manually downloaded once; no stable per-round URL)
       │
       ▼
gs://avantifellows-external-data/ducuet/raw/<pdf>   (canonical home, via upload_to_gcs.py)
       │ scripts/build_clean.py   (fetches any PDF missing from raw/ from GCS, parses all 3, MIN per cell → one fact)
       ▼
clean/ducuet_fact_cutoffs.parquet                          (local; gitignored)
       │ scripts/upload_to_gcs.py   (uploads raw PDFs + clean fact)
       ▼
gs://avantifellows-external-data/ducuet/raw/<pdf>            (traceability)
gs://avantifellows-external-data/ducuet/clean/ducuet_fact_cutoffs.parquet
       │ scripts/load_bq.py
       ▼
avantifellows.external_data_sources.ducuet_fact_cutoffs   (asia-south1)
```

`build_clean.py` reads raw PDFs from local `raw/` if present, else fetches
them from the GCS `raw/` prefix first — so the build reproduces from a
clean clone without anyone hand-copying files, as long as the PDFs have
been uploaded to GCS at least once. The single source of truth for
filenames, GCS URIs, and BQ destinations is
[`scripts/sources.py`](scripts/sources.py).

## Why MIN across rounds, not "latest round"

DU's allocation rounds are **not** a cumulative re-run of one merit order.
Each round reallocates that round's vacant seats against whoever is still in
the pool, so a later round can quote a **lower** minimum score than an
earlier round for the exact same (college, program, category) seat, as
demand for it drops off. There is no single official "final cutoff" column
in the source — this table reports the lowest minimum-allocation score a
category cleared in **any** of the 3 published rounds, i.e. the most
generous number relevant to "could a student with score X have gotten this
seat at some point in the cycle."

A blank category for a (college, program) in a given round's PDF means no
seat was open in that category that round — not a score of 0. See
[`schemas/README.md`](schemas/README.md) for the full read-before-analysing
notes, including why 124 program rows only exist from Round 2 with no
Round 1 counterpart.

## Table produced

**`ducuet_fact_cutoffs`** — long/tidy fact. Grain:
`(college_name, program_name, category)` → `min_allocation_score` (+
`rounds_published`, which of 1/2/3 actually carried a value for that cell).

Scoped to the 6 categories common to all 3 round PDFs — UR, OBC, SC, ST,
EWS, PwBD. Round 2 additionally reports SIKH, KM, SGC, and ORPHAN
(Female/Male); those columns are parsed but out of scope for this table
(Round 1/3 never report them, so no MIN could be taken across all 3 rounds
anyway).

Schema: [`schemas/ducuet_fact_cutoffs.yaml`](schemas/ducuet_fact_cutoffs.yaml).

## GCS layout

```
gs://avantifellows-external-data/
  ducuet/raw/<pdf>                                 ← source DU PDFs, as-is (traceability)
  ducuet/clean/ducuet_fact_cutoffs.parquet          ← the fact; load_bq.py loads this
```

## Raw data

The 3 round PDFs are gitignored (`raw/*.pdf`); their canonical home is
`gs://avantifellows-external-data/ducuet/raw/`, not this machine.
`build_clean.py` fetches any of them missing from local `raw/` straight
from that GCS prefix, so a clean clone can reproduce the build without
anyone hand-copying files — as long as they've been uploaded there at
least once.

DU's Admission Branch publishes each round's bulletin as a one-off PDF on
the admission bulletin page with no stable, predictable URL per round
(unlike, say, MoE's annual report), so there is no `fetch.py` pulling from
DU directly — for a **new admission cycle**, download that cycle's Round
1/2/3 "Minimum Allocation Score" PDFs manually from
[admission.uod.ac.in](https://admission.uod.ac.in/), drop them at the paths
in `scripts/sources.py` → `ROUNDS`, and run `upload_to_gcs.py --raw-only`
once to seed GCS for everyone else.

| File | Round |
|---|---|
| `du_cuet_ug_2025_r1.pdf` | Round 1 |
| `du_cuet_ug_2025_r2.pdf` | Round 2 |
| `du_cuet_ug_2025_r3.pdf` | Round 3 |

## First-time setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
gcloud auth application-default login   # for the GCS fetch/upload + BQ load
```

## Running

```bash
# 1. parse the PDFs and merge → clean/ducuet_fact_cutoffs.parquet
#    (pulls any round PDF missing from raw/ down from GCS automatically)
.venv/bin/python scripts/build_clean.py --dry-run     # preview + validate
.venv/bin/python scripts/build_clean.py

# 2. stage to GCS — uploads raw PDFs + the clean fact
.venv/bin/python scripts/upload_to_gcs.py --dry-run    # preview
.venv/bin/python scripts/upload_to_gcs.py               # raw + clean
#   …or just one side: --raw-only / --clean-only

# 3. load to BigQuery
.venv/bin/python scripts/load_bq.py --dry-run           # preview
.venv/bin/python scripts/load_bq.py
```

`load_bq.py` uses `WRITE_TRUNCATE`, so the load fully replaces the table.
Only the clean fact is loaded to BQ — the raw PDFs on GCS are for
traceability.

## Caveats — read before analysing

See [`schemas/README.md`](schemas/README.md) for the full list. Headlines:

- **MIN across rounds, not latest-round.** Explained above — don't assume
  Round 3's value is "the" cutoff.
- **Program-name matching is normalized, not exact-string.** Round 2 types
  a trailing period DU's other PDFs omit (`B.Sc.` vs `B.Sc`); matching
  lowercases and strips periods before joining across rounds.
- **124 program rows exist only from Round 2.** "BA Program"
  subject-combination seats with no normalized-match in Round 1 — kept as
  their own rows rather than fuzzy-matched onto a similarly-worded but
  different subject combination.
- **Blank ≠ zero.** A missing category for a cell means no seat was open in
  that category in any of the 3 rounds, not that the cutoff was 0.
