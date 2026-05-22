# Wage Curves — Methodology

How we estimate graduate starting wages and employment across the tiers of
Indian higher education, by discipline, plus wage growth to age 40. This is the
full analytical record; [`README.md`](README.md) is the quick file reference.

---

## 1. Objective

For each discipline, build a "wage curve" from the elite institutes down to the
long tail of unranked colleges, answering:
- **How many** graduate from each tier (graduating-class size)?
- **What share** are employed / placed?
- **What do they earn** at entry, and how does that grow to ~age 40?

Recurring finding: the ranked elite is a *tiny* slice — **~80% of engineering,
95% of medical, 97% of law graduates come from non-ranked colleges** — so the
published (NIRF) wage data describes only the top few percent. PLFS anchors the
mass.

---

## 2. Data sources

| Source | Access | Role | Vintage |
|---|---|---|---|
| **NIRF** | BigQuery `nirf_fact_aggregate` | Ranked elite: placement rate + median fresh-grad salary per institute | ranking_year 2022 (Agri 2023) |
| **AISHE** | `../aishe/clean/outturn.parquet` | Canonical graduating-class totals by discipline (UG) | 2021-22 |
| **PLFS** | `../plfs/clean/annual_2022_23/perv1.csv` | Population wages + employment by degree bucket and by NCO occupation | annual 2022-23 |
| **JoSAA seats** | `josaa_2022_seats.csv` (public matrix) | UG intake for IIT/NIT/IIIT (NIRF undercounts them) | 2022 |
| **NMC** | `../nmc/clean/mbbs_seats.parquet` | Govt/private MBBS seats | 2024-25 |
| **Avanti College DB** | `../../College DB/` | BDS seats; IIT/NIT/IIIT institute reference + placement | 2024-26 |
| **External** | web | 7th Pay Commission (doctor pay); IIT alumni surveys (elite CAGR) | — |

**Vintage drift** is real (NIRF 2022 / AISHE 2021-22 / PLFS 2022-23 / JoSAA 2022 /
NMC 2024-25 / BDS 2025-26). Everything is aligned to ~2021-22 where possible;
residual mismatch is documented per row's `source` field.

---

## 3. Discipline groupings & crosswalks

Each source carries its own grouping plus a mapping to the coarser ones. **PLFS
is coarsest**: its `technical_education` field only separates Engineering,
Medicine, and Agriculture; everything else (Arts/Commerce/Science/Law/Mgmt/…)
collapses into one **"General graduate/PG"** bucket.

| Source | Crosswalk file | Maps |
|---|---|---|
| PLFS (own) | `../plfs/codemaps/discipline.csv` | `tedu_lvl` → `plfs_discipline` |
| NIRF | `../nirf/codemaps/discipline_crosswalk.csv` | `ranking_category` → NIRF discipline → PLFS |
| AISHE | `../aishe/codemaps/discipline_crosswalk.csv` | AISHE discipline → NIRF → PLFS |

---

## 4. Core method (three layers per discipline)

```
NIRF  ── ranked elite: placement rate + median fresh-grad salary (per institute)
  │
AISHE ── canonical total graduating class  →  residual "Others X" = AISHE − NIRF-ranked
  │
PLFS  ── population anchor (wage + employment)  →  back-solve the unobserved tail so the
           graduate-weighted average across all tiers reconciles to the PLFS anchor
```

Back-solve formula for the residual tier (wage shown; placement identical with
the WPR anchor):

```
wage_others = (anchor_PLFS × AISHE_total − Σ_ranked grads_t × wage_t) / grads_others
```

This is applied where PLFS gives a clean **degree-bucket** anchor for the whole
graduate population (Engineering, Agriculture, and — via the general bucket — Law).
Medicine is handled differently (§7).

---

## 5. Engineering decomposition

Tiers, top to tail (`build_wage_curve.py`, `build_full_curve.py`):

| Tier | Sizing | Wage | Placement |
|---|---|---|---|
| IIT / IIIT / NIT | **JoSAA 2022 seats × 0.93** completion | NIRF 2022 median | NIRF 2022 |
| Top Colleges (rest of top-200 NIRF) | NIRF `graduating_on_time` | NIRF 2022 median | NIRF 2022 |
| Others (non-NIRF) | AISHE − above (residual) | back-solved (PLFS Eng anchor) | back-solved |

**Why seats for the public tiers, not NIRF counts:** NIRF `graduating_on_time`
is unreliable for IITs/NITs/IIITs — they run split 4-yr + 5-yr programs and
report them inconsistently (e.g. IIT Madras shows only its 5-yr dual degree;
some IITs show 0), so NIRF captures only ~6k grads for 19 IITs vs ~16k reality.
Private colleges run a single B.Tech and report completely, so the "Top Colleges"
tier keeps its NIRF counts. JoSAA seat totals also already cover the institutes
NIRF didn't rank, so no separate "un-ranked publics" step is needed.

