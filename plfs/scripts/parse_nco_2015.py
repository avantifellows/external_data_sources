"""
Parse NCO 2015 Vol-I Concordance Table into hierarchical CSVs.

Source PDF: raw/external/NCO_2015_VolI.pdf (DGE, Min. of Labour & Employment)
Extracted text: raw/external/NCO_2015_VolI.txt (via pdftotext -layout)

The concordance table (pages 33-238) is structured as:
    Division     1        <Title>
    Sub-Division 11       <Title>
    Group        111      <Title>
    Family       1111     <Title>
                 1111.0100 <Title>          <NCO-2004-code>

Outputs:
    codemaps/nco_division.csv     (1-digit)
    codemaps/nco_subdivision.csv  (2-digit)
    codemaps/nco_group.csv        (3-digit)  <- PLFS uses this level
    codemaps/nco_family.csv       (4-digit)
    codemaps/nco_full.csv         (8-digit, with NCO-2004 mapping)
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "raw" / "external" / "NCO_2015_VolI.txt"
OUT = ROOT / "codemaps"

# Table starts after the cover line "CONCORDANCE TABLE / OF / NCO 2015 ..." on
# the first page of section 2. The Alphabetical Index follows on page 239.
START_MARKER = "CONCORDANCE TABLE"
END_MARKER = "Alphabetical Index"

# Regex for each level. The "Division/Sub-/Group/Family" labels are optional and
# may not appear on every line (continuation lines). Code = anchor.
RE_DIV = re.compile(r"^\s*Division\s+(\d)\s+(.+?)\s*$")
RE_SUB = re.compile(r"^\s*Sub-\s+(\d{2})\s+(.+?)\s*$")
RE_SUB_LOOSE = re.compile(r"^\s*(\d{2})\s{2,}([A-Z].+?)\s*$")
RE_GROUP = re.compile(r"^\s*Group\s+(\d{3})\s+(.+?)\s*$")
RE_GROUP_LOOSE = re.compile(r"^\s*(\d{3})\s{2,}([A-Z].+?)\s*$")
RE_FAMILY = re.compile(r"^\s*Family\s+(\d{4})\s+(.+?)\s*$")
RE_FAMILY_LOOSE = re.compile(r"^\s*(\d{4})\s{2,}([A-Z].+?)\s*$")
# A bare heading with no label word in the left column. The LEVEL IS THE CODE'S LENGTH - 2 digits
# is a sub-division, 3 a group, 4 a family - which is unambiguous here and, unlike the label word,
# is always present. See the note on the state machine in main().
RE_HEADING_LOOSE = re.compile(r"^\s*(\d{2,4})\s{2,}([A-Za-z].+?)\s*$")
# A wrapped title continues on the next line: indented, no code of any kind, may still carry the
# NCO-2004 column at the end.
RE_CONTINUATION = re.compile(r"^\s{6,}([A-Za-z(][^\d]*?)(?:\s{2,}\d{4}\.\d{2})?\s*$")
# 8-digit form is "1111.0100" — code . code, with description and (optional)
# NCO 2004 code at end (format e.g. "1111.10").
RE_FULL = re.compile(
    r"^\s*(\d{4}\.\d{4})\s+(.+?)\s+(\d{4}\.\d{2})?\s*$"
)


FULLS = object()   # sentinel: `pending` points at the 8-digit list rather than a dict


def main():
    text = SRC.read_text(encoding="utf-8")
    # restrict to concordance section
    start = text.find(START_MARKER)
    end = text.find(END_MARKER, start)
    if start < 0 or end < 0:
        raise SystemExit("Markers not found in NCO text")
    body = text[start:end]

    divs, subs, groups, families, fulls = {}, {}, {}, {}, []
    current_label = None  # "Division" | "Sub-Division" | "Group" | "Family"
    pending = None        # (dict, code) most recently captured, for wrapped-title continuation

    for line in body.split("\n"):
        s = line.rstrip()

        # A blank line ends any wrapped title. Without this, continuation text could attach to an
        # entry several rows away.
        if not s.strip():
            pending = None
            continue

        # Set the current label so loose-form lines that follow are interpreted
        # at the right hierarchy level. The PDF puts "Sub-" on one line and
        # "Division" on the next, so look for substrings.
        stripped = s.strip()
        if stripped.startswith("Division"):
            m = RE_DIV.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                divs[code] = name
                pending = (divs, code)
                current_label = "Group_lookahead"  # next 2-digit line is sub-div
                continue
        if stripped.startswith("Sub-"):
            current_label = "Sub-Division"
            m = RE_SUB.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                subs[code] = name
                pending = (subs, code)
                continue
            # bare "Sub-" line, or "Sub-Division" header - just set label
            continue
        if stripped == "Division":
            # continuation of a "Sub-/Division" multi-line label
            continue
        if stripped.startswith("Group"):
            current_label = "Group"
            m = RE_GROUP.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                groups[code] = name
                pending = (groups, code)
                continue
        if stripped.startswith("Family"):
            current_label = "Family"
            m = RE_FAMILY.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                families[code] = name
                pending = (families, code)
                continue

        # 8-digit detailed line (always present with NNNN.NNNN form)
        m = RE_FULL.match(s)
        if m:
            full = m.group(1)
            name = m.group(2).strip()
            nco04 = m.group(3) or ""
            fulls.append((full, name, nco04))
            pending = (FULLS, full)
            current_label = None
            continue

        # Loose-form heading with no label word in the left column.
        #
        # WHY THIS NO LONGER DEPENDS ON current_label. The previous version only accepted a bare
        # "NNNN  Title" line while current_label was already set to the matching level, and every
        # 8-digit line reset current_label to None. The PDF's label column is vertically centred
        # in its table cell, so pdftotext -layout sometimes emits the word "Family" on the row
        # BELOW its heading - or omits it. In those cases the heading arrived with the state
        # cleared and was silently dropped. Three real families were lost this way:
        #     2352 Special Needs Teachers, 7222 Tool Makers and Related Workers,
        #     8112 Mineral and Stone Processing Plant Operators
        # The code's own length says what level it is, always, so that is what routes it now.
        m = RE_HEADING_LOOSE.match(s)
        if m:
            code, name = m.group(1), m.group(2).strip()
            target = {2: subs, 3: groups, 4: families}[len(code)]
            if code not in target:
                target[code] = name
                pending = (target, code)
            current_label = None
            continue

        # Wrapped title. A heading or 8-digit entry whose name is too long for the column runs on
        # to the next line, and the old parser kept only the first line - which is why the
        # committed codemaps contain entries like "741,Electrical Equipment Installers and" and
        # "634,Subsistence Fishers, Hunters, Trappers and". The continuation is appended to
        # whatever was captured last, and is cleared by any blank line so text can never migrate
        # across entries.
        if pending is not None:
            m = RE_CONTINUATION.match(s)
            if m:
                tail = m.group(1).strip()
                if tail:
                    target, code = pending
                    if target is FULLS:
                        fulls[-1] = (fulls[-1][0], f"{fulls[-1][1]} {tail}", fulls[-1][2])
                    else:
                        target[code] = f"{target[code]} {tail}"
                continue

    # write outputs
    def dump_dict(name, d):
        p = OUT / f"{name}.csv"
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["code", "description"])
            for k in sorted(d):
                w.writerow([k, d[k]])
        print(f"  {name:18s} {len(d):>4} codes  -> {p.name}")

    dump_dict("nco_division", divs)
    dump_dict("nco_subdivision", subs)
    dump_dict("nco_group", groups)
    dump_dict("nco_family", families)

    p = OUT / "nco_full.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "description", "nco_2004_code"])
        for code, name, nco04 in fulls:
            w.writerow([code, name, nco04])
    print(f"  nco_full           {len(fulls):>4} codes  -> nco_full.csv")


if __name__ == "__main__":
    main()
