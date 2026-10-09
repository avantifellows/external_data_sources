# jeeadv — JEE (Advanced) marks at published ranks

**What**: the aggregate marks (Paper 1 + Paper 2, out of 360) scored by the
candidate at ranks 1, 101, 201, … of each JEE (Advanced) rank list — CRL,
GEN-EWS, OBC-NCL, SC, ST, CRL-PwD — for 2025 and 2026. It turns a student's
JEE (Advanced) marks into a rank range ("marks 150 → CRL rank 4,9xx–5,0xx").

**Source**: the Joint Implementation Committee report of each year,
[jeeadv.ac.in/reports/2025.pdf](https://jeeadv.ac.in/reports/2025.pdf) and
[2026.pdf](https://jeeadv.ac.in/reports/2026.pdf), Volume 1 sections 6.8–6.13
"Aggregate Total Marks with Different Ranks in …".

```
raw/jic_report_<year>.pdf  →  scripts/build_clean.py  →  clean/jeeadv_fact_marks_at_rank.parquet
        │ upload_to_gcs.py                                      │ upload_to_gcs.py, load_bq.py
gs://avantifellows-external-data/jeeadv/{raw,clean}/  →  avantifellows.external_data_sources.jeeadv_fact_marks_at_rank (1,200 rows)
```

## Reading it

- **Only every 100th rank is published**, not every candidate. For marks M,
  the best possible rank is (last published rank scoring more than M) + 1;
  the worst is (first published rank scoring less than M) − 1. Ranges are
  ~100 wide except at the top (marks fall steeply) and in sparse lists.
- **CRL-PwD has 3 (2025) / 4 (2026) points** — ranges there are hundreds wide.
- **2024 is left out on purpose**: its marks-to-rank curve was an outlier;
  2023, 2025 and 2026 trend alike (per the academic team).
- **Next year's paper shifts the marks needed for a rank.** This is what past
  years did, not a forecast.

## Quality gates (`build_clean.py`)

Every (year, list) table present from rank 1; ranks 1 mod 100 (anything
else is a footer or another table) except the named misprint; marks 0–max;
marks never rise as rank falls; a rank printed twice must carry the same
marks. Two misprints in the 2025 CRL table: rank 17301 printed twice (99 both
times; kept once) and 28402 where the row's other columns read x401 (kept as
printed). Cross-checked: all 1,200 points equal an independent transcription
of the same tables.
