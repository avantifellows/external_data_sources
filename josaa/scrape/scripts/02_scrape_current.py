#!/usr/bin/env python3
"""
02_scrape_current.py — Scrape JoSAA 2025 (current cycle) Opening/Closing Ranks.

Source: https://josaa.admissions.nic.in/applicant/SeatAllotmentResult/CurrentORCR.aspx

Differences from archive endpoint:
  - No Year dropdown (it's the current cycle, year is implicit)
  - SeatType field is named `ddlSeattype` (lowercase 't'), not `ddlSeatType`
  - Otherwise the cascading-postback dance is identical

The current cycle's year is set in CURRENT_YEAR below — bump when JoSAA rolls forward.

Output: extracted_data/raw/<year>_R<round>.csv  — same schema as archive scrape.
"""
from __future__ import annotations
import time
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

URL = 'https://josaa.admissions.nic.in/applicant/SeatAllotmentResult/CurrentORCR.aspx'
CURRENT_YEAR = '2025'

HERE     = Path(__file__).resolve().parent
PIPELINE = HERE.parent
RAW      = PIPELINE / 'extracted_data' / 'raw'
RAW.mkdir(parents=True, exist_ok=True)

PAUSE_SEC = 0.6

F_ROUND   = 'ctl00$ContentPlaceHolder1$ddlroundno'
F_INSTYPE = 'ctl00$ContentPlaceHolder1$ddlInstype'
F_INST    = 'ctl00$ContentPlaceHolder1$ddlInstitute'
F_BRANCH  = 'ctl00$ContentPlaceHolder1$ddlBranch'
F_SEAT    = 'ctl00$ContentPlaceHolder1$ddlSeattype'   # NB: lowercase 't' in this endpoint
F_SUBMIT  = 'ctl00$ContentPlaceHolder1$btnSubmit'


def _hidden(soup):
    return {tag['name']: tag.get('value', '')
            for tag in soup.find_all('input', type='hidden') if tag.get('name')}


def _options(soup, name):
    sel = soup.find('select', attrs={'name': name})
    return [(o.get('value', ''), (o.text or '').strip()) for o in (sel.find_all('option') if sel else [])]


def _post(session, soup, updates, event_target):
    data = _hidden(soup)
    data.update(updates)
    data['__EVENTTARGET'] = event_target
    data['__EVENTARGUMENT'] = ''
    time.sleep(PAUSE_SEC)
    r = session.post(URL, data=data, timeout=60)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'lxml')


def _submit(session, soup, rnd):
    data = _hidden(soup)
    data.update({
        F_ROUND: rnd,
        F_INSTYPE: 'ALL', F_INST: 'ALL', F_BRANCH: 'ALL', F_SEAT: 'ALL',
        F_SUBMIT: 'Submit',
    })
    data.pop('__EVENTTARGET', None)
    data.pop('__EVENTARGUMENT', None)
    time.sleep(PAUSE_SEC)
    r = session.post(URL, data=data, timeout=120)
    r.raise_for_status()
    return BeautifulSoup(r.text, 'lxml')


def scrape_round(session, rnd):
    r = session.get(URL, timeout=30); r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')
    round_opts = [v for v, _ in _options(soup, F_ROUND) if v not in ('', '0')]
    if rnd not in round_opts:
        return None, f'round {rnd} not available; options={round_opts}'
    soup = _post(session, soup, {F_ROUND: rnd}, F_ROUND)
    soup = _post(session, soup, {F_ROUND: rnd, F_INSTYPE: 'ALL'}, F_INSTYPE)
    soup = _post(session, soup, {F_ROUND: rnd, F_INSTYPE: 'ALL', F_INST: 'ALL'}, F_INST)
    soup = _post(session, soup, {F_ROUND: rnd, F_INSTYPE: 'ALL', F_INST: 'ALL', F_BRANCH: 'ALL'}, F_BRANCH)
    soup = _submit(session, soup, rnd)

    table = soup.find('table', id=lambda x: x and 'GridView' in x)
    if table is None:
        return None, 'no GridView table in result page'
    df = pd.read_html(StringIO(str(table)))[0].dropna(how='all').copy()
    df['Year'] = CURRENT_YEAR
    df['Round'] = rnd
    return df, None


def discover_rounds(session):
    r = session.get(URL, timeout=30); r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')
    return [v for v, _ in _options(soup, F_ROUND) if v not in ('', '0')]


def main():
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36',
    })
    rounds = discover_rounds(session)
    print(f'[{CURRENT_YEAR}] rounds available: {rounds}')

    summary = []
    for rnd in rounds:
        out = RAW / f'{CURRENT_YEAR}_R{rnd}.csv'
        if out.exists():
            df = pd.read_csv(out)
            print(f'  R{rnd}: ✓ already cached ({len(df):,} rows)  → {out.name}')
            summary.append((rnd, len(df), 'cached'))
            continue
        print(f'  R{rnd}: scraping ...', end=' ', flush=True)
        t0 = time.time()
        try:
            df, err = scrape_round(session, rnd)
        except Exception as e:
            print(f'✗ exception: {e}')
            summary.append((rnd, 0, f'exc:{e}'))
            continue
        if df is None:
            print(f'✗ {err}')
            summary.append((rnd, 0, err))
            continue
        df.to_csv(out, index=False)
        print(f'✓ {len(df):,} rows  ({time.time()-t0:.1f}s)  → {out.name}')
        summary.append((rnd, len(df), 'ok'))

    print('\n' + '=' * 64)
    print(f'JoSAA {CURRENT_YEAR} summary:')
    for rnd, n, status in summary:
        flag = '✓' if status in ('ok', 'cached') else '✗'
        print(f'  {flag}  R{rnd:<2}  {n:>7,} rows  ({status})')


if __name__ == '__main__':
    main()
