"""
Longitudinal: youth (age 20-25) in regular IT jobs, across PLFS releases.

Filters per release:
  age IN [20, 25]   AND   pas == '31' (regular salaried/wage employee)   AND
  ind_pas starts with '62' or '63' (NIC 2008 IT industries)

Weights (per release):
  annual_2018_19, calendar_2022, calendar_2024 (annual-style):
      weight = mult / no_qtr / IF(nss == nsc, 100, 200)
  calendar_2025 (simplified rule):
      weight = mult / 100

Outputs:
  - Weighted count of youth in IT regular jobs per release
  - Wage distribution (P25, median, mean, P75, P90) — nominal
  - Real wage equivalent (deflated to 2025 prices using rough CPI factors)
  - Gender split

Caveats:
  - Sample sizes for this narrow cell can be small. n is reported.
  - CPI factors are approximations (All-India CPI, 2012=100). For more
    precise real-wage analysis use the actual MoSPI CPI series.
"""

import csv, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# CPI factors to convert nominal ₹ to "2025 prices" (rough; All-India CPI)
CPI_TO_2025 = {
    'annual_2018_19': 1.41,   # 2018-19 → 2025
    'calendar_2022':  1.15,   # 2022 → 2025
    'calendar_2024':  1.04,   # 2024 → 2025
    'calendar_2025':  1.00,
}

RELEASES = [
    ('annual_2018_19', 'clean/annual_2018_19/perv1.csv',     'Jul 2018 – Jun 2019', '2018-19'),
    ('calendar_2022',  'clean/calendar_2022/cperv1.csv',     'Jan – Dec 2022',      '2022'),
    ('calendar_2024',  'clean/calendar_2024/cperv1.csv',     'Jan – Dec 2024',      '2024'),
    ('calendar_2025',  'clean/calendar_2025/cperv1.csv',     'Jan – Dec 2025',      '2025'),
]


def safe_int(x, default=0):
    try: return int(x)
    except (ValueError, TypeError): return default


def annual_combined_weight(row):
    mult = safe_int(row.get('mult'))
    nss = safe_int(row.get('nss'))
    nsc = safe_int(row.get('nsc'))
    no_qtr = safe_int(row.get('no_qtr'), 1)
    if no_qtr == 0: no_qtr = 1
    div = 100 if nss == nsc else 200
    return mult / no_qtr / div


def cy2025_weight(row):
    return safe_int(row.get('mult')) / 100


WEIGHT_FN = {
    'annual_2018_19': annual_combined_weight,
    'calendar_2022':  annual_combined_weight,
    'calendar_2024':  annual_combined_weight,
    'calendar_2025':  cy2025_weight,
}


def is_it(ind_pas):
    return bool(ind_pas) and ind_pas[:2] in ('62', '63')


def weighted_pct(values_weights, q):
    s = sorted(values_weights)
    total = sum(w for _, w in s)
    if total == 0: return None
    target = total * q
    cum = 0
    for v, w in s:
        cum += w
        if cum >= target: return v
    return s[-1][0]


def weighted_mean(values_weights):
    total_w = sum(w for _, w in values_weights)
    if total_w == 0: return None
    return sum(v * w for v, w in values_weights) / total_w


def analyze(release, csv_path, period_label, year_label):
    weight_fn = WEIGHT_FN[release]
    cpi = CPI_TO_2025[release]

    n_total = 0
    weighted_total = 0.0
    n_men = 0; w_men = 0.0
    n_women = 0; w_women = 0.0
    wages = []          # (wage, weight) for all
    wages_men = []
    wages_women = []

    with open(csv_path) as f:
        for row in csv.DictReader(f):
            try:
                age = int(row['age'])
            except (KeyError, ValueError):
                continue
            if not (20 <= age <= 25): continue
            if row.get('pas') != '31': continue
            if not is_it(row.get('ind_pas', '')): continue
            try:
                w = weight_fn(row)
            except (ValueError, ZeroDivisionError):
                continue
            n_total += 1
            weighted_total += w
            sex = row.get('sex')
            if sex == '1':
                n_men += 1; w_men += w
            elif sex == '2':
                n_women += 1; w_women += w
            wage = safe_int(row.get('ern_reg'))
            if wage > 0:
                wages.append((wage, w))
                if sex == '1': wages_men.append((wage, w))
                elif sex == '2': wages_women.append((wage, w))

    # Wage stats — nominal
    p25 = weighted_pct(wages, 0.25)
    p50 = weighted_pct(wages, 0.50)
    p75 = weighted_pct(wages, 0.75)
    p90 = weighted_pct(wages, 0.90)
    mean = weighted_mean(wages)

    # Real (2025 prices)
    p50_real = int(p50 * cpi) if p50 else None
    mean_real = int(mean * cpi) if mean else None

    return {
        'release': release,
        'year': year_label,
        'period': period_label,
        'n_total': n_total,
        'weighted_total': weighted_total,
        'n_men': n_men, 'w_men': w_men,
        'n_women': n_women, 'w_women': w_women,
        'p25': p25, 'p50': p50, 'p75': p75, 'p90': p90, 'mean': mean,
        'p50_real_2025': p50_real, 'mean_real_2025': mean_real,
        'cpi_factor': cpi,
        'p50_men': weighted_pct(wages_men, 0.50),
        'p50_women': weighted_pct(wages_women, 0.50),
        'n_with_wage': len(wages),
    }


