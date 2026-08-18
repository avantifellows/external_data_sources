#!/usr/bin/env python3
"""
nit_hs_closing_ranks_all_categories.py
========================================

For each NIT × category, compute the HS-quota last closing rank under JoSAA 2024
(JEE Main, Gender-Neutral). Categories covered:

  - OPEN       (General / Unreserved)
  - EWS        (Economically Weaker Section)
  - OBC-NCL    (OBC Non-Creamy Layer)
  - SC         (Scheduled Caste)
  - ST         (Scheduled Tribe)

Reserved-category closing ranks are CATEGORY ranks (e.g. SC closing rank is the
SC-rank, not the All India Rank). OPEN closing rank is the AIR.

For each (NIT, category):
  - nit_last_closing_rank: max closing_rank across all branches (= the rank
                           below which you'd get _some_ seat at the NIT)
  - cse_closing_rank:      closing_rank for canonical Computer Science and
                           Engineering (4-year B.Tech, no AI/Cyber/DS flavour)

Joined to nirf_salary_cleaned (already merged into the enriched scrape via 04_enrich.py).

Inputs (local — direct from JoSAA scrape, enriched with state/college_id/salary):
  ../extracted_data/josaa_2024_enriched.csv

Outputs:
  ../extracted_data/nit_hs_closing_ranks_all_categories.csv       — long format
  ../extracted_data/nit_hs_closing_ranks_all_categories_wide.csv  — pivoted wide
  ../extracted_data/nit_hs_closing_ranks_scatter.png              — closing rank vs salary

To bump anchor year: change YEAR below from 2024 → 2025 (etc.) once methodology is updated.
"""
from __future__ import annotations
import re
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE     = Path(__file__).resolve().parent          # josaa-ranks/scripts/
PIPELINE = HERE.parent                              # josaa-ranks/
OUT      = PIPELINE / 'extracted_data'
OUT.mkdir(parents=True, exist_ok=True)

YEAR = 2024  # anchor year for the NCST cutoff methodology — change with care

CATEGORIES = ['OPEN', 'EWS', 'OBC-NCL', 'SC', 'ST']
CAT_COLOR  = {
    'OPEN':    '#1f77b4',
    'EWS':     '#9467bd',
    'OBC-NCL': '#2ca02c',
    'SC':      '#d62728',
    'ST':      '#ff7f0e',
}


def _is_nit(name) -> bool:
    if not isinstance(name, str): return False
    return bool(re.search(
        r'(?i)National Institute Of Technology|'
        r'Indian Institute Of Engineering Science And Technology', name))


def _is_canonical_cse(course) -> bool:
    if not isinstance(course, str): return False
    return bool(re.match(r'^Computer Science and Engineering \(\d+ Years',
                         course.strip()))


def _short_nit(name: str) -> str:
    """Compact NIT name for plot labels and tables. Case-insensitive on input."""
    s = re.sub(r'(?i)National Institute of Technology', 'NIT', name)
    s = re.sub(r'(?i)Indian Institute of Engineering Science and Technology', 'IIEST', s)
    s = s.replace('Karnataka Surathkal', 'Surathkal')
    # Python 3.14 disallows (?i) anywhere except the very start of a pattern; lead with the flag.
    s = re.sub(r'(?i)^Maulana Azad NIT',     'MANIT', s)
    s = re.sub(r'(?i)^Malaviya NIT',         'MNIT',  s)
    s = re.sub(r'(?i)^Motilal Nehru NIT',    'MNNIT', s)
    s = re.sub(r'(?i)^Visvesvaraya NIT',     'VNIT',  s)
    s = re.sub(r'(?i)^Sardar Vallabhbhai NIT','SVNIT',s)
    s = re.sub(r'(?i)^Dr B R Ambedkar NIT',  'NIT',   s)
    return s.strip()


