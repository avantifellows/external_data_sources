# KCET concepts in 60 seconds

KCET is Karnataka's state engineering entrance and counselling process,
administered by the Karnataka Examinations Authority (KEA). The table records
the last rank allotted for each college, program, reservation bucket, and
domicile pool in the 2025 Third Round.

The two official PDFs are separate merit pools:

- `GEN`: Rest of Karnataka.
- `HK`: the Article 371(j) Kalyana Karnataka pool.

Do not compare their ranks as if they were one list. Category codes also differ:
GEN uses codes such as `GM`, `2AG`, and `SCG`; HK uses `GMH`, `2AH`, and `SCH`.
Only cells with an allotted rank are stored—`--` source cells do not become rows.

Ranks can contain fractions such as `.25`, `.5`, `.75`, and `.875`. Preserve
the exact FLOAT value. `course_name_raw` supports source auditing;
`course_name` repairs extraction formatting while preserving meaningful degree
prefixes and specialization wording.

For reproducibility, both cutoff PDFs, the official 2025 draft seat-matrix PDF,
the parsed tall CSV, and the clean Parquet live under
`gs://avantifellows-external-data/kcet/`. The committed college-type codemap is
derived from those raw files; unresolved codes deliberately remain Unknown.
