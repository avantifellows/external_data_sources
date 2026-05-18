"""
Education × employability × wages, by age band.
Source: clean/calendar_2025/cperv1.csv (CY2025).

Education buckets (mutually exclusive, applied in priority order):
  E. Engineering grad        (tedu_lvl in {03, 13})
  M. Medical grad            (tedu_lvl in {04, 14})
  T. Other tech/prof grad    (tedu_lvl in {02, 05, 06, 12, 15, 16})
  D. Diploma / polytechnic   (gedu_lvl = 11   OR  tedu_lvl in {07-11} AND gedu_lvl<12)
  P. Postgraduate (general)  (gedu_lvl = 13 AND tedu_lvl = 01)
  G. Graduate (general)      (gedu_lvl = 12 AND tedu_lvl = 01)
  H. Higher secondary        (gedu_lvl = 10)
  S. Secondary               (gedu_lvl = 08)
  B. Below secondary         (everything else)

Cells:
  Worker Population Ratio   = wt(employed in PAS) / wt(total)
  Regular salaried share    = wt(PAS == 31) / wt(total)
  Median wage (regular)     = weighted median of ern_reg among PAS == 31 AND ern_reg > 0
  P25 / P75 wage            = weighted percentiles of ern_reg

Weight: CY2025 rule, weight = mult / 100.
"""

import csv, collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "clean" / "calendar_2025" / "cperv1.csv"

EMPLOYED_CODES = {'11','12','21','31','41','42','51'}

ENG_TEDU = {'03', '13'}
MED_TEDU = {'04', '14'}
OTHER_TECH_TEDU = {'02', '05', '06', '12', '15', '16'}
TECH_DIPLOMA_TEDU = {'07', '08', '09', '10', '11'}

BUCKET_ORDER = ['E', 'M', 'T', 'P', 'G', 'D', 'H', 'S', 'B']
BUCKET_LABEL = {
    'E': 'Engineering grad',
    'M': 'Medical grad',
    'T': 'Other tech/prof grad',
    'P': 'Postgraduate (general)',
    'G': 'Graduate (general)',
    'D': 'Diploma / polytechnic',
    'H': 'Higher Secondary',
    'S': 'Secondary',
    'B': 'Below Secondary',
}


def bucket_of(gedu: str, tedu: str) -> str:
    """Apply priority order: catch professional/technical first, then general levels."""
    if tedu in ENG_TEDU:        return 'E'
    if tedu in MED_TEDU:        return 'M'
    if tedu in OTHER_TECH_TEDU: return 'T'
    # Diploma / polytechnic before general grad/PG
    if gedu == '11':            return 'D'
    if tedu in TECH_DIPLOMA_TEDU and gedu not in {'12', '13'}: return 'D'
    if gedu == '13':            return 'P'
    if gedu == '12':            return 'G'
    if gedu == '10':            return 'H'
    if gedu == '08':            return 'S'
    return 'B'


def age_band(a: int) -> str:
    if 25 <= a <= 29: return '25-29'
    if 35 <= a <= 39: return '35-39'
    return ''


def weighted_percentiles(values_weights, percentiles=(25, 50, 75, 90)):
    """Return weighted percentiles. values_weights = [(value, weight), ...]."""
    if not values_weights:
        return {p: None for p in percentiles}
    s = sorted(values_weights)
    total_w = sum(w for _, w in s)
    out = {}
    cum = 0.0
    targets = {p: total_w * p / 100 for p in percentiles}
    remaining = dict(targets)
    for v, w in s:
        cum += w
        for p in list(remaining):
            if cum >= remaining[p]:
                out[p] = v
                del remaining[p]
        if not remaining:
            break
    for p in remaining:
        out[p] = s[-1][0]
    return out


