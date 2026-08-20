# wbjee/

WBJEE (West Bengal) engineering counselling cutoffs — **2021-2026, six years
including the live 2026 cycle**.

| table | rows | grain |
|---|---|---|
| `wbjee_fact_cutoffs` | 21,936 | year × round × institute × program × seat-type × quota × category |

```
raw/WBJEE_<year>_ORCR.html   the OR-CR reports exactly as admissions.nic.in serves them
   │  scripts/build_clean.py   parse, classify college_type (whitelist), canonical categories,
   ▼                           unify TFW across its two encodings, per-year vocab kept verbatim
clean/wbjee_fact_cutoffs.parquet → GCS → external_data_sources.wbjee_fact_cutoffs
```

Three per-year facts the data carries rather than smooths over: 2021 has no
seat-type column (the WBJEE-vs-JEE(Main) seat split began 2022); 2026 merged
OBC-A/OBC-B into one 'OBC'; EWS appears only from 2025.

The fetch trick that matters: the report URLs' `enc` token must keep its `+`
LITERAL — percent-encoding it returns NIC's error page. Tokens for every year
are listed publicly at wbjeeb.nic.in/ewbjee/. Pharmacy 2026 is archived in
raw/, unparsed.

Anchor check: Jadavpur CSE (Open, Home State) closes at GMR 66-309 across all
six years and sweeps the five hardest government seats in 2026 — exactly the
reality any Bengali engineering aspirant would describe.