- **JoSAA 2022 seats**: IIT 16,598 (23) · NIT 23,994 (31) · IIIT 7,126 (26) ·
  GFTI 6,759 (sum = 54,477, the cited JoSAA total).
- **Completion rate 0.93** (UG seats → graduates) — tunable (`--completion-rate`).

**ASSUMPTION — elite pool anchored to 2.5 lakh (`ELITE_POOL`).** IIT + IIIT + NIT +
Top Colleges are made to sum to **250,000**, the count of JEE Main qualifiers
eligible for JEE Advanced — a clean, well-known anchor for "the elite engineering
pool." IIT/IIIT/NIT are fixed by seats (~44.4k); **Top Colleges is then expanded
from its NIRF count (143,015) to 205,622** by absorbing the **top ~62.6k of the
Engg-Others tail**, assumed to perform like Top Colleges (NIRF wage ₹5.7L,
placement 69.7%). The Engg-Others residual shrinks to **579,627** (= AISHE eng −
250,000) and its back-solved wage/placement fall accordingly (₹2.68L→₹2.35L,
51.4%→49.4%) since more high earners moved up. Tune via `ELITE_POOL`.

---

## 6. Medical decomposition

Government medical is the targeted segment (analogous to IIT/NIT). Tiers:

| Tier | Sizing | Wage |
|---|---|---|
| Govt Medical (MBBS+BDS) | NMC + College DB seats × 0.93 | PLFS occupation (doctor/dentist), seat-weighted |
| Pvt Medical (MBBS+BDS) | NMC + College DB seats × 0.93 | same |
| Others (AYUSH/Nursing/allied) | residual of AISHE Medical Science | PLFS NCO-222 nursing |

- **Seats:** Govt MBBS 430 colleges / 60,324 (NMC, cross-checked vs College DB);
  Pvt MBBS 350 / 57,866; Govt BDS 60 / 4,046; Pvt BDS 270 / 23,970.
- **Wages by occupation, not back-solve:** doctor pay doesn't follow a campus-
  placement model. MBBS = PLFS NCO-221 (₹64.2k/mo all-ages salaried; ₹45k young;
  govt junior-resident gross ~₹65k via 7th CPC). BDS = NCO-226 (~₹20k/mo). The
  AISHE "Medical Science" total is a degree-mixed cluster (MBBS+BDS+AYUSH+
  nursing), so a single back-solved tail wage would be meaningless — wages are
  segmented by degree instead (`medical_salaries.csv`).
- **Key contrast with engineering:** medical wages are set by **degree**
  (MBBS ≈ ₹64k vs BDS ₹20k vs nursing ₹14.5k), not college tier — an MBBS grad
  earns the same from a govt or private college; govt-vs-private matters for
  *access/cost/merit*, not pay.

---

## 7. Agriculture & Law — consistent degree view (a deliberate choice)

**Principle:** the employment rate and the wage must describe the **same
population**. Pairing an *occupation* wage (what people working in the field
earn) with a *degree/general* employment rate double-counts a professional
premium that most graduates never realise.

- **Agriculture** is separable in PLFS (own `tedu` code) → uses its **agri-degree
  bucket** for both rate (34.3% WPR) and wage (₹252k). Consistent.
- **Law** is *not* separable in PLFS (lands in the general-graduate bucket) → uses
  the **general-graduate bucket** for both rate (38.5%) and wage (₹180k).
- **Occupation wages are kept as side references only** (lawyers NCO-261 ~₹300k;
  agri-pros NCO-131+213 ~₹300k). They describe those *working in the field*, which
  is a small minority — see §8.

**Evidence this is right (the lawyer reconciliation):** among general grads aged
22-30 (34.8M), only **~80k (0.23%)** work as lawyers (NCO-261). Against ~970k law
graduates in that age band (AISHE 107,945/yr × ~9 yrs), that's **~8% who actually
practise law**. So pricing all law grads at the lawyer wage would have been wrong
by an order of magnitude.

---

## 8. The "Others (general)" bucket and its occupation profile

The general (non-technical) bucket is huge — **6.45M of 7.75M UG grads (83%)** —
and priced at the PLFS general-graduate wage (₹180k, WPR 38.5%). It is *not*
uniform, so `general_grad_occupations.py` decomposes it by NCO occupation
(share of population × wage). Among general grads aged 22-30 (employment 41%):
crop growers 5.5%, shop salespersons 5.0%, teachers ~4%, clerks ~4%, finance 1.5%,
software 1.0% (₹30k/mo); high-pay professional roles are small slices; ~59% are
not employed / out of labour force. This table also lets us **size field-specific
supply from the general pool** (occupation share × general-grad population −
NIRF-college output = non-ranked contribution; treat as ratios — PLFS stock vs
AISHE/NIRF flow).

