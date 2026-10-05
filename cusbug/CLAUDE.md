# CLAUDE.md — cusbug

Central University of South Bihar UG (CUET) cut-offs. Read `../CLAUDE.md`
first. Layout as in `allahabadug/`: sources.py (every file + role),
build_clean.py (parses text rounds, merges extracted/manual_transcriptions.csv),
upload_to_gcs.py, load_bq.py.

Gotchas: programme names wrap over lines (canonicalised by keyword, next line
before previous); "--" / "-" = no seats that round (no row); "All" = all
registered candidates.
