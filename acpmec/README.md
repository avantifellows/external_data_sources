# acpmec — Gujarat medical, dental, AYUSH, nursing & allied institutes

Gujarat's admission committees for professional medical courses publish, for
each admission cycle, the list of institutes they admit to: with type
(government / grant-in-aid / self-financed), affiliating university, annual
intake and fees. This source keeps the **2026-27** lists for every degree
course that is not MBBS:

| course_code | course | committee | institutes |
|---|---|---|---|
| BDS | Bachelor of Dental Surgery | UG medical (NEET) | 13 |
| BAMS | Ayurveda | UG medical (NEET) | 43 |
| BHMS | Homoeopathy | UG medical (NEET) | 48 |
| BSC_NURSING | B.Sc. Nursing | nursing & allied | 299 |
| BPT | Physiotherapy | nursing & allied | 68 |
| BO | Optometry | nursing & allied | 8 |
| BASLP | Audiology & Speech-Language Pathology | nursing & allied | 3 |
| BOT | Occupational Therapy | nursing & allied | 1 |
| BOP | Prosthetics & Orthotics | nursing & allied | 1 |
| BNYS | Naturopathy & Yogic Sciences | nursing & allied | 1 |

MBBS is left out on purpose: `nmc_fact_mbbs_seats` already lists every MBBS
college. GNM / ANM nursing diplomas are left out: not degree courses.

Tables:

- `acpmec_dim_institutes` (485 rows, one per course x institute, 2026-27).
  See `schemas/acpmec_dim_institutes.yaml`.
- `acpmec_fact_last_ranks` (91,063 rows): the last rank admitted per course
  x institute x quota x category in 2025-26. Nursing & allied: the
  committee's merit-list rank (Class 12 marks), rounds 1-8, incl. the GNM /
  ANM diplomas. MBBS, BDS, BAMS, BHMS: NEET score, rank and percentile of the
  last student admitted, final list. See `schemas/acpmec_fact_last_ranks.yaml`.

## Run

```bash
pip install -r requirements.txt
python3 scripts/build_clean.py      # fetches raw/ from GCS if empty
python3 scripts/build_last_ranks.py
python3 scripts/upload_to_gcs.py
python3 scripts/load_bq.py
```

## Gaps, stated

- `intake` is null where the list prints none: the Occupational Therapy file
  (no intake column at all) and three blank cells (two optometry schools, one
  physiotherapy college). Each file's printed total still equals the parsed sum.
- BDS has no university column in its seat matrix and no fee: null.
- Addresses are not kept: the nursing & allied files print them in Gujarati
  and the extracted text is garbled. District comes from AISHE downstream.
- Last ranks are 2025-26 (the latest complete cycle) while the institute
  lists are 2026-27: a college new in 2026 has no last rank (9 nursing, 2
  BHMS), and six 2025 institutes are not on the 2026 lists.
- `seat_pool = 'M'` (labels like `HVNUR -M`) is a pool the PDFs do not
  explain. It is kept apart, not guessed at.
- One BDS college is in Daman (`DAMD`), not Gujarat: it is in Gujarat's
  counselling.
