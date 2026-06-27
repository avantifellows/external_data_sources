# naac

NAAC (National Assessment and Accreditation Council) accreditation data → BigQuery.

Three sheets from the official NAAC download (naac.gov.in → Accreditation Status),
covering all institutions with **valid accreditation as of 14-Aug-2025**.

## What NAAC is

NAAC is India's public body for assessing and accrediting higher education
institutions (HEIs). Established in 1994 under the University Grants Commission
(UGC), headquartered in Bengaluru. Its mandate: make quality assurance an
integral part of how Indian HEIs function.

### Grading system

NAAC scores institutions on a **0–4 CGPA scale** across seven assessment
criteria. The final CGPA maps to a letter grade:

| Grade | CGPA band | What it means |
|---|---|---|
| A++ | 3.51 – 4.00 | Highest |
| A+  | 3.26 – 3.50 | |
| A   | 3.01 – 3.25 | |
| B++ | 2.76 – 3.00 | |
| B+  | 2.51 – 2.75 | |
| B   | 2.01 – 2.50 | |
| C   | 1.51 – 2.00 | Lowest passing grade |
| D   | < 1.51 | Not accredited |

### Accreditation cycles

Each round of assessment is called a **cycle**. `current_cycle_number` in the
data = how many full accreditation rounds an institution has completed in its
history:

- **Cycle 1** = first-ever NAAC assessment
- **Cycle 5** = the institution has been continuously re-accrediting for ~25
  years (5 cycles × 5 years each)
- If an institution lets accreditation lapse and later reapplies, the cycle
  counter **resets to 1**

Accreditation is valid for **5 years** from the `date_of_declaration`. An
exception: institutions that score top grades in two consecutive prior cycles
may receive **7-year** validity. Institutions can also voluntarily apply for
reassessment (to try to improve their grade) after a minimum of 1 year but
before 3 years.

NAAC does **not** update grades annually — one grade per cycle, fixed until
the next assessment is completed. A grade from 2020 still stands today if the
institution hasn't completed its next cycle yet.

> **Note (Feb 2025):** NAAC announced a major overhaul — replacing the 5-year
> CGPA system with a Binary Accreditation framework (Accredited / Not
> Accredited) + MBGL levels, with 3-year validity. As of mid-2026 the new
> portal has not launched. This dataset reflects the legacy CGPA system.

### HEI types and assessment differences

NAAC categorises institutions into three types and applies different criterion
weightages to each:

- **University** — assessed on its own governance structure + all departments.
  Minimum threshold to proceed: 60%.
- **Autonomous College** — a college that has received UGC Autonomous Status
  (can set its own curriculum and exams, but still affiliated to a university
  for degree-granting). Minimum threshold: 50%.
- **Affiliated / Constituent College** — a college using the parent
  university's syllabus and exams. Minimum threshold: 40%.

This matters for analysis: **never compare CGPA directly across types** without
accounting for the different criteria weightages.

### Identifiers

- **AISHE-Id** — All India Survey on Higher Education unique code. Format:
  `U-XXXX` for universities, `C-XXXXX` for colleges. This is the stable
  national identifier — use it to join NAAC with other datasets.
- **Track-Id** — NAAC's internal tracking ID. Prefix encodes state + type
  (e.g. `AP` = Andhra Pradesh, `UN` = University, `CO` = College,
  `GN` = Government/aided). Not a standard national identifier.

---

## The three sheets / tables

### 1. Universities (497 rows)

Universities with valid NAAC accreditation. Assessed on their own governance
and departments. AISHE-Id format: `U-XXXX`.

### 2. Colleges (7,566 rows)

Affiliated, constituent, and autonomous colleges. This is the largest and most
useful table for career counseling — most colleges Avanti students apply to
appear here. One extra column vs. Universities: `affiliating_university`
(the university the college is legally affiliated to for degree-granting).
AISHE-Id format: `C-XXXXX`.

### 3. Transition Autonomous Colleges (290 rows)

A special legacy category requiring context to interpret correctly:

These colleges were originally **affiliated colleges** — accredited by NAAC
under affiliated-college criteria (receiving a CGPA and grade). They
subsequently received **UGC Autonomous Status**, which meant their existing
NAAC grade was earned under the wrong framework (affiliated ≠ autonomous
criteria). Rather than immediately de-accrediting them, NAAC created a
"Transition" provision: extend the old accreditation validity temporarily
while the college queues for reassessment under the autonomous-college
framework.

**Consequences for the data:**
- **No CGPA, no grade, no AISHE-Id, no Track-Id** — only `hei_name`, `state`,
  and `extended_validity_upto`. The old grade is no longer considered valid
  under the new category; these institutions are awaiting fresh assessment.
- **~61 of the 290 colleges have already expired** (`extended_validity_upto`
  in 2024 or earlier as of Aug 2025).
- **`hei_name` embeds the full address** (separated by a newline in the
  source) — there is no separate address column. `build_clean.py` collapses
  the newlines but does not split name from address.
- **No reliable join key to other datasets.** The only path to NIRF, JoSAA,
  or the main colleges table is fuzzy name matching.
- Heavily concentrated in Maharashtra (113), Tamil Nadu (54), Andhra Pradesh
  (40), Telangana (24), Karnataka (19) — states with heavy autonomous college
  culture.

---

## Pipeline

```
naac/raw/*.xlsx               (committed to repo — 1 MB)
       │
       │  scripts/build_clean.py   (rename cols, clean text, parse dates)
       ▼
naac/clean/*.parquet           (gitignored; local intermediate)
       │
       │  scripts/upload_to_gcs.py (pure upload — no transform)
       ▼
gs://avantifellows-external-data/naac/*.parquet
       │
       │  scripts/load_bq.py       (load_table_from_uri, WRITE_TRUNCATE)
       ▼
avantifellows.external_data_sources.naac_fact_*    (3 tables, asia-south1)
```

Single source of truth for all config: [`scripts/sources.py`](scripts/sources.py).

## Tables produced

| Table | Rows | Grain |
|---|---:|---|
| `naac_fact_universities` | 497 | `aishe_id` |
| `naac_fact_colleges` | 7,566 | `aishe_id` |
| `naac_fact_transition_autonomous_colleges` | 290 | `hei_name` |

All tables carry `data_as_of = 2025-08-14` (the date the source file was
published on naac.gov.in). Schemas: [`schemas/*.yaml`](schemas/).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 1. Build clean parquets
.venv/bin/python scripts/build_clean.py
.venv/bin/python scripts/build_clean.py --dry-run     # validate locally first

# 2. Upload to GCS
.venv/bin/python scripts/upload_to_gcs.py

# 3. Load GCS → BQ
.venv/bin/python scripts/load_bq.py
```

One-time prerequisites:
```bash
gcloud storage buckets create gs://avantifellows-external-data --location=asia-south1
bq --location=asia-south1 mk --dataset avantifellows:external_data_sources
```

## Updating with a new NAAC release

1. Replace the xlsx in `raw/` with the new file.
2. Update `XLSX_FILE` and `DATA_AS_OF` in `scripts/sources.py`.
3. Re-run `build_clean.py` → `upload_to_gcs.py` → `load_bq.py`.

BQ's 7-day time travel covers rollbacks if something goes wrong.