def main():
    # cell = (band, bucket) -> dict of accumulators + raw wage list
    agg = collections.defaultdict(lambda: {
        'pop': 0.0, 'employed': 0.0, 'regular': 0.0,
        'n': 0, 'n_emp': 0, 'n_reg': 0,
        'wages_reg': [],   # (wage, weight) for regular salaried
    })

    with SRC.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                age = int(row['age'])
                w   = int(row['mult']) / 100
            except (ValueError, KeyError):
                continue
            band = age_band(age)
            if not band:
                continue
            bkt = bucket_of(row.get('gedu_lvl', '') or '', row.get('tedu_lvl', '') or '')
            d = agg[(band, bkt)]
            d['pop'] += w; d['n'] += 1
            if row.get('pas') in EMPLOYED_CODES:
                d['employed'] += w; d['n_emp'] += 1
                if row.get('pas') == '31':
                    d['regular'] += w; d['n_reg'] += 1
                    try:
                        wage = int(row.get('ern_reg', '0') or '0')
                    except ValueError:
                        wage = 0
                    if wage > 0:
                        d['wages_reg'].append((wage, w))

    def fmt_wage(p):
        if p is None: return '   —   '
        if p >= 100000: return f'₹{p/1000:>4.0f}k'
        return f'₹{p:>5,}'

    for band in ['25-29', '35-39']:
        print('\n' + '=' * 110)
        print(f'CY2025 — Overall population, age {band}')
        print('=' * 110)
        print(f'{"Bucket":<26} {"N":>6} {"Pop (M)":>9} {"WPR":>6} {"%Reg":>6}'
              f'   {"P25":>9} {"Median":>9} {"P75":>9} {"P90":>9}   {"n(reg)":>7}')
        print('-' * 110)
        for bkt in BUCKET_ORDER:
            d = agg[(band, bkt)]
            if d['n'] == 0:
                continue
            wpr = d['employed'] / d['pop'] * 100
            reg_share = d['regular'] / d['pop'] * 100
            pcts = weighted_percentiles(d['wages_reg'], (25, 50, 75, 90))
            print(f'{BUCKET_LABEL[bkt]:<26} {d["n"]:>6,} '
                  f'{d["pop"]/1e6:>9,.2f} {wpr:>5.1f}% {reg_share:>5.1f}%   '
                  f'{fmt_wage(pcts[25])} {fmt_wage(pcts[50])} {fmt_wage(pcts[75])} {fmt_wage(pcts[90])}'
                  f'   {d["n_reg"]:>7,}')

    # Wage growth comparison: median wage at 35-39 / median wage at 25-29
    print('\n' + '=' * 110)
    print('Median wage (regular salaried only): age 25-29 → 35-39 trajectory')
    print('=' * 110)
    print(f'{"Bucket":<26} {"Median 25-29":>13} {"Median 35-39":>13} {"Δ ₹":>10} {"Growth":>9} {"n(25-29)":>9} {"n(35-39)":>9}')
    print('-' * 110)
    for bkt in BUCKET_ORDER:
        d25 = agg[('25-29', bkt)]
        d35 = agg[('35-39', bkt)]
        if d25['n_reg'] == 0 and d35['n_reg'] == 0:
            continue
        m25 = weighted_percentiles(d25['wages_reg'], (50,))[50] if d25['wages_reg'] else None
        m35 = weighted_percentiles(d35['wages_reg'], (50,))[50] if d35['wages_reg'] else None
        if m25 is None or m35 is None:
            print(f'{BUCKET_LABEL[bkt]:<26} {fmt_wage(m25):>13} {fmt_wage(m35):>13}      —       —    '
                  f'{d25["n_reg"]:>9} {d35["n_reg"]:>9}')
            continue
        delta = m35 - m25
        growth = m35 / m25
        print(f'{BUCKET_LABEL[bkt]:<26} {fmt_wage(m25):>13} {fmt_wage(m35):>13} '
              f'+₹{delta:>7,} {growth:>7.2f}x  '
              f'{d25["n_reg"]:>9,} {d35["n_reg"]:>9,}')

    # Headline: wage gaps
    print('\n' + '=' * 110)
    print('Wage gaps (regular salaried, median ₹/month)')
    print('=' * 110)
    for band in ['25-29', '35-39']:
        baseline = agg[(band, 'B')]
        if not baseline['wages_reg']:
            continue
        b_med = weighted_percentiles(baseline['wages_reg'], (50,))[50]
        print(f'\n  Age {band} — baseline (Below Secondary) median = ₹{b_med:,}/month  (n={baseline["n_reg"]:,})')
        for bkt in BUCKET_ORDER:
            if bkt == 'B': continue
            d = agg[(band, bkt)]
            if not d['wages_reg']: continue
            m = weighted_percentiles(d['wages_reg'], (50,))[50]
            print(f'    {BUCKET_LABEL[bkt]:<26} ₹{m:>7,}/month   '
                  f'premium: {(m/b_med - 1)*100:+6.0f}%   '
                  f'(n={d["n_reg"]:,})')


if __name__ == '__main__':
    main()
