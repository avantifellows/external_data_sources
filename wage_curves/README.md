# wage_curves

Cross-source **graduate wage-curve** analysis: how starting wages vary across
the tiers of India's higher-education system, by discipline. Combines three
primary sources plus two reference pulls.

> This is an **analysis**, not a source pipeline — it consumes the `nirf/`,
> `aishe/`, and `plfs/` sources rather than ingesting an upstream. It lives at
> the repo root (not under a single source) because it spans all three.

## The question

For a given discipline, what does a graduate earn — and how steeply does that
fall from the elite institutes to the long tail of unranked colleges?

## Method (three layers per discipline)

```
NIRF  ── the ranked elite: placement rate + median fresh-grad salary per institute
  │        (split into IIT / NIT / IIIT / Other-NIRF tiers for Engineering)
AISHE ── the canonical denominator: total graduating class per discipline
  │        → residual "Other X Colleges" = AISHE total − NIRF-ranked
PLFS  ── the population anchor: the discipline's whole-population graduate wage
           → back-solve the unobserved tail wage so the grad-weighted average
             across all tiers reconciles to the PLFS anchor
```

The recurring finding: the NIRF-ranked elite is a *tiny* slice — **80 % of
engineering, 95 % of medical, 97 % of law** graduates come from non-ranked
colleges. The published wage data only describes the top few percent; PLFS pins
down the mass.

## Discipline groupings & crosswalks

Each source carries its own discipline grouping plus a mapping to the coarser
ones (PLFS is coarsest — it can only separate Engineering / Medicine /
Agriculture; everything else collapses to "General graduate/PG"):

| Source | File | Maps |
|---|---|---|
| PLFS (own) | [`../plfs/codemaps/discipline.csv`](../plfs/codemaps/discipline.csv) | `technical_education` → `plfs_discipline` |
| NIRF | [`../nirf/codemaps/discipline_crosswalk.csv`](../nirf/codemaps/discipline_crosswalk.csv) | `ranking_category` → NIRF discipline → PLFS |
| AISHE | [`../aishe/codemaps/discipline_crosswalk.csv`](../aishe/codemaps/discipline_crosswalk.csv) | AISHE discipline → NIRF → PLFS |

## Files

| File | What |
|---|---|
| `build_wage_curve.py` + `nirf_engineering_tiers.sql` | Engineering tiered curve (IIT/NIT/IIIT/Other-NIRF/tail), seat-corrected publics |
| `build_discipline_summary.py` → `discipline_summary.csv` | Cross-discipline summary table |
| `josaa_2022_seats.csv` + `extract_*`† | Public-tier UG seat counts (JoSAA 2022) |
| `iit_nit_iiit_institutes_avanti_db.csv` + `extract_avanti_college_db.py` | Per-institute IIT/NIT/IIIT reference (counts + placement) |
| `govt_medical_seats.csv` + `medical_salaries.csv` + `extract_govt_medical_seats.py` | Govt MBBS/BDS seats + credible doctor/dentist wages |

†JoSAA seats are hand-entered from the public 2022 seat matrix (no extractor).

## Running

```bash
# Engineering tiered curve (PLFS anchor = young-cohort engineering wage, annual ₹)
python3 wage_curves/build_wage_curve.py --plfs-annual-wage 360000 --plfs-placement-rate 55.9

# Cross-discipline summary
python3 wage_curves/build_discipline_summary.py

# Refresh the pulled reference CSVs
python3 wage_curves/extract_avanti_college_db.py
python3 wage_curves/extract_govt_medical_seats.py
```

PLFS wage anchors come from [`../plfs/analyses/wage_by_discipline.py`](../plfs/analyses/wage_by_discipline.py)
(degree-based) or PLFS NCO-occupation cuts (doctors NCO-221, lawyers NCO-261).

## Runtime data dependencies (not committed — gitignored / external)

- **NIRF** → BigQuery `avantifellows.external_data_sources.nirf_fact_aggregate`
- **AISHE** → `../aishe/clean/outturn.parquet`
- **NMC** → `../nmc/clean/mbbs_seats.parquet` (MBBS seats)
- **Avanti College DB** → `../../College DB/` (BDS seats, institute reference)

## Provenance of the pulled CSVs

- `josaa_2022_seats.csv` — JoSAA 2022 public seat matrix (IIT/NIT/IIIT/GFTI; sum = 54,477)
- `iit_nit_iiit_institutes_avanti_db.csv` — Avanti College DB (`_institute_lookup.csv` + `college_database.csv`)
- `govt_medical_seats.csv` — MBBS from repo `nmc/` source; BDS from Avanti College DB (DCI/MCC)
- `medical_salaries.csv` — PLFS NCO-221/226 (doctors/dentists) + 7th Pay Commission junior-resident scale

## Caveats (also documented in-script)

- **NIRF `graduating_on_time` undercounts IITs/NITs/IIITs** (inconsistent 4-yr/5-yr
  program reporting) — so the public engineering tiers are sized from JoSAA seats,
  not NIRF counts. Private colleges report completely and keep their NIRF counts.
- **PLFS reconciles cleanly only for Engineering & Agriculture** (true degree
  buckets). Law uses an occupation anchor (employed lawyers ≠ all law grads);
  Medical's AISHE total is a degree-mixed cluster (MBBS+BDS+AYUSH+nursing), so its
  tail isn't back-solved — wages are segmented by degree in `medical_salaries.csv`.
- **Vintage drift**: NIRF 2022 / AISHE 2021-22 / PLFS 2022-23 / JoSAA 2022 /
  NMC 2024-25 / BDS 2025-26. Aligned to ~2021-22 where possible.
- **MBA dropped** (PG; AISHE parquet is UG-only and NIRF management placement
  exists only in 2025). Pharmacy / Dental / Architecture are NIRF-only (AISHE
  folds them into Medical Science / Engineering).
