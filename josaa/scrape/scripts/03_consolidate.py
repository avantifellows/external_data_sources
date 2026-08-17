#!/usr/bin/env python3
"""
03_consolidate.py — Reduce per-(year, round) raw CSVs to per-year final-round tables.

Inputs:  extracted_data/raw/<year>_R<round>.csv  (produced by 01_scrape_archive.py + 02_scrape_current.py)
Outputs:
  extracted_data/josaa_<year>.csv            — final round only, per year (one file per year)

Schema (consistent across years):
  Institute, Academic Program Name, Quota, Seat Type, Gender,
  Opening Rank, Closing Rank, Year, Round

Cleanups applied:
  - Closing Rank "P" suffix (Preparatory rank for PwD) → strip suffix, mark in is_preparatory col
  - Coerce Opening/Closing rank to nullable Int64
  - Strip extra whitespace from Institute name (JoSAA HTML has stray double-spaces)

NOTE: this used to also produce a `josaa_all_years.csv` union (~87 MB).
That file was dropped because (a) it exceeded GitHub limits when enriched
and (b) it's trivially regenerable. To consolidate at use-time:

  import pandas as pd; from pathlib import Path
  raw = Path('extracted_data/raw')
  all_data = pd.concat([pd.read_csv(f) for f in sorted(raw.glob('*.csv'))], ignore_index=True)
"""
from __future__ import annotations
import re
from pathlib import Path

import pandas as pd

HERE     = Path(__file__).resolve().parent
PIPELINE = HERE.parent
RAW      = PIPELINE / 'extracted_data' / 'raw'
OUT      = PIPELINE / 'extracted_data'


def _clean_rank(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Strip 'P' (Preparatory) suffix; return (rank_int_nullable, is_prep_bool)."""
    s = series.astype(str).str.strip()
    is_prep = s.str.endswith('P')
    s_num = s.str.rstrip('P')
    # to_numeric → float64 with NaN for non-numeric; round + Int64 for nullable int dtype.
    # (Direct .astype('Int64') can fail on numpy/pandas version mismatches; round first.)
    f = pd.to_numeric(s_num, errors='coerce')
    return f.round().astype('Int64'), is_prep


def load_raw():
    files = sorted(RAW.glob('*_R*.csv'))
    if not files:
        raise SystemExit(f'No raw scrape files in {RAW}')
    frames = []
    for f in files:
        df = pd.read_csv(f)
        # Year/Round in filename are authoritative; trust the cols already in CSV
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def main():
    df = load_raw()
    print(f'Loaded {len(df):,} raw rows from {len(list(RAW.glob("*.csv")))} (year, round) files')

    # Normalise institute name whitespace (JoSAA HTML has 'Indian Institute  of Technology Bhubaneswar'
    # with a double space — collapse to single)
    df['Institute'] = df['Institute'].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
    df['Academic Program Name'] = df['Academic Program Name'].astype(str).str.strip()

    # Clean ranks + capture preparatory flag
    df['Opening Rank'], df['opening_is_preparatory'] = _clean_rank(df['Opening Rank'])
    df['Closing Rank'], df['closing_is_preparatory'] = _clean_rank(df['Closing Rank'])

    # Order columns
    cols = ['Institute', 'Academic Program Name', 'Quota', 'Seat Type', 'Gender',
            'Opening Rank', 'Closing Rank', 'Year', 'Round',
            'opening_is_preparatory', 'closing_is_preparatory']
    df = df[cols]

    # Sort for stable output
    df = df.sort_values(['Year', 'Round', 'Institute', 'Academic Program Name',
                         'Quota', 'Seat Type', 'Gender'], kind='mergesort').reset_index(drop=True)

    # Per-year final-round CSVs (the only outputs of this script)
    for year, g in df.groupby('Year'):
        max_r = g['Round'].max()
        gf = g[g['Round'] == max_r].copy()
        out = OUT / f'josaa_{year}.csv'
        gf.to_csv(out, index=False)
        print(f'  josaa_{year}.csv  → final round R{max_r}, {len(gf):,} rows  ({gf["Institute"].nunique()} institutes)')

    # Sanity
    print('\nSanity check — IIT Bombay CSE Open Gender-Neutral, all years final-round closing:')
    iitb = df[df['Institute'].str.contains('Bombay', na=False) &
              df['Academic Program Name'].str.startswith('Computer Science and Engineering (4 Years') &
              (df['Quota'] == 'AI') & (df['Seat Type'] == 'OPEN') &
              (df['Gender'] == 'Gender-Neutral')]
    final = iitb.loc[iitb.groupby('Year')['Round'].idxmax()][['Year', 'Round', 'Closing Rank']]
    print(final.to_string(index=False))


if __name__ == '__main__':
    main()