---

## 9. Wage anchors (PLFS young-cohort, annual ₹)

| Discipline | Anchor ₹/yr | Basis |
|---|---|---|
| Engineering | 360,000 | degree bucket, age 22-28 |
| Agriculture | 252,000 | agri-degree bucket (small n) |
| General (incl. Law) | 180,000 | general-graduate bucket |
| Medicine (MBBS) | 540,000 | occupation NCO-221 (doctors), 25-34 |
| Medicine (BDS) | 240,000 | occupation NCO-226 |
| Medicine (nursing/allied) | 192,000 | occupation NCO-222 |
| *Law in-field (reference)* | *300,000* | *occupation NCO-261 — NOT the curve anchor* |
| *Agri in-field (reference)* | *300,000* | *occupation NCO-131+213 — reference only* |

Source: `wage_by_discipline.py` (degree buckets) and PLFS
NCO-occupation cuts. All annualised ×12.

---

## 10. Placement / employment rates

- **Anchor** = PLFS young-cohort employment rate (WPR) per discipline:
  Engineering 55.9% · Medicine 50.6% · Agriculture 34.3% · General 38.5%.
- **Non-NIRF tiers** are back-solved from the discipline WPR (same machinery as
  wages); NIRF tiers keep their measured campus-placement %.
- **Construct caveat:** NIRF "placement" is a campus-*offer* %; PLFS WPR is
  *observed employment* %. Mixing them is first-order, like the wages. Two
  artefacts to know:
  - **Agri Others (35.5%) > Agri NIRF (29.6%)** — not a bug: agri grads favour
    PG/govt exams over campus placement, so NIRF's campus-offer % sits *below* the
    broader employment rate.
  - **Medical 50.6% is uniform** across govt/pvt/others — it's the discipline WPR;
    young WPR is depressed by the residency/PG-prep pipeline, so actual doctor
    employment is higher.

---

## 11. Wage growth, age 25 → 40

**PLFS age-wage profile** (`wage_growth.py`, annual_2022_23, regular-salaried
median by 5-yr band):

| Discipline | 25-29 → 40-44 | Multiple |
|---|---|---|
| Engineering | ₹32k → ₹55k/mo | 1.7× |
| Medicine | ₹20k → ₹55k/mo | 2.75× (junior → specialist) |
| General | ₹16.8k → ₹30k/mo | 1.8× |

This is **cross-sectional** (today's 40-yr-olds vs today's 25-yr-olds), which
*understates* longitudinal growth — today's 40-yr-olds started ~15 yrs ago at
lower real wages — so the multiple is a **lower bound** even for the population.

**NIRF elite projection** — PLFS cannot observe IIT-level earners (IIT starts at
₹13L/yr, above PLFS engineering P90 of ~₹11.5L/yr at *any* age, due to small
population + survey top-coding). We therefore bound their 25→40 growth:

| | Multiplier | IIT ₹13L → @40 |
|---|---|---|
| **PLFS-rate (floor)** | ×1.7 (eng median) | ₹22.4L |
| **Elite CAGR** | ×3.6 (9%/yr × 15y) | ₹47.5L |

The **9% elite CAGR** is anchored to IIT alumni salary data: start ₹8-15L →
₹30-60L mid-career (5-10y) → ₹50L-1cr senior (15y+), implying a ~8-10% 15-year-
average CAGR (steeper early, flattening later). Tunable via `--elite-cagr`.

**Counter-signal:** top-campus *entry* wages are down ~22% in real terms since
2010 and IIT placement has fallen below 70% — so the starting point is under
pressure even as the growth multiple for those in tech/finance/management stays
steep.

---

## 12. Headline output

**`wage_curve_full.csv`** (13 rows) is the single consolidated table. Columns:
`discipline, tier, institutes, graduates, share_in_disc_pct, share_all_pct,
placement_pct, start_wage_inr, wage_growth_pct_to40, wage_at_40_inr,
growth_basis, source` — i.e. graduating-class size, placement rate, starting
wage, growth %, and the projected wage at ~age 40, all in one place (growth per
the §11 rule: elite 9% CAGR for NIRF-ranked engineering tiers, PLFS discipline
multiple for the rest).

