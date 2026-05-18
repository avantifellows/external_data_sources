"""
Socio-economic profile of India's engineering graduate pool (CY2025).

Two questions:
  1. Income distribution: what % of engineering grads are from low-income households?
     Proxy: MPCE quintile (Monthly Per Capita Consumer Expenditure = hce_tot / hh_size).
     "Low income" = bottom 20% (Q1) of national MPCE distribution.

  2. First-generation learners: what % of engineering grads have a household head
     with below-graduate education (i.e., parents likely didn't graduate)?
     Caveat: this is a proxy. Engineers who live independently as the head of
     their own household are excluded (we can't observe parental education).

Definitions:
  Engineering grad   = tedu_lvl == '03' (technical degree, engineering/tech)
  MPCE              = hce_tot / hh_size (rupees/month per person)
  First-gen-eligible = engineering grad who is NOT the household head AND NOT the
                       head's spouse (i.e., they're a child/sibling/relative of the head)
                       Sub-case: head has gedu_lvl < 12 AND tedu_lvl == '01'
                                 → "first-gen" yes
"""

import csv, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHHV1 = ROOT / 'clean' / 'calendar_2025' / 'chhv1.csv'
CPERV1 = ROOT / 'clean' / 'calendar_2025' / 'cperv1.csv'

# Household key columns: stable across chhv1 and cperv1 in CY2025
HH_KEY_COLS = ('qtr', 'month', 'visit', 'sec', 'st', 'dc', 'mfsu', 'sss', 'ssu')


def hh_key(row):
    return tuple(row[c] for c in HH_KEY_COLS)


def weighted_quantile(values_weights, q):
    """Weighted quantile (q in [0,1])."""
    s = sorted(values_weights)
    total = sum(w for _, w in s)
    target = total * q
    cum = 0.0
    for v, w in s:
        cum += w
        if cum >= target:
            return v
    return s[-1][0]


