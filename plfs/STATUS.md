# PLFS activity status — the codes, and the three clocks they run on

Companion to `WEIGHTS.md` and `EARNINGS.md`. Same rule: read the manual, not a summary of it.

Everything below is from `raw/docs/InstructionManual_VolI` unless stated.

## Three reference periods, not one

§1.5.16 — PLFS determines activity status on **three** windows at once, and collects all three:

| basis | window | tie-break | what it answers |
|---|---|---|---|
| **Usual status** | 365 days | major time | what someone mainly did over the year |
| Current weekly status (CWS) | 7 days | priority | what they did last week |
| Current daily status (CDS) | each day of that week | priority | what they did on a given day |

**This is the single most load-bearing distinction in the dataset**, because different columns hang off
different clocks and nothing in the column names says so:

- `pas`, `sas` and everything `_pas`-suffixed (industry, occupation, enterprise type, contract, social
  security, paid leave) are **usual status** — 365 days.
- `ern_reg` and `ern_self` are keyed to **current weekly status** (§3.6 xviii/xix). See `EARNINGS.md`.
- `ern11`–`ern27`, `hr11`–`hr27` are **per day** of the reference week.
- `sts11`–`sts27` would be the daily status codes, and are **empty in every release loaded here**.

So "is this a point-in-time measure?" has different answers per column. The status shown by any
analysis built on `pas`/`sas` is *not* point-in-time — it is the whole preceding year.

## Usual principal vs subsidiary

§1.5.18–19. The **principal** status is the activity taking the major part of the 365 days. A
**subsidiary** status is any *additional* economic activity of **30 days or more**.

PLFS's own published employment figures are on **principal-or-subsidiary (ps+ss)**. Reading `pas`
alone is a narrower question and understates work — most sharply for women, whose principal status is
more often domestic duties while they also do 30+ days of economic activity.

Resolving ps+ss by precedence — principal code where that is work, else subsidiary where *that* is
work, else principal — reproduces the published rural female LFPR for 2021-22 at **36.6%** against
**35.6%** published, and still partitions the population to exactly 100.0%. `pas` alone gives 28.6%.

## The fourteen codes

§3.5.1.7, verbatim — the USUAL activity status vocabulary, which is what `pas` and `sas` carry. All
fourteen are present in all releases loaded here. The current daily/weekly vocabulary is a DIFFERENT
list that reuses some of the same digits — see the note under the table.

| code | meaning | |
|---|---|---|
| 11 | own-account worker | working |
| 12 | employer | working |
| 21 | unpaid helper in a household enterprise | working |
| 31 | regular salaried / wage employee | working |
| 41 | casual labour — public works | working |
| 51 | casual labour — other | working |
| 81 | unemployed: sought or was available for work | in labour force |
| 91 | attended an educational institution | outside |
| 92 | attended to domestic duties only | outside |
| 93 | domestic duties + free collection of goods | outside |
| 94 | rentier, pensioner, remittance recipient | outside |
| 95 | not able to work | outside |
| 97 | others | outside |
| 99 | not applicable (age) | outside |

**Code 42 does not occur in `pas` or `sas`** — but it is a real code elsewhere in the schedule, and
an earlier version of this file said flatly "there is no code 42", which is wrong in general.
§3.6.5 states the difference outright:

> "these codes are the same as the usual activity status codes, except the codes 42, 61, 62, 71, 72,
> 82 and 98 which are not applicable for usual status. Moreover, activity status code 41 in the usual
> status is used for casual wage labour in ALL types of public works, whereas in the current activity
> status, code 41 is for casual wage labour in public works other than MGNREG works and code 42 is
> for casual wage labour in MGNREG works."

So in usual status, 41 covers casual wage labour in **all** public works, MGNREG included, and 51
covers other casual work. `pas IN ('41','51')` is the complete casual filter and it already contains
MGNREG workers. A `pas IN ('41','42','51')` test appears in several places in our own history; it is
harmless — it matches nothing extra rather than widening the population — and it is the tell that a
list was written from memory rather than from this table.

In the daily and weekly block — `sts11`–`sts27` — 41 EXCLUDES MGNREG and 42 carries it. **That block
is populated in eight of the eleven releases loaded here**, and code 42 really is in it, so the
MGNREG split IS available for those eight. Counted on V1, cells across `sts11`–`sts27`:

| release | cells coded 42 | cells coded 41 | `sts11` populated |
|---|---|---|---|
| annual_2018-19 | 3,537 | 2,594 | yes |
| annual_2019-20 | 2,795 | 4,283 | yes |
| annual_2020-21 | 3,669 | 4,422 | yes |
| annual_2021-22 | 4,611 | 4,786 | yes |
| annual_2022-23 | 7,383 | 1,811 | yes |
| annual_2023-24 | 7,304 | 1,778 | yes |
| calendar_2021 | — | — | **no** |
| calendar_2022 | 5,249 | 3,099 | yes |
| calendar_2023 | 7,775 | 1,821 | yes |
| calendar_2024 | — | — | **no** |
| calendar_2025 | — | — | **no** |

An earlier version of this file, and note 17b of `plfs_fact_persons.yaml`, said these columns were
"empty in every release loaded here" and concluded that MGNREG could not be separated at all. Both
were wrong, and the second conclusion followed from the first. Measured, the pattern is that the two
daily blocks are **mutually exclusive across releases**: `sts11`–`sts27` are populated in exactly the
eight releases where `hr11`–`hr27` are empty, and `hr11`–`hr27` are populated in exactly the two
where `sts` is empty. calendar_2021 carries neither.

Two things follow that we have not acted on:

* **MGNREG can be split off casual work for those eight releases**, and only for them. Any such cut
  must name its releases; it cannot span the series.
* **`ern11`–`ern27` (the daily earnings block) is populated in nine releases, not two.** The casual
  daily wage is currently derived only for calendar_2024 and calendar_2025 because days worked are
  taken from `hr11`–`hr27`. Days for the earlier eight would have to come from `sts` instead, which
  is a different derivation and is not written here — the point is that the limit is our method, not
  the data.
* **Hours and earnings do not line up cell by cell**, which is what counting days from hours assumes.
  §3.6.9 records hours for every work status (11–72); §3.6.11 records wage earnings only for 41, 42
  and 51. A usually-casual person's self-employed or regular days therefore carry hours and no wage,
  so days counted from hours over-count casual days. Measured on calendar_2025: 9.5% of casual wage
  earners by weight are affected, and mean days a week is 5.414 from hours against 5.201 from
  earnings. The median daily wage is ₹400 either way — the heaping makes it robust — so published
  medians stand; the days figure is the one that moves. Details in EARNINGS.md.

§3.6.5 does the same thing to unemployment: usual-status 81 covers both seeking and being available
for work, while current status splits it into 81 (sought work) and 82 (available, did not seek).

The codes **partition** the population — every person carries exactly one — which is what makes a
status breakdown sum to 100% and a residual row a genuine check rather than a catch-all.

## Conditions of employment cover casual work too

§3.5.1.15: `job_pas`, `leave_pas` and `ssec_pas` are recorded "for those with status codes **31, 41 or
51**" and pertain to the principal status. Casual workers are in scope, and the items are 100%
populated for them — so any formality measure conditioned on `pas='31'` excludes casual work by
construction, not for want of data. Codes and measured levels are in `EARNINGS.md`.
