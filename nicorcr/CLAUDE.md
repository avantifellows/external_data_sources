# CLAUDE.md — nicorcr

Orientation for the NIC OR-CR pipeline (HBTU; MMMUT pending). Read
`../CLAUDE.md` first.

- `scripts/sources.py` lists every report (board, portal, exact link title,
  year). A report link opened directly lands on NIC's error page; follow it
  from the portal with the portal as Referer (`fetch_reports.py`).
- `scripts/build_clean.py` normalises headers that differ by year
  ("Program" vs "Academic Program Name", "Opening Rank" vs "Opening CRL
  Rank") and splits categories like uptac/.
- Raw HTML gitignored; GCS canonical (`fetch_raw()`).
