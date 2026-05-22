# wage_curves

Cross-source **graduate wage-curve** analysis: how starting wages vary across
the tiers of India's higher-education system, by discipline. Combines three
primary sources plus two reference pulls.

> This is an **analysis**, not a source pipeline — it consumes the `nirf/`,
> `aishe/`, and `plfs/` sources rather than ingesting an upstream. It lives at
> the repo root (not under a single source) because it spans all three.

**[METHODOLOGY.md](METHODOLOGY.md)** is the full analytical record — every data
source, decision, formula, and caveat. This README is the quick file reference.

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
| `datasource.py` | **Single data seam** — all source access (NIRF→BQ live; AISHE/NMC/PLFS→local parquet/CSV today, with the BQ-target table per source documented for when they load). The analysis scripts never touch sibling-repo internals. |
| **`build_full_curve.py` → `wage_curve_full.csv`** | **Headline output** — every tier of every discipline, top to tail (NIRF elite + non-NIRF residuals), PLFS-anchored |
| `wage_by_discipline.py` | PLFS wage + employment baseline by discipline (the anchors); supports `--age-min/--age-max` for the young-cohort fresh-grad view |
| `nirf_engineering_tiers.sql` | NIRF engineering tier query (IIT/NIT/IIIT split) — used by `build_full_curve.py` |
| `general_grad_occupations.py` → `general_grad_occupations.csv` | Occupation profile of general (non-technical) grads — decomposes the flat "Others (general)" row by NCO occupation (share + wage) |
| `wage_growth.py` → `wage_growth.csv` | Age 25→40 wage growth: PLFS age-wage profile per discipline + NIRF-elite projection (PLFS-rate ×1.7 floor vs 9% elite CAGR) |
| `josaa_2022_seats.csv` + `extract_*`† | Public-tier UG seat counts (JoSAA 2022) |
| `iit_nit_iiit_institutes_avanti_db.csv` + `extract_avanti_college_db.py` | Per-institute IIT/NIT/IIIT reference (counts + placement) |
| `govt_medical_seats.csv` + `medical_salaries.csv` + `extract_govt_medical_seats.py` | Govt MBBS/BDS seats + credible doctor/dentist wages |

†JoSAA seats are hand-entered from the public 2022 seat matrix (no extractor).

## Running

```bash
# Headline: full top-to-tail curve, all tiers + Top-3L/Others roll-ups
python3 wage_curves/build_full_curve.py

# Supporting analyses
python3 wage_curves/wage_by_discipline.py [--age-min 22 --age-max 28]  # PLFS anchors
python3 wage_curves/general_grad_occupations.py
python3 wage_curves/wage_growth.py [--elite-cagr 0.09]

# Refresh the pulled reference CSVs
python3 wage_curves/extract_avanti_college_db.py
python3 wage_curves/extract_govt_medical_seats.py
```

PLFS wage anchors come from [`wage_by_discipline.py`](wage_by_discipline.py)
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
- `wage_growth.csv` — PLFS age-wage profile (annual_2022_23); elite 9% CAGR anchored to IIT
  alumni salary data (start ₹8-15L → ₹30-60L mid-career → ₹50L-1cr senior ⇒ ~8-10% 15-yr CAGR).
  Caveat: top-campus entry wages ↓~22% real since 2010 & IIT placement <70%. Sources:
  [IITian earnings 5-10y (Quora)](https://www.quora.com/How-much-does-an-IITian-earn-after-5-10-years-of-work-experience) ·
  [Top Talent, Elite Colleges & Migration: Evidence from the IITs, J.Dev.Econ](https://www.sciencedirect.com/science/article/pii/S0304387823000755) ·
  [Diminishing Returns of Higher Education in India](https://www.puirp.com/index.php/research/article/view/53)

## Caveats (also documented in-script)

- **NIRF `graduating_on_time` undercounts IITs/NITs/IIITs** (inconsistent 4-yr/5-yr
  program reporting) — so the public engineering tiers are sized from JoSAA seats,
  not NIRF counts. Private colleges report completely and keep their NIRF counts.
- **Wage & placement use the SAME population (degree view)**: rate and wage must
  describe one population, else you double-count a professional premium. So
  Engineering and Agriculture use their PLFS *degree* buckets (separable); Law
  isn't separable in PLFS → it uses the *general-graduate* bucket. The occupation
  wages (lawyers ₹300k, agri-pros ₹300k) are kept only as side references — most
  law grads don't practise law (see `general_grad_occupations.csv`: NCO-261 legal
  is <0.5% of general grads), so the lawyer wage can't price all law grads.
  Medicine is the exception: MBBS→doctor is a tight pipeline, so its occupation
  wage ≈ the employed-grad wage.
- **Placement rate** = PLFS young-cohort employment (WPR) per discipline,
  back-solved for the non-NIRF tiers. NIRF "placement" is a campus-offer %, PLFS
  is observed employment % — mixed first-order. Watch: Agri Others (35.5%) > Agri
  NIRF (29.6%) because agri grads favour PG/govt over campus placement; and
  Medical's 50.6% is the discipline WPR (young, depressed by residency/PG pipeline
  — actual doctor employment is higher).
- **Vintage drift**: NIRF 2022 / AISHE 2021-22 / PLFS 2022-23 / JoSAA 2022 /
  NMC 2024-25 / BDS 2025-26. Aligned to ~2021-22 where possible.
- **MBA dropped** (PG; AISHE parquet is UG-only and NIRF management placement
  exists only in 2025). Pharmacy / Dental / Architecture are NIRF-only (AISHE
  folds them into Medical Science / Engineering).
