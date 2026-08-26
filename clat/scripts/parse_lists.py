"""
Parse the final (5th) list PDFs into extracted/clat_admitted_2026.csv —
one row per provisionally-admitted candidate seat.

Each PDF has two sections:
  "Provisional 5th List"            fresh 5th-round allottees (no status col)
  "Status of provisionally admitted
   students in the fourth list"     carryovers, status ∈ {Provisionaly
                                    Admitted (sic), Vacant}

Admitted = fresh allottees + carryovers with status 'Provisionaly Admitted'.
'Vacant' rows are candidates who exited — their ranks must NOT shape a
closing rank, which is exactly the mistake a naive scrape of these PDFs
would make.

Row anatomy:  {sl} {air} {admit_card_9digits} {vertical} [{horizontals…}] [status]
  arrows:      'OBC -> General W-OBC' means the candidate was ADMITTED AGAINST
               the right-hand vertical (a cross-category shift during
               upgrades); the effective category is the post-arrow one, the
               pre-arrow original is kept in vertical_before_shift.
  vertical:    the seat's category column (General, EWS, OBC, SC, ST, and
               state codes like GC-KA, BC-A-AP, SC-AP-G2 …)
  horizontals: overlay reservations on that seat (W = women, PWD*, NCC-XX,
               CAP-XX, ESP-XX …) — kept verbatim, space-joined.

No candidate identifiers are carried into the output beyond the AIR needed
to aggregate closings; admit-card numbers stay in the raw PDFs only.
"""
from __future__ import annotations

import csv
import re
import warnings
from pathlib import Path
import sys

import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import EXTRACTED, FINAL_LIST, RAW

warnings.filterwarnings("ignore")

ROW = re.compile(r"\s*\d+\s+(\d+)\s+(\d{9})\s+(.+?)\s*$")
STATUS = re.compile(r"(Provisional?y Admitted|Vacant)\s*$")

# filename → program. Default (no suffix) is the flagship B.A. LL.B. (Hons.).
PROGRAM_SUFFIXES = [
    ("BScLLBHonsCriminologyandForensic", "B.Sc. LL.B. (Hons.) Criminology and Forensic Science"),
    ("BScLLBHonsCyberSecurity", "B.Sc. LL.B. (Hons.) Cyber Security"),
    ("BBALLBHonours", "B.B.A. LL.B. (Hons.)"),  # MNLU Nagpur spells it out
    ("BBALLBHons", "B.B.A. LL.B. (Hons.)"),
    ("BBALLB", "B.B.A. LL.B. (Hons.)"),
    ("BComLLBHons", "B.Com. LL.B. (Hons.)"),
    ("BComLLB", "B.Com. LL.B. (Hons.)"),
    ("BALLBHons", "B.A. LL.B. (Hons.)"),
    ("BALLB", "B.A. LL.B. (Hons.)"),
]


def college_and_program(path: Path, pdf) -> tuple[str, str]:
    stem = path.stem[3:].rsplit("-", 1)[0]  # drop 'UG-' and '-2026'
    program = "B.A. LL.B. (Hons.)"
    for suf, prog in PROGRAM_SUFFIXES:
        if stem.endswith(suf):
            program = prog
            break
    # college display name comes from the PDF header, not the squashed filename
    text = pdf.pages[0].extract_text() or ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # header: CONSORTIUM… / P.O. Bag… / Provisional 5th List… / <college name>
    college = stem
    for i, l in enumerate(lines):
        if l.startswith("Provisional") and i + 1 < len(lines):
            college = lines[i + 1]
            break
    # multi-program NLUs append the programme to the header line — strip it,
    # the programme already comes from the filename
    college = re.sub(r"\s*[-–]\s*B[\.\s]?(A|B|Sc|Com)[^-]*$", "", college)
    college = re.sub(r"\s+B\.?Sc\.?\s?\.?\s*LL.*$", "", college)
    return college.strip().rstrip(",-– "), program


