"""
Better approach: estimate "household income excl. grad" from PLFS earnings data
directly, instead of using HCE as proxy.

For each engineering grad age 20-24:
  hh_income_excl_grad = sum of (ern_reg + ern_self) for ALL persons in the
                        household, EXCEPT the grad themselves
  Compare to ₹40k/month cutoff.

Caveats:
  - PLFS earnings cover only employment income (wage + self-employment).
    Misses rental, dividend, pension, govt transfers, remittances.
  - For households where the head is retired or non-working, captured income
    will be 0 even if there's pension/rent income.
  - More accurate than HCE for active-earning households; less accurate for
    households with non-employment income.

Output: comparison of three methods —
  (A) HCE-based proxy (hce_tot - grad_earnings, floored at 0)
  (B) Earnings-based (sum of ern_reg + ern_self of non-grad members)
  (C) HCE-based but with an income-adjustment factor (HCE × 1.4 ≈ income)
"""

import csv, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHHV1 = ROOT / 'clean' / 'calendar_2025' / 'chhv1.csv'
CPERV1 = ROOT / 'clean' / 'calendar_2025' / 'cperv1.csv'
HH_KEY_COLS = ('qtr', 'month', 'visit', 'sec', 'st', 'dc', 'mfsu', 'sss', 'ssu')
CUTOFF = 40_000


def hh_key(row):
    return tuple(row[c] for c in HH_KEY_COLS)


def safe_int(x):
    try: return int(x)
    except (ValueError, TypeError): return 0