def main():
    j = pd.read_csv(OUT / f'josaa_{YEAR}_enriched.csv')

    base = j[(j['quota'] == 'HS')
             & (j['gender'] == 'Gender-Neutral')
             & (j['entrance_test'] == 'JEE Main')
             & (j['seat_type'].isin(CATEGORIES))].copy()
    base = base[base['college_name'].apply(_is_nit)]
    base['closing_rank'] = pd.to_numeric(base['closing_rank'], errors='coerce')
    base = base.dropna(subset=['closing_rank'])

    # JoSAA HTML has occasional double-spaces in institute names (e.g.,
    # "Indian Institute  of Technology Bhubaneswar") — already collapsed by 03_consolidate.py.
    # Lowercase compare here just in case multiple capitalisation variants leak through.
    def _normalize_name(n):
        return re.sub(r'\s+', ' ', str(n).lower().strip())
    name_canonical = (base.assign(_n=base['college_name'].apply(_normalize_name))
                          .groupby('_n')['college_name']
                          .agg(lambda s: s.value_counts().index[0]))
    base['college_name'] = base['college_name'].apply(_normalize_name).map(name_canonical)

    # Per (state, NIT, category): NIT-last + CSE
    overall = (base.groupby(['state', 'college_name', 'college_id', 'seat_type'],
                            as_index=False)
                   .agg(nit_last_closing_rank=('closing_rank', 'max'),
                        n_branches=('closing_rank', 'count')))

    cse = base[base['course'].apply(_is_canonical_cse)]
    cse_grp = (cse.groupby(['state', 'college_name', 'college_id', 'seat_type'],
                           as_index=False)
                   .agg(cse_closing_rank=('closing_rank', 'max')))

    long = overall.merge(cse_grp,
                         on=['state', 'college_name', 'college_id', 'seat_type'],
                         how='left')

    # NIRF median salary is already on the enriched rows; pull one value per institute
    salary = (j[['college_id', 'nirf_salary_cleaned']]
                .dropna(subset=['college_id']).drop_duplicates('college_id'))
    long = long.merge(salary, on='college_id', how='left')

    long['short_name'] = long['college_name'].apply(_short_nit)
    long = long.rename(columns={'seat_type': 'category'})
    long = long.sort_values(['state', 'category']).reset_index(drop=True)

    long_path = OUT / 'nit_hs_closing_ranks_all_categories.csv'
    long.to_csv(long_path, index=False)
    print(f'wrote {long_path}  ({len(long)} rows)')

    # Wide pivot for human-readable table
    wide_nit_last = long.pivot_table(index=['state', 'short_name'],
                                     columns='category',
                                     values='nit_last_closing_rank',
                                     aggfunc='first')[CATEGORIES]
    wide_cse = long.pivot_table(index=['state', 'short_name'],
                                columns='category',
                                values='cse_closing_rank',
                                aggfunc='first')[CATEGORIES]
    salary = long.groupby(['state', 'short_name'])['nirf_salary_cleaned'].first()

    # Combine into one wide DataFrame
    wide = pd.concat([
        salary.rename('nirf_median_salary'),
        wide_nit_last.add_prefix('nit_last_'),
        wide_cse.add_prefix('cse_'),
    ], axis=1).reset_index()
    wide = wide.sort_values('cse_OPEN', na_position='last').reset_index(drop=True)
    wide_path = OUT / 'nit_hs_closing_ranks_all_categories_wide.csv'
    wide.to_csv(wide_path, index=False)
    print(f'wrote {wide_path}  ({len(wide)} rows × {wide.shape[1]} cols)')

    # ---- Scatter plot: closing rank vs NIRF salary, colored by category ----
    plot_data = long.dropna(subset=['nirf_salary_cleaned']).copy()

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), sharey=True)
    for ax, rank_col, title in [
        (axes[0], 'cse_closing_rank',      'CSE closing rank'),
        (axes[1], 'nit_last_closing_rank', 'NIT-last closing rank (any branch)'),
    ]:
        for cat in CATEGORIES:
            sub = plot_data[plot_data['category'] == cat]
            sub = sub.dropna(subset=[rank_col])
            ax.scatter(sub[rank_col], sub['nirf_salary_cleaned'] / 100_000,
                       c=CAT_COLOR[cat], label=cat, alpha=0.75,
                       s=55, edgecolor='white', linewidth=0.5)
        ax.set_xscale('log')
        ax.set_xlabel(f'{title}  (log scale)')
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(
            lambda x, _: f'{int(x):,}' if x >= 1 else ''))
        ax.grid(True, alpha=0.3)
        ax.set_title(title)
    axes[0].set_ylabel('NIRF median salary (₹ lakhs / year)')
    axes[0].legend(title='Category', loc='lower left')

    fig.suptitle('NIT HS-quota: closing rank vs NIRF median salary (JoSAA 2024)',
                 fontsize=13)
    plt.tight_layout()

    out_png = OUT / 'nit_hs_closing_ranks_scatter.png'
    plt.savefig(out_png, dpi=140)
    print(f'wrote {out_png}')


if __name__ == '__main__':
    main()
