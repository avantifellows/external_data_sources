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
| `ern_reg` | "Earnings For Regular Salaried/Wage Activity" (col 9, 8 bytes) | **monthly** | usual status, 365 days |
| `ern_self` | "Earnings For Self Employed" (col 10, 8 bytes) | **monthly** | usual status, 365 days |
| `ern11`–`ern17` | "wage earning for activity 1 on 1st…7th day" (col 9/3.1–3.7, 5 bytes) | **daily** | current weekly status, last 7 days |
| `ern21`–`ern27` | "wage earning for activity 2 on 1st…7th day" (col 9/3.1–3.7, 5 bytes) | **daily** | current weekly status, last 7 days |

Paired with `hr11`–`hr17` and `hr21`–`hr27`, "hours actually worked for activity 1/2 on <n>th day", so
a daily wage can be put on an hourly basis where that is wanted.

`ern_reg` and `ern_self` load as `INT64`. The daily block loads as **`STRING`** and needs
`SAFE_CAST(NULLIF(TRIM(ern1n), '') AS INT64)`.

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
