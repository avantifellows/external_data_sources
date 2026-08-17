#!/usr/bin/env python3
"""
04_enrich.py — Enrich per-year final-round JoSAA CSVs with state / college_id /
NIRF salary by joining against avanti-college-db-v1/csv/college_master.csv on
institute name.

Match strategy:
  1. Normalised direct match (lowercase, strip punctuation/abbreviations/stop-words).
  2. Fuzzy match (rapidfuzz WRatio ≥ 92) for the rest.
  3. Manual override list for known stragglers.

Coverage today (May 2026):
  NITs    32/32 = 100% (31 direct + 1 fuzzy)
  IITs    23/23 = 100%
  IIITs   ~26/30 = 87%
  GFTIs   ~31/56 = 55% (many GFTIs not in college_master because the master sheet
                        was filtered to JoSAA-2024-Avanti-relevant institutes)

Inputs (must run after 03_consolidate.py):
  extracted_data/josaa_<year>.csv          per-year final-round CSVs

Outputs:
  extracted_data/josaa_<year>_enriched.csv   per-year final round + state/college_id/salary
  extracted_data/_institute_lookup.csv       one row per scrape institute, for traceability

Schema of enriched output:
  college_id, college_name, course, quota, seat_type, gender,
  opening_rank, closing_rank, year, round,
  state, nirf_salary_cleaned, entrance_test, institute_type,
  match_kind, match_score, opening_is_preparatory, closing_is_preparatory

To get all-rounds enriched data at use-time:
  import pandas as pd; from pathlib import Path
  raw = Path('extracted_data/raw')
  all_rounds = pd.concat([pd.read_csv(f) for f in sorted(raw.glob('*.csv'))], ignore_index=True)
  # Then apply build_lookup() + match_institutes() from this module to enrich.
"""
from __future__ import annotations
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import process, fuzz

HERE     = Path(__file__).resolve().parent
PIPELINE = HERE.parent
UPSTREAM = PIPELINE.parent / 'avanti-college-db-v1' / 'csv'
OUT      = PIPELINE / 'extracted_data'

# ---- institute type classifier ----
def classify(name: str) -> str:
    n = str(name)
    if re.search(r'(?i)Indian Institute of Information Technology', n):
        return 'IIIT'
    if re.search(r'(?i)Indian Institute of Engineering Science', n):
        return 'IIEST'
    if re.search(r'(?i)Indian Institute of Technology', n):
        return 'IIT'
    if re.search(r'(?i)National Institute of Technology', n):
        return 'NIT'
    return 'GFTI'

# IITs use JEE Advanced; everything else (NITs/IIITs/GFTIs/IIEST) uses JEE Main
ENTRANCE_FOR = {'IIT': 'JEE Advanced'}


