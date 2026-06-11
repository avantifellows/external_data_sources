#!/usr/bin/env python3
"""
01_scrape_archive.py — Scrape JoSAA Opening/Closing Rank archive (2016–2024).

Source: https://josaa.admissions.nic.in/applicant/seatmatrix/openingclosingrankarchieve.aspx
Form: ASP.NET WebForms with cascading dropdowns (Year → Round → InsType → Institute → Branch → SeatType).
We submit "ALL" for InsType / Institute / Branch / SeatType to get the full table per (year, round).

Approach: requests + BeautifulSoup. Maintain a session; carry __VIEWSTATE / __EVENTVALIDATION
between posts; trigger each cascade with __EVENTTARGET pointing at the dropdown that just changed.

Output: extracted_data/raw/<year>_R<round>.csv  — per-(year, round), schema:
  Institute, Academic Program Name, Quota, Seat Type, Gender, Opening Rank, Closing Rank, Year, Round

Idempotent: re-running overwrites the same files.
2025 is on a separate "current" endpoint; see 02_scrape_current.py.
"""
from __future__ import annotations
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = 'https://josaa.admissions.nic.in/applicant/seatmatrix/openingclosingrankarchieve.aspx'

HERE     = Path(__file__).resolve().parent
PIPELINE = HERE.parent
RAW      = PIPELINE / 'extracted_data' / 'raw'
RAW.mkdir(parents=True, exist_ok=True)

# Pause between cascading postbacks to be a polite scraper.
PAUSE_SEC = 0.6

# Default years/rounds. Each year's actual round count is discovered after Year is selected.
DEFAULT_YEARS = ['2024', '2023', '2022', '2021', '2020', '2019', '2018', '2017', '2016']

# ASP.NET control names
F_YEAR    = 'ctl00$ContentPlaceHolder1$ddlYear'
F_ROUND   = 'ctl00$ContentPlaceHolder1$ddlroundno'
F_INSTYPE = 'ctl00$ContentPlaceHolder1$ddlInstype'
F_INST    = 'ctl00$ContentPlaceHolder1$ddlInstitute'
F_BRANCH  = 'ctl00$ContentPlaceHolder1$ddlBranch'
F_SEAT    = 'ctl00$ContentPlaceHolder1$ddlSeatType'
F_SUBMIT  = 'ctl00$ContentPlaceHolder1$btnSubmit'


def _hidden(soup):
    """Capture every ASP.NET hidden input (VIEWSTATE etc.) — must be sent on every postback."""
    return {tag['name']: tag.get('value', '')
            for tag in soup.find_all('input', type='hidden') if tag.get('name')}


def _options(soup, name):
    """Read current options of a select."""
    sel = soup.find('select', attrs={'name': name})
    if sel is None:
        return []
    return [(o.get('value', ''), (o.text or '').strip()) for o in sel.find_all('option')]


def _post(session, soup, updates, event_target):
    """Send a single postback with given field updates. Returns the new soup."""
    data = _hidden(soup)
    data.update(updates)
    data['__EVENTTARGET'] = event_target
    data['__EVENTARGUMENT'] = ''
    time.sleep(PAUSE_SEC)
    r = session.post(URL, data=data, timeout=60)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'lxml')


def _submit(session, soup, year, rnd):
    """Final POST: trigger Submit with all dropdowns set to ALL. Returns the result soup."""
    data = _hidden(soup)
    data.update({
        F_YEAR: year, F_ROUND: rnd,
        F_INSTYPE: 'ALL', F_INST: 'ALL', F_BRANCH: 'ALL', F_SEAT: 'ALL',
        F_SUBMIT: 'Submit',
    })
    # Submit is not an EVENTTARGET dropdown; pop the cascade markers so the page interprets
    # this as a button click, not a dropdown change.
    data.pop('__EVENTTARGET', None)
    data.pop('__EVENTARGUMENT', None)
    time.sleep(PAUSE_SEC)
    r = session.post(URL, data=data, timeout=120)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'lxml')


