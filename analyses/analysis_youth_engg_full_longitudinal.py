"""
Longitudinal: engineers (UG/PG, tedu_lvl in {03, 13}) age 20-24 in regular salaried jobs ≥ ₹25k.
Across all usable PLFS releases 2018-19 to CY2025.

Excluded: calendar_2021 (cat 209) — limited schema, no tedu_lvl/pas/ern_reg.

This analysis uses the per-release weight functions from scripts/weights.py.
Per-release rules are documented in WEIGHTS.md and surfaced as the
`weight_rule` column in clean/releases.csv.

Wage tiers (nominal):
  Low: ₹25,000 – ₹29,999
  Med: ₹30,000 – ₹49,999
  High: ≥ ₹50,000
"""
import csv, collections, sys
from pathlib import Path

# Pull weight functions + release metadata from the shared module
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from weights import get_weight_fn       # noqa: E402
from releases import RELEASES as _ALL_RELEASES   # noqa: E402

ENGG_TEDU = {'03', '13'}
AGE_LO, AGE_HI = 20, 24
WAGE_FLOOR = 25_000

# Which releases participate in this analysis — excludes 'limited' rules.
# Ordered chronologically. Per-release labels for the report.
RELEASE_ORDER = [
    'annual_2018_19', 'annual_2019_20', 'annual_2020_21',
    'annual_2021_22', 'calendar_2022',  'annual_2022_23',
    'calendar_2023',  'annual_2023_24', 'calendar_2024',
    'calendar_2025',
]

def _per_path(release_id: str) -> Path:
    """Return the person-level file path for a release (perv1 or cperv1)."""
    cfg = _ALL_RELEASES[release_id]
    candidates = ('perv1.csv', 'cperv1.csv')
    for c in candidates:
        p = cfg['out_dir'] / c
        if p.exists():
            return p
    raise FileNotFoundError(f"No perv1/cperv1 for {release_id}")

# Build the list of (release_id, path, period_label, format, year_label)
RELEASES = []
for rid in RELEASE_ORDER:
    cfg = _ALL_RELEASES[rid]
    period = f"{cfg['period_start']} – {cfg['period_end']}"
    if rid == 'calendar_2023': period += " *"   # flagged for half-yearly note
    RELEASES.append((rid, _per_path(rid), period, cfg['format'], cfg['year_label']))


def tier(wage):
    if wage < 30_000: return 'Low (₹25-30k)'
    if wage < 50_000: return 'Med (₹30-50k)'
    return 'High (>₹50k)'

TIERS = ['Low (₹25-30k)', 'Med (₹30-50k)', 'High (>₹50k)']

def _safe_int(x, d=0):
    try: return int(x)
    except (ValueError, TypeError):
        try: return int(float(x))
        except (ValueError, TypeError): return d

# Per release: collect cohort
data = {}
for release, path, period, fmt, year in RELEASES:
    weight_fn = get_weight_fn(release)
    rows = []
    if not path.exists():
        print(f'  MISSING: {path}')
        continue
    with path.open() as f:
        for r in csv.DictReader(f):
            if r.get('tedu_lvl') not in ENGG_TEDU: continue
            try: age = int(r['age'])
            except (ValueError, KeyError): continue
            if not (AGE_LO <= age <= AGE_HI): continue
            if r.get('pas') != '31': continue
            try: w = weight_fn(r)
            except (ValueError, ZeroDivisionError, NotImplementedError): continue
            wage = _safe_int(r.get('ern_reg'))
            if wage < WAGE_FLOOR: continue
            rows.append({'wage': wage, 'tier': tier(wage), 'weight': w})
    data[year] = {'rows': rows, 'fmt': fmt, 'period': period, 'release': release}

print('=' * 110)
print('Engineering grads age 20-24 in regular salaried jobs ≥ ₹25,000/month (nominal) — wage-tier longitudinal')
print('=' * 110)
print(f'{"Year":<10} {"Period":<22} {"Format":<10} ', '  '.join(f'{t:<19}' for t in TIERS), '   Total')
print('-' * 130)

for year, d in data.items():
    rows = d['rows']
    total_w = sum(r['weight'] for r in rows)
    cells = []
    for t in TIERS:
        w = sum(r['weight'] for r in rows if r['tier'] == t)
        n = sum(1 for r in rows if r['tier'] == t)
        share = w/total_w*100 if total_w else 0
        cells.append(f'{w:>9,.0f} ({share:>4.1f}%) n={n:<3}')
    print(f'{year:<10} {d["period"]:<22} {d["fmt"]:<10} ', '  '.join(f'{c:<19}' for c in cells), f'   {total_w:>9,.0f} (n={len(rows):>3})')