# ---- name normalisation for join ----
def norm(s: str) -> str:
    """Strip punctuation, common abbreviations, 'and'/'of', collapse whitespace."""
    s = str(s).lower()
    s = re.sub(r'[(),&\.\-]', ' ', s)
    s = re.sub(r'\b(iiit|iiitm|iit|nit)\b', ' ', s)
    s = s.replace(' and ', ' ').replace(' of ', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


# ---- manual overrides for known stragglers ----
# Map: scrape_institute_name → college_master.college_name (canonical form to look up)
# Add entries here as you find specific misses worth fixing.
MANUAL_OVERRIDES = {
    # 'Indian Institute of Technology (BHU) Varanasi': '...',  # example: add when you locate the right college_master row
}


_LOOKUP_COLS = ['college_id', 'college_name', 'state',
                'nirf_salary_cleaned',
                'rank_engineering_2024', 'rank_engineering_2025',
                'management_type',
                'salary_tier', 'college_type', 'top_200_nirf']


def build_lookup(college_master_path: Path, college_db_path: Path):
    """Build lookup keyed on normalised institute name. Pulls institutional
    metadata from college_master.csv plus state_cet (entrance_test) from
    college_database.csv (which has the per-state-CET assignments).

    `state_cet` is filtered to true state-level CETs only — national tests
    (JEE, CUET) and private institute tests (BITSAT, VIT) are nulled out so
    the column reads as a state-CET name (KCET, MHT CET, TNEA, etc.) or NaN.
    """
    m = pd.read_csv(college_master_path, low_memory=False, usecols=_LOOKUP_COLS)
    cd = pd.read_csv(college_db_path, low_memory=False,
                     usecols=['college_id', 'entrance_test'])
    cd = cd.dropna(subset=['college_id']).drop_duplicates('college_id')

    # Filter to actual state CETs; everything else (JEE / CUET / BITSAT / VIT) → NaN
    NON_STATE_TESTS = {'JEE', 'JEE Main', 'JEE Advanced', 'CUET', 'BITSAT', 'VIT'}
    cd['state_cet'] = cd['entrance_test'].where(~cd['entrance_test'].isin(NON_STATE_TESTS))
    cd = cd.drop(columns=['entrance_test'])

    m = m.merge(cd, on='college_id', how='left')

    m = m.dropna(subset=['college_name']).copy()
    m['_n'] = m['college_name'].map(norm)
    # Dedupe normalised names; prefer the row with non-null NIRF salary
    m = (m.sort_values('nirf_salary_cleaned', ascending=False, na_position='last')
           .drop_duplicates('_n', keep='first'))
    keep_cols = [c for c in _LOOKUP_COLS if c != 'college_name'] + ['college_name', 'state_cet']
    return m.set_index('_n')[keep_cols].to_dict('index')


def match_institutes(institutes, lookup):
    """For each unique institute name, return (record-or-None, score, kind)."""
    rows = []
    keys = list(lookup.keys())
    for s in institutes:
        if s in MANUAL_OVERRIDES:
            target_norm = norm(MANUAL_OVERRIDES[s])
            if target_norm in lookup:
                rows.append((s, lookup[target_norm], 100, 'manual'))
                continue
        n = norm(s)
        if n in lookup:
            rows.append((s, lookup[n], 100, 'direct'))
            continue
        best = process.extractOne(n, keys, scorer=fuzz.WRatio, score_cutoff=92)
        if best:
            rows.append((s, lookup[best[0]], best[1], 'fuzzy'))
            continue
        rows.append((s, None, 0, 'miss'))
    return rows


RENAMES = {
    'Institute':              'college_name',
    'Academic Program Name':  'course',
    'Quota':                  'quota',
    'Seat Type':              'seat_type',
    'Gender':                 'gender',
    'Opening Rank':           'opening_rank',
    'Closing Rank':           'closing_rank',
    'Year':                   'year',
    'Round':                  'round',
}

ENRICHED_COLS = [
    # Identity
    'college_id', 'college_name', 'course', 'quota', 'seat_type', 'gender',
    'opening_rank', 'closing_rank', 'year', 'round',
    # Institutional
    'state', 'management_type', 'college_type', 'institute_type',
    # Tier / outcome signals
    'rank_engineering_2024', 'rank_engineering_2025',
    'nirf_salary_cleaned', 'salary_tier', 'top_200_nirf',
    # Entry route
    'entrance_test', 'entry_jee_main', 'state_cet',
    # Provenance
    'match_kind', 'match_score',
    'opening_is_preparatory', 'closing_is_preparatory',
]


def enrich_dataframe(df, inst_lookup):
    """Apply the institute-level enrichment join to any JoSAA scrape DataFrame
    (final-round per-year or all-rounds union — same join works on both).
    Caller is responsible for column renames if needed."""
    e = df.merge(
        inst_lookup[['institute_scrape', 'institute_type', 'college_id', 'state',
                     'management_type', 'college_type',
                     'rank_engineering_2024', 'rank_engineering_2025',
                     'nirf_salary_cleaned', 'salary_tier', 'top_200_nirf',
                     'entrance_test', 'entry_jee_main', 'state_cet',
                     'match_kind', 'match_score']],
        left_on='Institute', right_on='institute_scrape', how='left'
    ).drop(columns=['institute_scrape'])
    e = e.rename(columns=RENAMES)
    return e[ENRICHED_COLS]


def main():
    per_year_files = sorted(OUT.glob('josaa_20*.csv'))
    # Filter out any *_enriched.csv files we'd otherwise pick up
    per_year_files = [f for f in per_year_files if '_enriched' not in f.name]
    if not per_year_files:
        raise SystemExit(f'No per-year CSVs in {OUT}. Run 03_consolidate.py first.')
    print(f'Loading {len(per_year_files)} per-year CSVs ...')

    lookup = build_lookup(UPSTREAM / 'college_master.csv',
                          UPSTREAM / 'college_database.csv')
    print(f'  college_master normalised lookup: {len(lookup):,} entries')

    # Build the institute lookup once over the union of unique institute names
    # across all years (cheap — we only need unique strings, not full data).
    unique_insts = set()
    for f in per_year_files:
        unique_insts.update(pd.read_csv(f, usecols=['Institute'])['Institute'].dropna().unique())
    matches = match_institutes(sorted(unique_insts), lookup)
    matched = sum(1 for _, r, _, _ in matches if r is not None)
    print(f'  Matched: {matched}/{len(matches)} institutes')

    rows = []
    for inst, rec, score, kind in matches:
        rows.append({
            'institute_scrape': inst,
            'institute_type':   classify(inst),
            'college_id':       rec['college_id'] if rec else None,
            'college_name':     rec['college_name'] if rec else inst,
            'state':            rec['state'] if rec else None,
            'management_type':  rec['management_type'] if rec else None,
            'rank_engineering_2024': rec['rank_engineering_2024'] if rec else None,
            'rank_engineering_2025': rec['rank_engineering_2025'] if rec else None,
            'nirf_salary_cleaned': rec['nirf_salary_cleaned'] if rec else None,
            'salary_tier':      rec['salary_tier'] if rec else None,
            'college_type':     rec['college_type'] if rec else None,
            'top_200_nirf':     rec['top_200_nirf'] if rec else None,
            'state_cet':        rec.get('state_cet') if rec else None,
            'match_kind':       kind,
            'match_score':      score,
        })
    inst_lookup = pd.DataFrame(rows)
    # Entrance exam: 'JEE Advanced' for IITs, 'JEE Main' for everything else
    inst_lookup['entrance_test'] = inst_lookup['institute_type'].map(ENTRANCE_FOR).fillna('JEE Main')
    # Boolean-style flag (matches top_200_nirf 'Yes'/'No' convention)
    inst_lookup['entry_jee_main'] = (inst_lookup['institute_type'] != 'IIT').map({True: 'Yes', False: 'No'})
    inst_lookup.to_csv(OUT / '_institute_lookup.csv', index=False)
    print(f'  Wrote _institute_lookup.csv\n')

    print('Match quality by institute type:')
    print(inst_lookup.groupby('institute_type').agg(
        n=('institute_scrape', 'count'),
        matched=('match_kind', lambda s: (s != 'miss').sum()),
        direct=('match_kind', lambda s: (s == 'direct').sum()),
        fuzzy=('match_kind', lambda s: (s == 'fuzzy').sum()),
    ).to_string())
    print()

    # Enrich per-year final-round CSVs (one file in, one file out)
    for f in per_year_files:
        df = pd.read_csv(f)
        e = enrich_dataframe(df, inst_lookup)
        out_path = OUT / f.name.replace('.csv', '_enriched.csv')
        e.to_csv(out_path, index=False)
        print(f'  Wrote {out_path.name}: {len(e):,} rows')


if __name__ == '__main__':
    main()