def main():
    print('Loading chhv1...')
    hh = {}
    with CHHV1.open() as f:
        for row in csv.DictReader(f):
            hce = safe_int(row.get('hce_tot'))
            size = safe_int(row.get('hh_size'))
            if size == 0: continue
            hh[hh_key(row)] = {'hce_tot': hce, 'hh_size': size}
    print(f'  {len(hh):,} households loaded')

    # Pass 1: build per-household sum of all members' earnings + identify grads
    print('Pass 1 over cperv1: aggregate earnings per household + tag grads...')
    hh_total_earnings = collections.defaultdict(int)
    hh_member_count = collections.Counter()
    grad_records = []   # (hh_key, person_serial, age, sex, ern_reg, ern_self, weight, pas)

    with CPERV1.open() as f:
        for row in csv.DictReader(f):
            k = hh_key(row)
            ern_reg = max(0, safe_int(row.get('ern_reg')))
            ern_self = max(0, safe_int(row.get('ern_self')))
            hh_total_earnings[k] += ern_reg + ern_self
            hh_member_count[k] += 1
            if row.get('tedu_lvl') != '03': continue
            try:
                age = int(row.get('age') or '0')
            except ValueError: continue
            if not (20 <= age <= 24): continue
            try:
                w = int(row['mult']) / 100
            except (ValueError, KeyError): continue
            grad_records.append({
                'k': k,
                'srl': row.get('srl'),
                'age': age,
                'sex': row.get('sex'),
                'ern_reg': ern_reg,
                'ern_self': ern_self,
                'weight': w,
                'pas': row.get('pas'),
                'rel': row.get('rel'),
            })
    print(f'  {len(grad_records):,} engineering grads age 20-24 found')

    # For each grad, compute three estimates of household income excl. grad
    rows = []
    for g in grad_records:
        h = hh.get(g['k'])
        if h is None: continue
        hce_total = h['hce_tot']
        grad_earnings = g['ern_reg'] + g['ern_self']

        # Method A: HCE-based
        method_a = max(0, hce_total - grad_earnings)

        # Method B: Earnings-based (subtract grad's earnings from sum of all members)
        method_b = max(0, hh_total_earnings[g['k']] - grad_earnings)

        # Method C: HCE-based with income-adjustment factor (typical savings rate)
        # For low-income households, savings rate is near 0 → HCE ≈ income.
        # For middle-income, savings ≈ 20% → income ≈ HCE / 0.8 = HCE × 1.25.
        # We'll use a simple 1.4× multiplier as a midpoint; this is illustrative.
        method_c = max(0, int(hce_total * 1.4) - grad_earnings)

        rows.append({
            **g,
            'hce_total': hce_total,
            'grad_earnings': grad_earnings,
            'method_a': method_a,
            'method_b': method_b,
            'method_c': method_c,
            'hh_member_count': hh_member_count[g['k']],
        })

    total_w = sum(r['weight'] for r in rows)
    total_n = len(rows)
    print(f'\n  Total joinable: {total_n:,} (raw)   {total_w:,.0f} (weighted)')

    # Compare three methods at user's ₹40k cutoff
    print('\n' + '=' * 90)
    print(f'Engineering grads age 20-24 below ₹{CUTOFF:,}/month, by methodology:')
    print('=' * 90)

    methods = [
        ('A. HCE-based: hce_tot - grad_earnings',          'method_a'),
        ('B. Earnings-based: Σ(ern_reg+ern_self) of non-grad members', 'method_b'),
        ('C. HCE × 1.4 (savings-adjustment) - grad_earnings','method_c'),
    ]
    for label, key in methods:
        below_w = sum(r['weight'] for r in rows if r[key] < CUTOFF)
        below_n = sum(1 for r in rows if r[key] < CUTOFF)
        zero_w = sum(r['weight'] for r in rows if r[key] == 0)
        print(f'\n  {label}')
        print(f'    Below ₹{CUTOFF:,}/month: {below_w:>11,.0f} weighted ({below_w/total_w*100:>5.1f}%)   n={below_n:,}')
        print(f'    Of which =₹0:        {zero_w:>11,.0f} weighted ({zero_w/total_w*100:>5.1f}%)')

    # Sensitivity: method B at multiple cutoffs (the most direct income measure)
    print('\n' + '=' * 90)
    print('Method B (earnings-based) — sensitivity to cutoff:')
    print('=' * 90)
    for cutoff in [10000, 20000, 30000, 40000, 50000, 75000, 100000]:
        b = sum(r['weight'] for r in rows if r['method_b'] < cutoff)
        n = sum(1 for r in rows if r['method_b'] < cutoff)
        print(f'  Below ₹{cutoff:>6,}/month: {b:>11,.0f} weighted ({b/total_w*100:>5.1f}%)   n={n:,}')

    # Critical: how many households have ZERO captured earnings?
    zero_earnings = [r for r in rows if r['method_b'] == 0]
    z_w = sum(r['weight'] for r in zero_earnings)
    print(f'\n  Households with ZERO captured non-grad earnings: {len(zero_earnings):,} (raw)  '
          f'{z_w:,.0f} weighted ({z_w/total_w*100:.1f}%)')
    print(f'  These could be: (i) genuinely no employed members, (ii) family runs informal '
          f'business with un-reported earnings, (iii) survivor on pension/transfers/rent.')

    # By gender, using method B
    print('\nBy gender (method B):')
    for sex_code, sex_label in [('1', 'Men  '), ('2', 'Women')]:
        cohort = [r for r in rows if r['sex'] == sex_code]
        cw = sum(r['weight'] for r in cohort)
        below = [r for r in cohort if r['method_b'] < CUTOFF]
        bw = sum(r['weight'] for r in below)
        if cw == 0: continue
        print(f'  {sex_label}: total {cw:>10,.0f} (n={len(cohort)})  '
              f'< ₹40k: {bw:>9,.0f} (n={len(below)})  '
              f'share: {bw/cw*100:.1f}%')

    # Distribution of method B (earnings-based)
    print('\n' + '=' * 90)
    print('Distribution of HH non-grad earnings (Method B), engineering grads 20-24:')
    print('=' * 90)
    bands = [
        ('= ₹0',                   0, 1),
        ('₹1 - ₹9,999',            1, 10000),
        ('₹10,000 - ₹19,999',     10000, 20000),
        ('₹20,000 - ₹29,999',     20000, 30000),
        ('₹30,000 - ₹39,999',     30000, 40000),
        ('₹40,000 - ₹59,999',     40000, 60000),
        ('₹60,000 - ₹99,999',     60000, 100000),
        ('₹100,000+',            100000, float('inf')),
    ]
    print(f'{"Band":<22} {"weighted":>13} {"%":>6} {"raw n":>9}')
    print('-' * 60)
    for label, lo, hi in bands:
        w = sum(r['weight'] for r in rows if lo <= r['method_b'] < hi)
        n = sum(1 for r in rows if lo <= r['method_b'] < hi)
        print(f'  {label:<20} {w:>13,.0f} {w/total_w*100:>5.1f}% {n:>9,}')


if __name__ == '__main__':
    main()
