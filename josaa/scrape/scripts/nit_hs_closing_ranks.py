#!/usr/bin/env python3
"""
nit_hs_closing_ranks.py
=======================

For each NIT, compute the **last closing rank** under HS quota for a General
(OPEN) Gender-Neutral student in JoSAA 2024:

  - 'NIT_overall'   max closing_rank across all branches at the NIT —
                    the rank at which the NIT's last seat goes (some branch).
                    If your rank ≤ this number, you'll get _some_ seat at the NIT.
  - 'CSE_only'      closing_rank for the canonical Computer Science and
                    Engineering branch.

This is the OPEN-only quick view. For the full 5-category table that the
downstream NCST cutoff methodology consumes, see
nit_hs_closing_ranks_all_categories.py.

Inputs (local — direct from JoSAA scrape, enriched with state/college_id/salary):
  ../extracted_data/josaa_2024_enriched.csv

Outputs:
  ../extracted_data/nit_hs_closing_ranks.csv        — sortable table
  ../extracted_data/nit_hs_closing_ranks.png        — histogram
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

YEAR = 2024  # anchor year — matches the all-categories script

# Filter: HS quota, OPEN seat, Gender-Neutral, NITs only.
# NIT names follow the pattern 'National Institute Of Technology <name>'; we
# also include IIEST Shibpur which is treated as an NIT-equivalent in JoSAA.
def _is_nit(name: str) -> bool:
    if not isinstance(name, str): return False
    return bool(re.search(
        r'(?i)National Institute Of Technology|'
        r'Indian Institute Of Engineering Science And Technology', name))


# Canonical CSE only — exclude AI/DS/cyber/etc flavours
def _is_canonical_cse(course: str) -> bool:
    if not isinstance(course, str): return False
    # Match "Computer Science and Engineering (" but not flavours like
    # "(Artificial Intelligence & Data Science)" or "(Cyber Security)"
    return bool(re.match(r'^Computer Science and Engineering \(\d+ Years',
                         course.strip()))


def main():
    j = pd.read_csv(OUT / f'josaa_{YEAR}_enriched.csv')

    base = j[(j['quota'] == 'HS')
             & (j['seat_type'] == 'OPEN')
             & (j['gender'] == 'Gender-Neutral')
             & (j['entrance_test'] == 'JEE Main')].copy()
    base = base[base['college_name'].apply(_is_nit)]
    # closing_rank may have a 'P' suffix on PWD rows; coerce numerically
    base['closing_rank'] = pd.to_numeric(base['closing_rank'], errors='coerce')
    base = base.dropna(subset=['closing_rank'])

    # Per-NIT: max closing rank across all branches
    overall = (base.groupby(['state', 'college_name'], as_index=False)
                   .agg(nit_last_closing_rank=('closing_rank', 'max'),
                        n_branches=('closing_rank', 'count')))

    # Per-NIT: closing rank for canonical CSE
    cse = base[base['course'].apply(_is_canonical_cse)]
    cse_grp = (cse.groupby(['state', 'college_name'], as_index=False)
                   .agg(cse_closing_rank=('closing_rank', 'max')))

    table = overall.merge(cse_grp, on=['state', 'college_name'], how='left')
    table = table.sort_values('nit_last_closing_rank').reset_index(drop=True)

    # Save the table
    out_csv = OUT / 'nit_hs_closing_ranks.csv'
    table.to_csv(out_csv, index=False)
    print(f'wrote {out_csv}\n')
    print(table.to_string(index=False))

    # ---- Histogram ----
    fig, ax = plt.subplots(figsize=(11, 6))
    bins = [0, 5_000, 10_000, 15_000, 20_000, 30_000, 50_000, 75_000,
            100_000, 150_000, 250_000]
    ax.hist(table['nit_last_closing_rank'], bins=bins,
            alpha=0.55, label='NIT last seat (any branch)', color='#1f77b4',
            edgecolor='black')
    ax.hist(table['cse_closing_rank'].dropna(), bins=bins,
            alpha=0.65, label='CSE only', color='#d62728', edgecolor='black')

    ax.set_xlabel('JEE Main HS closing rank (OPEN, Gender-Neutral)')
    ax.set_ylabel('Number of NITs')
    ax.set_title('NIT HS-quota closing ranks (JoSAA 2024)\n'
                 'Distribution across the 30 NITs')
    ax.legend(loc='upper right')
    ax.set_xscale('log')
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(
        lambda x, _: f'{int(x):,}' if x >= 1 else ''))
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    out_png = OUT / 'nit_hs_closing_ranks.png'
    plt.savefig(out_png, dpi=140)
    print(f'\nwrote {out_png}')


if __name__ == '__main__':
    main()