# Sample sizes table
print('\n' + '=' * 80)
print('Raw sample sizes — flag cells with n<10 as too sparse to interpret')
print('=' * 80)
print(f'{"Year":<10} ', '  '.join(f'{t:<14}' for t in TIERS), '   Total')
print('-' * 80)
sparse_cells = 0
for year, d in data.items():
    rows = d['rows']
    cells = []
    for t in TIERS:
        n = sum(1 for r in rows if r['tier'] == t)
        flag = ' ⚠️' if n < 10 else ''
        cells.append(f'n = {n:>4}{flag}')
        if n < 10: sparse_cells += 1
    cells.append(f'n = {len(rows):>4}')
    print(f'{year:<10} ', '  '.join(f'{c:<14}' for c in cells))

print(f'\nTotal sparse cells (n<10): {sparse_cells}')

# Year-over-year change in totals (nominal)
print('\n' + '=' * 110)
print('Total cohort growth (₹25k+ regular jobs for engineers 20-24) — anchor to 2018-19')
print('=' * 110)
years_seen = list(data.keys())
baseline = sum(r['weight'] for r in data[years_seen[0]]['rows'])
print(f'{"Year":<10} {"Total weighted":>16} {"Δ vs 2018-19":>18}')
print('-' * 50)
for year, d in data.items():
    tot = sum(r['weight'] for r in d['rows'])
    pct = (tot/baseline - 1)*100 if baseline else 0
    print(f'{year:<10} {tot:>16,.0f} {pct:>+16.1f}%')

# Drill into HIGH tier specifically — most volatile
print('\n' + '=' * 110)
print('High-wage engineering jobs (>₹50k/month) — engineer 20-24, year by year')
print('=' * 110)
print(f'{"Year":<10} {"Weighted":>12} {"Median wage in tier":>20} {"P75 wage":>10} {"P90 wage":>10}  {"raw n":>7}')
print('-' * 80)
def wp(vw, q):
    if not vw: return None
    s = sorted(vw); tot = sum(w for _, w in s)
    cum = 0
    for v, w in s:
        cum += w
        if cum >= tot*q: return v
    return s[-1][0]
for year, d in data.items():
    rows = [r for r in d['rows'] if r['tier'] == 'High (>₹50k)']
    n = len(rows)
    w_total = sum(r['weight'] for r in rows)
    vw = [(r['wage'], r['weight']) for r in rows]
    med = wp(vw, 0.5); p75 = wp(vw, 0.75); p90 = wp(vw, 0.9)
    print(f'{year:<10} {w_total:>12,.0f} {f"₹{med:,}" if med else "—":>20} '
          f'{f"₹{p75:,}" if p75 else "—":>10} {f"₹{p90:,}" if p90 else "—":>10}  {n:>7,}')

# Drill into the LOW tier (₹25-30k) — most exposed to AI cuts at entry level
print('\n' + '=' * 110)
print('Low-wage entry-tier engineering jobs (₹25-30k/month) — engineer 20-24')
print('=' * 110)
print(f'{"Year":<10} {"Weighted":>12} {"Median wage in tier":>20} {"P75":>10}  {"raw n":>7}')
print('-' * 65)
for year, d in data.items():
    rows = [r for r in d['rows'] if r['tier'] == 'Low (₹25-30k)']
    n = len(rows)
    w_total = sum(r['weight'] for r in rows)
    vw = [(r['wage'], r['weight']) for r in rows]
    med = wp(vw, 0.5); p75 = wp(vw, 0.75)
    print(f'{year:<10} {w_total:>12,.0f} {f"₹{med:,}" if med else "—":>20} '
          f'{f"₹{p75:,}" if p75 else "—":>10}  {n:>7,}')

# DROP recommendations
print('\n' + '=' * 110)
print('SPARSENESS ASSESSMENT — which datasets to keep / drop')
print('=' * 110)
for year, d in data.items():
    rows = d['rows']
    n_total = len(rows)
    n_high = sum(1 for r in rows if r['tier'] == 'High (>₹50k)')
    n_low = sum(1 for r in rows if r['tier'] == 'Low (₹25-30k)')
    if n_total < 50:
        verdict = 'DROP (total n<50)'
    elif n_high < 10 and n_low < 10:
        verdict = 'CAUTION (both high and low tiers sparse)'
    else:
        verdict = 'KEEP'
    print(f'  {year:<10} n={n_total:>4}  high={n_high:>3}  low={n_low:>3}  →  {verdict}')
