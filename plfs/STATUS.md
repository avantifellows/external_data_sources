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

§3.5.1.7, verbatim. All fourteen are present in all releases loaded here.

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

**There is no code 42.** Casual labour is 41 and 51. A `pas IN ('41','42','51')` test appears in
several places in our own history; it is harmless and it is the tell that a list was written from
memory rather than from this table.

The codes **partition** the population — every person carries exactly one — which is what makes a
status breakdown sum to 100% and a residual row a genuine check rather than a catch-all.

## Conditions of employment cover casual work too

§3.5.1.15: `job_pas`, `leave_pas` and `ssec_pas` are recorded "for those with status codes **31, 41 or
51**" and pertain to the principal status. Casual workers are in scope, and the items are 100%
populated for them — so any formality measure conditioned on `pas='31'` excludes casual work by
construction, not for want of data. Codes and measured levels are in `EARNINGS.md`.