def main():
    rows = []
    for release, csv_path, period, year in RELEASES:
        if not Path(csv_path).exists():
            print(f'  SKIP {release}: {csv_path} not found')
            continue
        rows.append(analyze(release, csv_path, period, year))

    # Headline table
    print('=' * 110)
    print('Youth (age 20-25) employed in regular IT jobs — longitudinal')
    print('=' * 110)
    print(f'{"Year":<10} {"Period":<22} {"N (raw)":>8} {"Weighted pop":>13}  {"Men":>10} {"Women":>10}  {"%Wmn":>5}')
    print('-' * 110)
    for r in rows:
        women_share = r['w_women'] / r['weighted_total'] * 100 if r['weighted_total'] else 0
        print(f'{r["year"]:<10} {r["period"]:<22} {r["n_total"]:>8,} {r["weighted_total"]:>13,.0f}  '
              f'{r["w_men"]:>10,.0f} {r["w_women"]:>10,.0f}  {women_share:>4.1f}%')

    # Wage table — nominal
    print('\n' + '=' * 110)
    print('Wages (₹/month, regular salaried, NOMINAL)')
    print('=' * 110)
    print(f'{"Year":<10} {"P25":>10} {"Median":>10} {"Mean":>10} {"P75":>10} {"P90":>10}   {"n(wage)":>8}')
    print('-' * 80)
    for r in rows:
        if not r['p50']:
            print(f'{r["year"]:<10} (no wage data)')
            continue
        print(f'{r["year"]:<10} ₹{r["p25"]:>8,} ₹{r["p50"]:>8,} ₹{r["mean"]:>8,.0f} ₹{r["p75"]:>8,} ₹{r["p90"]:>8,}   {r["n_with_wage"]:>8,}')

    # Wage table — real
    print('\n' + '=' * 110)
    print('Wages adjusted to 2025 prices (CPI-deflated, rough estimate)')
    print('=' * 110)
    print(f'{"Year":<10} {"CPI×":>6}  {"Nominal median":>16}  {"Real (2025) median":>22}  {"Nominal mean":>16}  {"Real (2025) mean":>20}')
    print('-' * 110)
    for r in rows:
        if not r['p50']: continue
        print(f'{r["year"]:<10} {r["cpi_factor"]:>5.2f}×  '
              f'₹{r["p50"]:>14,}  ₹{r["p50_real_2025"]:>20,}  '
              f'₹{r["mean"]:>14,.0f}  ₹{r["mean_real_2025"]:>18,}')

    # Gender wage gap
    print('\n' + '=' * 110)
    print('Median wage by gender (₹/month, nominal)')
    print('=' * 110)
    print(f'{"Year":<10} {"Men median":>12} {"Women median":>14}  {"F/M ratio":>10}')
    print('-' * 60)
    for r in rows:
        m = r['p50_men']; w = r['p50_women']
        if not (m and w): continue
        ratio = w / m
        print(f'{r["year"]:<10} ₹{m:>10,} ₹{w:>12,}  {ratio*100:>9.0f}%')

    # YoY change relative to 2018-19 baseline
    if rows and rows[0]['weighted_total']:
        baseline = rows[0]
        print('\n' + '=' * 110)
        print('Change relative to 2018-19 baseline')
        print('=' * 110)
        print(f'{"Year":<10} {"Pop change":>12}   {"Real-wage median change":>24}')
        print('-' * 55)
        for r in rows:
            pop_d = (r['weighted_total'] / baseline['weighted_total'] - 1) * 100
            if r['p50_real_2025'] and baseline['p50_real_2025']:
                wage_d = (r['p50_real_2025'] / baseline['p50_real_2025'] - 1) * 100
                wage_str = f'{wage_d:>+8.1f}%'
            else:
                wage_str = '       —'
            print(f'{r["year"]:<10} {pop_d:>+10.1f}%        {wage_str}')


if __name__ == '__main__':
    main()