```
Tier                   Grads   Place%   Start ₹   Grow%    @40 ₹
IIT                   15,436    78.7%    13.0L     264%    47.5L     ← 0.2% of all UG grads
IIIT                   6,627    64.4%    13.2L     264%    48.0L
NIT                   22,314    78.3%     7.2L     264%    26.1L
Top Colleges         205,622    69.7%     5.7L     264%    20.8L     ← expanded to fill the 250k JEE pool
Eng Others (non-NIRF) 579,627   49.4%     2.3L      72%     4.0L     ← 70% of engineering grads
Govt Medical          59,864    50.6%     5.2L     175%    14.3L
Pvt Medical           76,107    50.6%     4.5L     175%    12.4L
Medical Others       165,508    50.6%     1.9L     175%     5.3L
Agriculture NIRF      14,052    29.6%     4.9L     103%    10.0L
Agriculture Others    54,625    35.5%     1.9L     103%     3.9L
Law NIRF               3,695    61.7%     7.8L      79%    14.0L
Law Others           104,250    37.7%     1.6L      79%     2.8L
Others (general)   6,446,494    38.5%     1.8L      79%     3.2L     ← 83% of ALL UG grads
── aggregates (graduate-weighted) ──
Top 3L seats         309,863    67.0%     6.3L     250%    21.9L     ← 4% of grads: JEE-elite engg + govt medical
Others             7,444,358    39.7%     1.9L      83%     3.4L     ← the other 96%
```

The two bottom rows are graduate-weighted roll-ups: **"Top 3L seats"** =
IIT + IIIT + NIT + Top Colleges + Govt Medical (MBBS+BDS) — the ~3.1 lakh
genuinely selective seats — and **"Others"** = everyone else. The gap is the
headline: the selective 4% start ~3.3× higher and pull away further with age
(₹6.3L→₹21.9L vs ₹1.9L→₹3.4L).

---

## 13. Reproduce

```bash
python3 wage_curves/build_full_curve.py            # → wage_curve_full.csv (headline)
python3 wage_curves/build_discipline_summary.py    # → discipline_summary.csv
python3 wage_curves/build_wage_curve.py --plfs-annual-wage 360000 --plfs-placement-rate 55.9
python3 wage_curves/general_grad_occupations.py     # → general_grad_occupations.csv
python3 wage_curves/wage_growth.py [--elite-cagr 0.09]   # → wage_growth.csv
python3 wage_curves/extract_avanti_college_db.py    # refresh institute reference
python3 wage_curves/extract_govt_medical_seats.py   # refresh medical seats
```

---

## 14. Caveats & limitations (consolidated)

1. **NIRF undercounts public-tier grad counts** → engineering publics sized from
   JoSAA seats (§5).
2. **PLFS can't separate non-technical degrees** → Law uses the general bucket;
   only Engineering/Medicine/Agriculture are separable.
3. **Degree vs occupation**: occupation wages describe in-field workers, a
   minority for Law (~8% practise) — kept as references, not curve anchors (§7).
4. **Placement = employment proxy**, not campus-offer; construct mismatch and the
   agri inversion / medical-WPR notes in §10.
5. **PLFS can't observe the elite tail** → wage-growth elite column is a bounded
   assumption (§11).
6. **Cross-sectional age profile** understates true longitudinal growth (§11).
7. **Small samples** for Medicine/Agriculture wage cells (n in tens).
8. **Vintage drift** across sources (§2).
9. **PLFS stock vs AISHE/NIRF flow** — supply reconciliations are ratios, not
   levels (§8).
10. **MBA dropped** (PG; AISHE parquet is UG-only, NIRF mgmt placement only 2025).
    Pharmacy/Dental/Architecture are NIRF-only (AISHE folds them into Medical
    Science / Engineering).
11. **Elite pool anchored to 250k JEE qualifiers** (`ELITE_POOL`): Top Colleges is
    expanded from its NIRF count (143k → 206k) by reclassifying the top ~62.6k of
    the Engg-Others tail as "similar to Top Colleges" (§5). A modelling choice for
    a clean elite-pool size, not a measured boundary.

---

## 15. External sources

- IIT alumni mid-career earnings — [Quora](https://www.quora.com/How-much-does-an-IITian-earn-after-5-10-years-of-work-experience)
- *Top Talent, Elite Colleges, and Migration: Evidence from the IITs* — [J. Dev. Econ.](https://www.sciencedirect.com/science/article/pii/S0304387823000755)
- *Diminishing Returns of Higher Education in India* — [PUIRP](https://www.puirp.com/index.php/research/article/view/53)
- Doctor pay (7th Pay Commission junior resident) — [Docthub](https://blogs.docthub.com/mbbs-doctor-salary-in-india-private-and-government-2024-BLG212), [India.com](https://www.india.com/business/7th-pay-commission-up-government-hikes-salaries-of-junior-and-senior-resident-doctors-demonstrators-3812583/)