def scrape_year_round(session, year, rnd):
    """Cascade through (Year, Round, Type=ALL, Inst=ALL, Branch=ALL, Seat=ALL) → submit → harvest."""
    # 0. Fresh GET to re-init viewstate
    r = session.get(URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')

    # 1. Year
    soup = _post(session, soup, {F_YEAR: year}, F_YEAR)
    round_opts = [v for v, _ in _options(soup, F_ROUND) if v not in ('', '0')]
    if rnd not in round_opts:
        return None, f'round {rnd} not available; options={round_opts}'

    # 2. Round
    soup = _post(session, soup, {F_YEAR: year, F_ROUND: rnd}, F_ROUND)
    type_opts = [v for v, _ in _options(soup, F_INSTYPE) if v not in ('', '0')]
    if 'ALL' not in type_opts:
        return None, f'no ALL in instype; opts={type_opts}'

    # 3. Type=ALL
    soup = _post(session, soup, {F_YEAR: year, F_ROUND: rnd, F_INSTYPE: 'ALL'}, F_INSTYPE)
    # 4. Inst=ALL
    soup = _post(session, soup,
                 {F_YEAR: year, F_ROUND: rnd, F_INSTYPE: 'ALL', F_INST: 'ALL'}, F_INST)
    # 5. Branch=ALL
    soup = _post(session, soup,
                 {F_YEAR: year, F_ROUND: rnd, F_INSTYPE: 'ALL', F_INST: 'ALL', F_BRANCH: 'ALL'},
                 F_BRANCH)
    # 6. SeatType=ALL + Submit
    soup = _submit(session, soup, year, rnd)

    table = soup.find('table', id=lambda x: x and 'GridView' in x)
    if table is None:
        return None, 'no GridView table in result page'

    df = pd.read_html(StringIO(str(table)))[0]
    df = df.dropna(how='all').copy()
    df['Year'] = year
    df['Round'] = rnd
    return df, None


def discover_rounds(session, year):
    """Return list of round numbers available for a year."""
    r = session.get(URL, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')
    soup = _post(session, soup, {F_YEAR: year}, F_YEAR)
    return [v for v, _ in _options(soup, F_ROUND) if v not in ('', '0')]


def main():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
    })

    summary = []
    for year in DEFAULT_YEARS:
        try:
            rounds = discover_rounds(session, year)
        except Exception as e:
            print(f'[{year}] ✗ discover_rounds failed: {e}')
            continue
        print(f'\n[{year}] rounds available: {rounds}')

        for rnd in rounds:
            out = RAW / f'{year}_R{rnd}.csv'
            if out.exists():
                df = pd.read_csv(out)
                print(f'  R{rnd}: ✓ already cached ({len(df):,} rows)  → {out.name}')
                summary.append((year, rnd, len(df), 'cached'))
                continue

            print(f'  R{rnd}: scraping ...', end=' ', flush=True)
            t0 = time.time()
            try:
                df, err = scrape_year_round(session, year, rnd)
            except Exception as e:
                print(f'✗ exception: {e}')
                summary.append((year, rnd, 0, f'exc:{e}'))
                continue
            if df is None:
                print(f'✗ {err}')
                summary.append((year, rnd, 0, err))
                continue
            df.to_csv(out, index=False)
            print(f'✓ {len(df):,} rows  ({time.time()-t0:.1f}s)  → {out.name}')
            summary.append((year, rnd, len(df), 'ok'))

    print('\n' + '=' * 64)
    print(f'Summary: {len(summary)} (year, round) attempts')
    print('=' * 64)
    total_rows = 0
    for y, r, n, status in summary:
        flag = '✓' if status in ('ok', 'cached') else '✗'
        print(f'  {flag}  {y} R{r:<2}  {n:>7,} rows  ({status})')
        total_rows += n
    print(f'\n  Total rows across all (year, round): {total_rows:,}')


if __name__ == '__main__':
    main()
