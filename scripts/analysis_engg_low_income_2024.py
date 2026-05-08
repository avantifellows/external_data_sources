"""
Estimate the number of engineering graduates age 20-24 from households with
non-graduate income < ₹40,000/month (i.e., ₹4 lakh/annum).

Approach:
  - Engineering grad   = tedu_lvl == '03'
  - Age band           = 20-24
  - Household income proxy = hce_tot from chhv1 (monthly consumer expenditure)
  - "Excluding graduate's salary" = hce_tot - ern_reg(grad) - ern_self(grad)
    Rationale: at low-income levels savings rate is near zero, so consumer
    expenditure ≈ household income. Subtracting the grad's own earnings gives
    the income that would remain absent the grad's contribution.

Caveats reported alongside:
  - HCE underestimates true income at higher quintiles (savings effect).
  - The 'subtract grad's earnings' assumes the grad's earnings flow into HCE.
    If the grad lives apart but is reported in the household, we'd over-subtract.
"""

import csv, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHHV1 = ROOT / 'clean' / 'calendar_2025' / 'chhv1.csv'
CPERV1 = ROOT / 'clean' / 'calendar_2025' / 'cperv1.csv'

HH_KEY_COLS = ('qtr', 'month', 'visit', 'sec', 'st', 'dc', 'mfsu', 'sss', 'ssu')
CUTOFF = 40_000  # ₹/month, household earnings excl. graduate's salary


def hh_key(row):
    return tuple(row[c] for c in HH_KEY_COLS)


def safe_int(x):
    try:
        return int(x)
    except (ValueError, TypeError):
        return 0


