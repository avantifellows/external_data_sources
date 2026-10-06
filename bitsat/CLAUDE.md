# CLAUDE.md — bitsat

BITSAT cut-offs from BITS's single cut-off page. Read `../CLAUDE.md` first.
build_clean.py walks `<div id="YYYY-YYYY">` blocks and their innermost
tables; two layouts (pre-2020 per-campus tables, 2020+ Campus|Program
tables), a malformed 2021-22 wrapper row (skipped), note rows (skipped).
Any other unread row fails the build.
