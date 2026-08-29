# PLFS Earnings — three bases, and why they must not be averaged together

PLFS records earnings on **three different bases**, on two different reference periods. Which column a
person's earnings sit in is determined by their activity, so any figure that averages across activities
is averaging incommensurable things.

Companion to `WEIGHTS.md`. Same rule applies: read the source, not a summary of it.

## The columns

All four names below are verbatim from the data layout — `raw/docs_calendar_2025/FV_Data_Layout_2025.xlsx`,
sheet `CPERV1`, which maps every column to its schedule position.

| column(s) | layout description | basis | reference period |
|---|---|---|---|
| `ern_reg` | "Earnings For Regular Salaried/Wage Activity" (col 9, 8 bytes) | **preceding calendar month** | keyed to **current weekly** status |
| `ern_self` | "Earnings For Self Employed" (col 10, 8 bytes) | **last 30 days** | keyed to **current weekly** status |
| `ern11`–`ern17` | "wage earning for activity 1 on 1st…7th day" (col 9/3.1–3.7, 5 bytes) | **daily** | current weekly status, last 7 days |
| `ern21`–`ern27` | "wage earning for activity 2 on 1st…7th day" (col 9/3.1–3.7, 5 bytes) | **daily** | current weekly status, last 7 days |

Paired with `hr11`–`hr17` and `hr21`–`hr27`, "hours actually worked for activity 1/2 on <n>th day", so
a daily wage can be put on an hourly basis where that is wanted.

`ern_reg` and `ern_self` load as `INT64`. The daily block loads as **`STRING`** and needs
`SAFE_CAST(NULLIF(TRIM(ern1n), '') AS INT64)`.

## Correction: none of these is a usual-status figure

An earlier version of this table said `ern_reg` and `ern_self` were "monthly, usual status, 365 days".
That is wrong, and it is the same failure mode as the weights error in `WEIGHTS.md` — right magnitudes,
invented mechanism.

`InstructionManual_VolI` 3.6, items (xviii) and (xix), are explicit:

> If a person is classified as a regular salaried/wage employee **in the current weekly status**,
> earnings (received/receivable) **during the preceding calendar month** ... will be recorded.

> If a person is classified as a self-employed person **in the current weekly status**, gross earning
> **during last 30 days** from the self-employment activity ... will be recorded.

So all three earnings blocks hang off a **7-day** classification, while `pas`/`sas` are the **365-day**
usual status. Cross-tabbing earnings against usual status — which is what any analysis on this page
does — crosses two reference periods. That is usually harmless, because the two classifications agree
for most people, and it is exactly why a handful of `pas='31'` rows carry `ern_self` and vice versa.
State it rather than let someone rediscover it.

## Which activity uses which column

Measured on `calendar_2025`, `visit='V1'`, ages 25-29:

| activity (`pas`) | n | `ern_reg` > 0 | `ern_self` > 0 | `ern11` > 0 | `ern17` > 0 |
|---|---|---|---|---|---|
| regular salaried (`31`) | 20,603 | **19,880** | 75 | 34 | 38 |
| self-employed (`11`,`12`) | 17,219 | 59 | **14,108** | 148 | 159 |
| casual wage (`41`,`42`,`51`) | 9,803 | 41 | 122 | **6,152** | **7,470** |

The pattern is complementary, not partial coverage. Regular salaried and casual workers are near
mirror images: the first are paid a monthly salary and the second a daily wage, and PLFS asks each the
question that fits.

**So "casual workers have no earnings data" is wrong.** They have earnings on a different basis. Any
analysis that reports casual earnings as absent has looked in the wrong column.

## The rule

**Never put two bases in one column, and never average across them.**

A monthly salary and a day's wage differ by a factor of roughly 22-26; a business income and a salary
differ in meaning even at the same magnitude. A weighted median over rows drawn from more than one basis
returns a number with no interpretation, and it will look plausible.

If a monthly equivalent for casual work is needed, it is a **derivation with assumptions**, not a
column read:

- sum 7 days across both activities to get a week, then scale to a month — which changes the reference
  period from 365 days to 7, so it is a snapshot of the survey week rather than a usual-status figure;
- it merges activity 1 and activity 2 into one figure, losing the distinction PLFS deliberately keeps;
- weekly earnings of casual workers are volatile by nature, which is why the survey asks per day.

That derived figure deserves its own column with its own name (`monthly_equiv_casual`, say) and a note
saying how it was built. It does not belong in a column whose other rows are usual-status monthly
salaries.

## How the consumers handle it

`../../data-assistant/analysis/plfs/extract_industry_function.sql` resolves a single `earn` column per
activity — `ern_reg` for regular salaried, `ern_self` for self-employed, NULL for casual — so no
downstream aggregate *can* mix them. The mixing is made impossible rather than discouraged, because a
comment is not a constraint.

Casual median earnings are therefore NULL on the India HE dashboard by design, and the page says so
rather than leaving a blank cell to be read as missing data.


## Days and hours, and why casual pay needs three numbers

`sts11`–`sts27`, the daily activity status codes, exist in the layout and are **empty in every release
loaded here**. `hr11`–`hr27` are populated and line up with `ern11`–`ern27` cell by cell — a day with
`hr=0` carries `ern=0`, a day with `hr=8` carries that day's wage — so **days worked is derived from
hours**, counting a day when either activity records positive hours.

Measured on `calendar_2025`, all ages, weighted:

| | |
|---|---|
| casual workers (`pas` in 41, 51) | 9.90 crore |
| with a wage recorded | 87.2% |
| days worked per week | **5.45** |
| hours per day | **7.6** |
| median daily wage | **₹400** |
| median hourly wage | **₹52.7** |

A casual worker's pay is a daily rate **times the days they get**, and both vary. Quoting a monthly
equivalent without the days hides the half that makes the work precarious, and turns a derivation from
a 7-day window into something that reads as a measurement. PLFS publishes the daily rate for this
reason.

Note the medians above are **pooled**. A weighted average of per-cell medians runs higher on this
right-skewed distribution — ₹432 for the same population — so say which one you are quoting.

## Conditions of employment are collected for casual workers

`InstructionManual_VolI` 3.5.1.15: columns 11–13 — `job_pas` (written contract), `leave_pas` (paid
leave), `ssec_pas` (social security) — are recorded "for those with status codes **31, 41 or 51**", and
they pertain to the principal status. Casual workers are in scope and the items are **100% populated**
for them.

So a formality measure conditioned on `pas='31'` excludes casual work **by construction**, not for want
of data. Measured, `calendar_2025`, all ages: **0.00%** of casual workers hold a written contract and
**0.32%** have any social security.

Codes: `job_pas` 1 = none, 2 = ≤1 year, 3 = 1–3 years, 4 = >3 years. `ssec_pas` 1–7 = eligible for some
combination of PF/pension, gratuity, health/maternity; 8 = none; 9 = not known — so a formality test
reads `NOT IN ('8','9')`.