def main():
    print('Loading chhv1...')
    hh = {}
    with CHHV1.open() as f:
        for row in csv.DictReader(f):
            hce = safe_int(row.get('hce_tot'))
            size = safe_int(row.get('hh_size'))
            if size == 0:
                continue
            hh[hh_key(row)] = {'hce_tot': hce, 'hh_size': size}
    print(f'  {len(hh):,} households loaded')

    # Filter to age 20-24 engineering grads
    print('\nProfiling engineering grads age 20-24...')
    rows_kept = []
    earner_count = 0
    nonearner_count = 0
    for_cutoffs = []

    with CPERV1.open() as f:
        for row in csv.DictReader(f):
            if row.get('tedu_lvl') != '03':
                continue
            try:
                age = int(row.get('age') or '0')
            except ValueError:
                continue
            if not (20 <= age <= 24):
                continue
            try:
                w = int(row['mult']) / 100
            except (ValueError, KeyError):
                continue
            h = hh.get(hh_key(row))
            if h is None:
                continue
            ern_reg = max(0, safe_int(row.get('ern_reg')))
            ern_self = max(0, safe_int(row.get('ern_self')))
            grad_earnings = ern_reg + ern_self
            hce_total = h['hce_tot']
            # Floor at 0: if grad's earnings exceed HCE, the household had ~zero
            # income excluding grad (grad is effectively the primary earner).
            hce_excl_grad = max(0, hce_total - grad_earnings)
            if grad_earnings > 0:
                earner_count += 1
            else:
                nonearner_count += 1
            rows_kept.append({
                'age': age, 'sex': row.get('sex'), 'pas': row.get('pas'),
                'rel': row.get('rel'),
                'hh_size': h['hh_size'],
                'hce_total': hce_total,
                'grad_earnings': grad_earnings,
                'hce_excl_grad': hce_excl_grad,
                'weight': w,
            })

    total_n = len(rows_kept)
    total_w = sum(r['weight'] for r in rows_kept)
    print(f'  Total rows: {total_n:,}  Weighted population: {total_w:,.0f}')
    print(f'  With own earnings >0: {earner_count:,}  Without earnings: {nonearner_count:,}')
    earners_w = sum(r['weight'] for r in rows_kept if r['grad_earnings'] > 0)
    print(f'  Weighted: earners {earners_w:,.0f} ({earners_w/total_w*100:.1f}%)  '
          f'non-earners {total_w - earners_w:,.0f} ({(total_w-earners_w)/total_w*100:.1f}%)')

    # Headline answer
    print('\n' + '=' * 80)
    print(f'ENGINEERING GRADS AGE 20-24 BY HOUSEHOLD INCOME (excl. grad earnings)')
    print('=' * 80)
    bands = [
        ('= ₹0 (grad earnings ≥ HCE)', 0, 1),
        ('₹1 - ₹9,999/month',          1, 10000),
        ('₹10,000 - ₹19,999',          10000, 20000),
        ('₹20,000 - ₹29,999',          20000, 30000),
        ('₹30,000 - ₹39,999',          30000, 40000),
        ('₹40,000 - ₹59,999',          40000, 60000),
        ('₹60,000 - ₹99,999',          60000, 100000),
        ('₹100,000+',                  100000, float('inf')),
    ]
    print(f'{"HCE excl. grad":<24} {"weighted":>13} {"%":>6} {"raw n":>8} {"cum %":>7}')
    print('-' * 65)
    cum_w = 0.0
    for label, lo, hi in bands:
        w = sum(r['weight'] for r in rows_kept if lo <= r['hce_excl_grad'] < hi)
        n = sum(1 for r in rows_kept if lo <= r['hce_excl_grad'] < hi)
        cum_w += w
        print(f'  {label:<22} {w:>13,.0f} {w/total_w*100:>5.1f}% {n:>8,} {cum_w/total_w*100:>6.1f}%')

    # Headline numbers
    print('\n' + '=' * 80)
    print('HEADLINE — engineering grads age 20-24, by ₹40k household-income cutoff')
    print('=' * 80)

    below = [r for r in rows_kept if r['hce_excl_grad'] < CUTOFF]
    below_n = len(below)
    below_w = sum(r['weight'] for r in below)
    print(f'\n  Total engg grads age 20-24:       {total_n:>6,} (raw)   {total_w:>11,.0f} (weighted)')
    print(f'  Of which from HH with hce_tot - grad_earnings < ₹{CUTOFF:,}:')
    print(f'                                      {below_n:>6,} (raw)   {below_w:>11,.0f} (weighted)')
    print(f'  Share: {below_w/total_w*100:.1f}% of all engg grads age 20-24')

    # Sensitivity: try a few cutoffs
    print('\nSensitivity to cutoff:')
    for cutoff in [25000, 30000, 40000, 50000, 60000, 80000, 100000]:
        b = sum(r['weight'] for r in rows_kept if r['hce_excl_grad'] < cutoff)
        n = sum(1 for r in rows_kept if r['hce_excl_grad'] < cutoff)
        print(f'  Below ₹{cutoff:>6,}/month: {b:>11,.0f} weighted ({b/total_w*100:>5.1f}%)   n={n:,}')

    # Same with HCE-only (no subtraction) for comparison
    print('\nFor reference — using hce_tot directly (no subtraction of grad\'s salary):')
    for cutoff in [40000]:
        b = sum(r['weight'] for r in rows_kept if r['hce_total'] < cutoff)
        n = sum(1 for r in rows_kept if r['hce_total'] < cutoff)
        print(f'  Below ₹{cutoff:>6,}/month: {b:>11,.0f} weighted ({b/total_w*100:>5.1f}%)   n={n:,}')

    # Sub-split: what fraction of those below ₹40k have grad earnings >0?
    below_earners = [r for r in below if r['grad_earnings'] > 0]
    bw = sum(r['weight'] for r in below_earners)
    print(f'\n  Of the {below_w:,.0f} below-₹40k cohort: {bw:,.0f} ({bw/below_w*100:.0f}%) have grad earnings > 0')
    print(f'    (i.e., {below_w - bw:,.0f} are non-earners, parental income alone < ₹40k)')

    # By gender
    print('\nBy gender:')
    for sex_code, sex_label in [('1', 'Men'), ('2', 'Women')]:
        cohort = [r for r in rows_kept if r['sex'] == sex_code]
        cw = sum(r['weight'] for r in cohort)
        cn = len(cohort)
        below_cohort = [r for r in cohort if r['hce_excl_grad'] < CUTOFF]
        bcw = sum(r['weight'] for r in below_cohort)
        bcn = len(below_cohort)
        if cw == 0: continue
        print(f'  {sex_label:6s}: total {cw:>10,.0f} (n={cn:,})  '
              f'below ₹40k: {bcw:>9,.0f} (n={bcn:,})  '
              f'share: {bcw/cw*100:.1f}%')


if __name__ == '__main__':
    main()
