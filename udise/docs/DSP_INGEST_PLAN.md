# UDISE+ DSP microdata — ingest plan (SUPERSEDED)

**This plan is done.** It was written before anything was built; the ingest it
describes shipped, and its "nothing is built yet" framing and two-year scope are
both wrong now. Kept only so links to it still resolve.

For the DSP microdata as it actually exists, read, in order:

1. [`../README.md`](../README.md#dsp-microdata-school-level) — what the pipeline is,
   how to run it, and how to add a new edition.
2. [`../schemas/README.md`](../schemas/README.md) — the UDISE+ primer, the five
   things that get DSP numbers wrong, the codemaps, what is deliberately not
   loaded, and the five things the data says that the codebooks do not.
3. The four schema YAMLs in [`../schemas/`](../schemas/) — `udise_dim_school_dsp`,
   `udise_fact_enrolment_dsp`, `udise_fact_teacher_dsp`,
   `udise_fact_facility_dsp`.

What actually shipped, against what this plan guessed:

| Plan said | Turned out |
|---|---|
| 2 editions held (2020-21, 2024-25) | **5** — 2022-23, 2023-24 and 2025-26 added later; 2021-22 still not held |
| one schema | **four layouts**; 2020-21 is a structural outlier and 2025-26 adds a `safety` group |
| BPL *and* EWS as the poverty variables | **BPL only** — EWS is published in 2023-24 alone, 25,100 schools |
| "profile first, stop there for a first PR" | held: profile + enrolment shipped first, teacher + facility/safety second |
| reconcile against a published total | done — 2024-25 social-category enrolment is **246,932,680**, matching Report 4000 exactly |
