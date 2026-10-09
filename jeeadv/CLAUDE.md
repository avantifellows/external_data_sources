# CLAUDE.md — jeeadv

JEE (Advanced) marks at every 100th rank, from the JIC reports' sections
6.8–6.13. Read `../CLAUDE.md` first. build_clean.py reads pdftotext -layout
of the first 60 pages, finds the six headings (skipping the contents page's
dot-leader copies), takes (rank, score) pairs from digit-only lines, keeps
ranks ≡ 1 mod 100 plus KNOWN_MISPRINTS. Adding a year = a RawFile row
(check its max marks in the report: "The top ranker scored N out of 360").
The reports also print toppers' names and roll numbers — never extract those.
