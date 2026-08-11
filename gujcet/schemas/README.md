# ACPC Gujarat in 60 seconds

ACPC (Admission Committee for Professional Courses) runs Gujarat's centralised
admission for degree engineering and degree/diploma pharmacy. This table records
the **last admitted** candidate in each (institute, course, category) seat
bucket, from ACPC's own closure PDFs.

## The one thing that will bite you

**The two streams are different admission years.**

| stream | year |
|---|---|
| engineering | **2025**-26 |
| pharmacy | **2024**-25 |

```sql
-- ALWAYS scope to one cycle
WHERE stream = 'engineering' AND year = 2025
```

A query spanning both silently mixes cycles. Pharmacy is a year behind because
that is the latest closure ACPC published in this format.

## Two metrics, opposite directions

- `closing_rank` — merit rank, **lower = harder**
- `closing_percentile` — 0-100 composite score, **higher = harder**

They correlate at −0.96. Never mix them in one `ORDER BY`.

`closing_rank` is **FLOAT**: ACPC publishes tied ranks with a `.5` suffix
(e.g. `36906.5`), same as KEA does for KCET.

## The engineering rank is not a GUJCET rank

Gujarat's Home-State merit list blends **GUJCET ⅓ + JEE Main ⅓ + Class 12 ⅓**
into one composite score, so there is a single rank per category — no separate
GUJCET-vs-JEE rows. Pharmacy is not GUJCET-based at all (GUJCET is a PCM
engineering test); ACPC admits on its own merit list and does not publish the
formula. `rank_basis` states which applies per row.

## Categories

`category_raw` is what ACPC prints; `category` is the canonical rollup:

| raw | canonical |
|---|---|
| `OP` / `OPEN` | GEN |
| `SEBC` | OBC-NCL (Gujarat's OBC label) |
| `SC`, `ST`, `EWS` | same |
| `TFWS` (tuition-fee waiver) | OTHER + `sub_pool='TFWS'` |
| `ESM` (ex-servicemen) | OTHER + `sub_pool='ESM'` |

TFWS and ESM are **horizontal** pools — properties of the seat, not the
candidate's social category.

```sql
-- clean base-category aggregate
WHERE sub_pool = ''
```

642 of 2,487 rows are `OTHER`, so they are not ignorable.

## Institute types

All types ship; government scope is a query, not a filter baked into the data:

```sql
WHERE college_type IN ('Govt', 'Govt-Aided', 'State-Univ-Dept')   -- 696 rows / 34 institutes
```

`college_type` comes from ACPC's own `INST_TYPE` column — **stated in the
source**, not guessed from the name. `institute_type_raw` keeps the finer
taxonomy: GOV, GIA, SFI, UNI-SFI, COE, PPP, Auto.

Two edge cases worth knowing:

- **PPP is not govt.** One college (GIDC Navsari) is public-private-partnership
  — GIDC land, privately run, fills at private-level cutoffs. → `Private/SF`.
- **Auto is govt.** One institute (IITRAM) is state-legislature-established and
  fully state-funded. → `State-Univ-Dept`.

## An absent category means no admission

Rows exist only where ACPC recorded a last-admitted candidate. `VAC` / `------`
/ `******` cells produce no row — so a college+course with no SC row simply had
no SC admission that year. Don't read absence as missing data.

## Home-State quota only

The source PDFs also carry JEE-only All-India-quota columns; those are
deliberately excluded. See `quota`.

## Reproducibility

The parsed CSVs, the clean Parquet, and both official ACPC PDFs live under
`gs://avantifellows-external-data/gujcet/`. The parser is
`state_cet/scrape/scripts/state_GJ.py` in
[`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2).