def main():
    # === Step 1: load chhv1 → dict keyed by hh_key with hce_tot, hh_size ===
    print('Loading chhv1...')
    hh = {}
    with CHHV1.open() as f:
        for row in csv.DictReader(f):
            try:
                hce  = int(row.get('hce_tot') or '0')
                size = int(row.get('hh_size') or '0')
                w    = int(row['mult']) / 100
            except (ValueError, KeyError):
                continue
            if size == 0:
                continue
            hh[hh_key(row)] = {
                'hce_tot': hce,
                'hh_size': size,
                'mpce': hce / size,
                'weight': w,
            }
    print(f'  {len(hh):,} households loaded')

    # === Step 2: pass over cperv1 to find the head's education per household ===
    print('Pass 1 over cperv1: head-of-household education lookup...')
    head_edu = {}
    with CPERV1.open() as f:
        for row in csv.DictReader(f):
            if row.get('rel') != '1':  # rel=1 → self, i.e., head of household
                continue
            head_edu[hh_key(row)] = {
                'gedu_lvl': row.get('gedu_lvl', ''),
                'tedu_lvl': row.get('tedu_lvl', ''),
                'age': row.get('age', ''),
                'sex': row.get('sex', ''),
            }
    print(f'  {len(head_edu):,} heads found')

    # === Step 3: compute MPCE quintile thresholds across ALL persons ===
    print('Computing national MPCE quintiles (person-weighted)...')
    all_mpce = []
    with CPERV1.open() as f:
        for row in csv.DictReader(f):
            try:
                w = int(row['mult']) / 100
            except (ValueError, KeyError):
                continue
            h = hh.get(hh_key(row))
            if h is None:
                continue
            all_mpce.append((h['mpce'], w))

    q20 = weighted_quantile(all_mpce, 0.20)
    q40 = weighted_quantile(all_mpce, 0.40)
    q60 = weighted_quantile(all_mpce, 0.60)
    q80 = weighted_quantile(all_mpce, 0.80)
    print(f'  National MPCE quintile thresholds (₹/month/person, weighted):')
    print(f'    Q1 ≤ ₹{q20:>6,.0f}    Q2 ≤ ₹{q40:>6,.0f}    Q3 ≤ ₹{q60:>6,.0f}    Q4 ≤ ₹{q80:>6,.0f}    Q5 > ₹{q80:>6,.0f}')

    def quintile(mpce):
        if mpce <= q20: return 'Q1 (poorest)'
        if mpce <= q40: return 'Q2'
        if mpce <= q60: return 'Q3'
        if mpce <= q80: return 'Q4'
        return 'Q5 (richest)'

    # === Step 4: profile engineering grads ===
    print('\nPass 2 over cperv1: profile engineering grads...')
    quintile_pop = collections.Counter()      # weighted
    quintile_n = collections.Counter()        # raw
    n_engg_total = 0; w_engg_total = 0.0
    n_no_hh = 0
    n_engg_is_head = 0; w_engg_is_head = 0.0
    n_engg_parent = 0; w_engg_parent = 0.0   # has a head other than self
    fg_buckets = collections.Counter()         # weighted population in each bucket
    fg_n = collections.Counter()               # raw counts

    # also break down by age band for richer story
    age_quintile_pop = collections.defaultdict(lambda: collections.Counter())
    age_fg_pop = collections.defaultdict(lambda: collections.Counter())
    age_fg_n = collections.defaultdict(lambda: collections.Counter())

    def age_band(a):
        if 25 <= a <= 29: return '25-29'
        if 30 <= a <= 34: return '30-34'
        if 35 <= a <= 39: return '35-39'
        if 20 <= a <= 24: return '20-24'
        return None

    def first_gen_class(rel, head):
        """Returns: 'self_is_head', 'no_head_record', 'first_gen', 'parent_grad', 'parent_diploma',
        depending on head education."""
        if rel == '1':
            return 'engg_is_head'
        if head is None:
            return 'no_head_record'
        head_g = head['gedu_lvl']
        head_t = head['tedu_lvl']
        # If head has a graduate degree (general or technical at degree level)
        if head_g == '12' or head_g == '13':
            return 'parent_graduate'
        if head_t in {'02','03','04','05','06','12','13','14','15','16'}:
            # head has a technical degree (engineering or other)
            return 'parent_graduate'
        # Head has below-grad general education AND no technical degree:
        if head_g == '11' or head_t in {'07','08','09','10','11'}:
            return 'parent_diploma'
        return 'first_gen'

    with CPERV1.open() as f:
        for row in csv.DictReader(f):
            if row.get('tedu_lvl') != '03':
                continue
            try:
                w = int(row['mult']) / 100
                age = int(row.get('age') or '0')
            except (ValueError, KeyError):
                continue
            n_engg_total += 1; w_engg_total += w
            k = hh_key(row)
            h = hh.get(k)
            if h is None:
                n_no_hh += 1
                continue
            mpce = h['mpce']
            qb = quintile(mpce)
            quintile_pop[qb] += w
            quintile_n[qb] += 1
            band = age_band(age)
            if band:
                age_quintile_pop[band][qb] += w

            # First-gen analysis
            head = head_edu.get(k)
            cls = first_gen_class(row.get('rel', ''), head)
            fg_buckets[cls] += w
            fg_n[cls] += 1
            if band:
                age_fg_pop[band][cls] += w
                age_fg_n[band][cls] += 1

    # === Step 5: print results ===
    print(f'\nTotal engineering grads in CY2025: weighted={w_engg_total:,.0f} (raw n={n_engg_total:,})')
    print(f'  Households joinable: {n_engg_total - n_no_hh:,} of {n_engg_total:,} ({(n_engg_total-n_no_hh)/n_engg_total*100:.1f}%)')

    # Income distribution
    print('\n' + '=' * 80)
    print('INCOME PROFILE (MPCE quintile of engineering grads vs national)')
    print('=' * 80)
    print(f'{"Quintile":<14} {"Weighted Pop":>14} {"% of engg":>11} {"raw n":>8}    (national: 20%)')
    print('-' * 80)
    total = sum(quintile_pop.values())
    for qb in ['Q1 (poorest)', 'Q2', 'Q3', 'Q4', 'Q5 (richest)']:
        pop = quintile_pop[qb]
        n = quintile_n[qb]
        pct = pop / total * 100
        bar = '█' * int(pct / 2)
        print(f'{qb:<14} {pop:>14,.0f} {pct:>10.1f}% {n:>8,}   {bar}')

    # First-gen analysis
    print('\n' + '=' * 80)
    print('FIRST-GENERATION LEARNER PROFILE (head-of-household education)')
    print('=' * 80)
    total_fg = sum(fg_buckets.values())
    print(f'{"Class":<32} {"Weighted":>13} {"%":>6} {"raw n":>8}')
    print('-' * 70)
    labels = {
        'engg_is_head':     'Engineer is the household head',
        'no_head_record':   'No head record found (data error)',
        'first_gen':        'First-gen: head < graduate, no diploma',
        'parent_diploma':   'Head has diploma/cert (below grad)',
        'parent_graduate':  'Head has graduate or higher degree',
    }
    for k, lbl in labels.items():
        pop = fg_buckets[k]
        n = fg_n[k]
        pct = pop/total_fg*100 if total_fg else 0
        print(f'  {lbl:<32} {pop:>13,.0f} {pct:>5.1f}% {n:>8,}')

    # Among engineers living with parents (excludes self-headed):
    co_resident_total = sum(fg_buckets[k] for k in ('first_gen', 'parent_diploma', 'parent_graduate'))
    if co_resident_total:
        print(f'\nAmong engineers living with parents (n={sum(fg_n[k] for k in ("first_gen","parent_diploma","parent_graduate")):,} weighted={co_resident_total:,.0f}):')
        for k, lbl in [('first_gen','First-gen (head < grad, no diploma)'),
                       ('parent_diploma','Parent has diploma'),
                       ('parent_graduate','Parent has graduate degree')]:
            print(f'  {lbl:<40} {fg_buckets[k]/co_resident_total*100:>5.1f}%  (weighted {fg_buckets[k]:,.0f})')

    # Age-band cross-tab
    print('\n' + '=' * 80)
    print('Income & first-gen, by age band of engineering grad')
    print('=' * 80)
    for band in ['20-24', '25-29', '30-34', '35-39']:
        if not age_quintile_pop[band]:
            continue
        total_age = sum(age_quintile_pop[band].values())
        print(f'\nAge {band}: weighted population = {total_age:,.0f}')
        print(f'  Income (MPCE quintile):')
        for qb in ['Q1 (poorest)', 'Q2', 'Q3', 'Q4', 'Q5 (richest)']:
            p = age_quintile_pop[band][qb]
            print(f'    {qb:<14}  {p/total_age*100:>5.1f}%')
        print(f'  First-gen status:')
        total_fg_age = sum(age_fg_pop[band].values())
        for k, lbl in labels.items():
            p = age_fg_pop[band][k]
            n = age_fg_n[band][k]
            if p == 0: continue
            print(f'    {lbl:<32}  {p/total_fg_age*100:>5.1f}%  (n={n:,})')


if __name__ == '__main__':
    main()