def parse_cutoff_table(pdf, college, program):
    """Each PDF ends with the consortium's own 'Cut-Off Rank Table' —
    category label, seats, AIR cut-off, category-rank cut-off. This is the
    OFFICIAL aggregation (overlay admits are attributed to the overlay row,
    e.g. a PwD admit counts under PWD, not under their vertical) and is the
    number the app must show. '**' = seats existed but no cutoff published
    (unfilled or overlay-only)."""
    rows, grab = [], False
    for page in pdf.pages:
        for line in (page.extract_text() or "").splitlines():
            if re.search(r"Cut-?Off Rank Table", line, re.I):
                grab = True
                continue
            if not grab:
                continue
            m = re.match(r"\s*([A-Za-z].*?)\s+(\d+)\s+(\d+|\*+)\s+(\d+|\*+)\s*$", line)
            if m and not line.strip().startswith("Reservation"):
                label = m.group(1).strip()
                codes = [c for c in re.findall(r"\(([^()]+)\)", label)
                         if re.fullmatch(r"[A-Z][A-Za-z0-9&\- ]{1,20}", c)]
                # PDF line wrap can truncate long labels ("…freedom fighter
                # Or"), colliding several categories onto one visible label —
                # suffix an occurrence number so no two rows merge silently.
                seen = [r for r in rows if r[3] == label or
                        (r[3].startswith(label) and "#" in r[3])]
                if not codes and seen:
                    label = f"{label} #{len(seen) + 1}"
                rows.append([2026, college, program, label,
                             codes[-1] if codes else label,
                             int(m.group(2)),
                             None if "*" in m.group(3) else int(m.group(3)),
                             None if "*" in m.group(4) else int(m.group(4))])
    return rows


def main() -> None:
    out_rows = []
    cutoff_rows = []
    files = sorted((RAW / "pdf" / f"list{FINAL_LIST}").glob("UG-*.pdf"))
    print(f"parsing {len(files)} final-list pdfs")
    for path in files:
        pdf = pdfplumber.open(path)
        college, program = college_and_program(path, pdf)
        in_carryover = False
        n_fresh = n_carry = n_vacant = 0
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if "Status of provisionally admitted" in line:
                    in_carryover = True
                    continue
                m = ROW.match(line)
                if not m:
                    continue
                air, rest = int(m.group(1)), m.group(3)
                st = STATUS.search(rest)
                if st:
                    rest = rest[: st.start()].strip()
                if in_carryover:
                    if not st or st.group(1) == "Vacant":
                        n_vacant += st is not None and st.group(1) == "Vacant"
                        if not st:
                            # carryover rows always carry a status; a bare row
                            # here is a parse surprise worth hearing about
                            print(f"  WARN {path.name}: statusless carryover row (AIR {air})")
                        continue
                    n_carry += 1
                    section = "carryover_list4"
                else:
                    n_fresh += 1
                    section = "fresh_list5"
                before = ""
                if "->" in rest:
                    pre, post = [x.strip() for x in rest.split("->", 1)]
                    before, rest = pre.split()[0], post
                toks = rest.split()
                vertical = toks[0] if toks else ""
                horizontal = " ".join(toks[1:])
                out_rows.append([2026, college, program, air, vertical,
                                 before, horizontal, section, path.name])
        cutoff_rows += parse_cutoff_table(pdf, college, program)
        pdf.close()

    EXTRACTED.mkdir(exist_ok=True)
    with open(EXTRACTED / "clat_cutoff_tables_2026.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "college", "program", "category_label",
                    "category_code", "seats", "air_cutoff",
                    "category_rank_cutoff"])
        w.writerows(cutoff_rows)
    print(f"official cut-off table rows: {len(cutoff_rows):,}")
    with open(EXTRACTED / "clat_admitted_2026.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "college", "program", "air", "vertical_raw",
                    "vertical_before_shift", "horizontal_raw", "section",
                    "source_file"])
        w.writerows(out_rows)
    print(f"admitted rows: {len(out_rows):,} → extracted/clat_admitted_2026.csv")


if __name__ == "__main__":
    main()
