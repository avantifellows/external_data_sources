# ndc — National Dental Commission dental colleges

Every BDS college in India from the National Dental Commission's college search
(dciindia.gov.in, formerly the Dental Council of India), with each college's
own details page.

```
python3 scripts/fetch.py         # list page + 330 details pages → raw/<date>/ (1 request/s, ~40 min, resumable)
python3 scripts/build_clean.py   # → clean/ndc_dim_dental_colleges.parquet, clean/ndc_fact_dental_seats.parquet
python3 scripts/upload_to_gcs.py # raw + clean → gs://avantifellows-external-data/ndc/   (gcs-handler key)
python3 scripts/load_bq.py       # → external_data_sources.ndc_dim_dental_colleges / ndc_fact_dental_seats
```

**Source.** `CollegeSearch.aspx?ColName=&CourseId=1&StateId=0` lists every
college with BDS: state, year established, Govt/Private and the 2025-26
permitted BDS seats. Each row's "View College Details" is an ASP.NET postback
that redirects to `SearchCollegeDetails.aspx?Id=<opaque id>`; `fetch.py` makes
the postback, follows the redirect and saves the page. `ndc_id` is that id.

**Tables (fetch of 2026-11-17).**
- `ndc_dim_dental_colleges`: 330 colleges in 28 states (267 private, 60 govt);
  27,914 permitted BDS seats for 2025-26 (list page).
- `ndc_fact_dental_seats`: college × course (BDS / MDS / PG Diploma) ×
  speciality, academic year 2026-27 only: approved, recognised, intake,
  permitted, admitted seats. 2026-27 permitted: BDS 27,464, MDS 7,640.

**Parse notes.**
- The details page names a college its own way ("V.S. Dental College" in the
  list is "Vokkaligara Sangha Dental College" on its page). `build_clean.py`
  checks every page names its list row's college; the 16 pairs that differ in
  words were checked by hand and are listed in `scripts/reviewed_name_pairs.json`.
- The seats grid shows 10 rows a page, newest year first. Only the first page
  is fetched, so only the newest year is complete; older years are dropped.
- The site prints one seat row twice (identical); exact duplicates are dropped.
- 11 colleges have no 2026-27 BDS row on that first page (PG-only institutions
  such as Army Hospital R&R and AFMC Pune, or a BDS row on a later page).

**Left out on purpose.** The principal's name and e-mail (a person), and the
hostel / dental-chair / built-area grids (their newest years are on later grid
pages). Shareability: open (official, institution-level only).
