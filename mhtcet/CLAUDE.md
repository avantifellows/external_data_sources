# CLAUDE.md — mhtcet/

Guidance for Claude Code when working inside the `mhtcet/` source folder.
See the [top-level CLAUDE.md](../CLAUDE.md) for cross-source conventions.

## What this folder is

An ingestion pipeline for Maharashtra CAP state-quota admission cutoffs across
four streams. Source data is the State CET Cell's official CAP cutoff PDFs,
parsed by `state_MH.py` / `state_MH_arch.py` in the
[`avantifellows/futures-v2`](https://github.com/avantifellows/futures-v2) repo
and deposited into `mhtcet/raw/` as one CSV per stream.

## Neutral-fact principle

This table carries what the CET Cell publishes plus derived classification:

| Stays in `mhtcet/` (neutral fact) | Stays in downstream enrichment |
|---|---|
| college_code, college_name, branch_code, branch_name | canonical college_id, NIRF rank |
| category_raw, quota, opening/closing_rank | salary_tier, cutoff trends |
| num_rank_observations, last_round_with_max | cross-year comparisons |
| year, round, state, cet_name, stream, rank_basis | |
| college_type (derived from the PDF's Status field) | |
| category / gender / sub_pool (decoded from category_raw) | |

`college_type` is derived from the Status line the CET Cell prints for each
institute, not from an external list. `category`, `gender` and `sub_pool` are
decoded from `category_raw` using the legend printed on every cutoff page —
`category_raw` is always retained so the decoding is auditable and reversible.

## Reservation taxonomy — the load-bearing bit

Codes read as `[G|L] + vertical + [H|O|S]`, per the PDF legend:
`G = General, L = Ladies, H = Home University, O = Other than Home University,
S = State Level, AI = All India Seat`.

Three rules that have each already caused a real bug:

1. **`G` is gender-NEUTRAL, not male.** Female reservation in Maharashtra is
   horizontal — `L*` seats are additional access for women, not their only
   access. `gender` may only be `'All'` or `'Girls'`; `build_clean.py` fails the
   build if `'Boys'` ever appears, because that means the upstream decoder
   regressed. Note `state_MH_arch.py` keeps its **own copy** of the decoder
   (`normalise_seat_type`), so decoder fixes must be applied in both files —
   futures-v2 has a test asserting the two agree.
2. **PWD / DEF / TFWS / ORPHAN / minority are horizontal flags**, recorded in
   `sub_pool` over a decoded base `category`. Never fold them into the base
   category: a `PWDROBC` seat is an OBC seat with a disability flag. Any
   base-category aggregate must filter `sub_pool = ''`.
3. **`quota` is a domicile pair**, not a category — `Home → Other` etc. The same
   bucket closes at very different ranks across pools.

## Grain

`(stream, college_code, branch_code, quota, category_raw, college_type, year)`

`college_type` is in the grain deliberately: a few institutes genuinely run two
funding pools under one code (03016 Bombay College of Pharmacy runs both
Government-Aided and Un-Aided seats). Dropping it from the key would merge two
real, separately-funded seat pools into one row.

`category_raw` is in the grain rather than `category`, because `category` is a
lossy 5-bucket rollup and is deliberately non-unique.

## Scope

All college types ship. Government scope is a **query**
(`college_type IN ('Govt','Govt-Aided','State-Univ-Dept')`), not a pipeline
decision — same choice as `kcet/`. Do not add a govt-only filter here; the
predictor and other consumers need private colleges too.

## Refresh

`build_clean.py` hard-asserts per-stream row counts and two named anchors
(VJTI CSE opening 103 / closing 119; college 03016 retaining both funding
pools). These are designed to fail on a refresh. When they do:

1. Confirm the change is real — CET Cell republished, or an upstream parser fix.
2. Update the expected values **in the same commit** as the cause.
3. Never relax an assertion to make a build pass.

Rank ceiling context for sanity checks: MHT-CET 2025 engineering had ~4.5 lakh
candidates, so a few hundred thousand is an ordinary tail rank; past ~6 lakh is
not credible.
