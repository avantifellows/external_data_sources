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
# 8-digit form is "1111.0100" — code . code, with description and (optional)
# NCO 2004 code at end (format e.g. "1111.10").
RE_FULL = re.compile(
    r"^\s*(\d{4}\.\d{4})\s+(.+?)\s+(\d{4}\.\d{2})?\s*$"
)


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

    for line in body.splitlines():
        s = line.rstrip()

        # Set the current label so loose-form lines that follow are interpreted
        # at the right hierarchy level. The PDF puts "Sub-" on one line and
        # "Division" on the next, so look for substrings.
        stripped = s.strip()
        if stripped.startswith("Division"):
            m = RE_DIV.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                divs[code] = name
                current_label = "Group_lookahead"  # next 2-digit line is sub-div
                continue
        if stripped.startswith("Sub-"):
            current_label = "Sub-Division"
            m = RE_SUB.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                subs[code] = name
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
                continue
        if stripped.startswith("Family"):
            current_label = "Family"
            m = RE_FAMILY.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                families[code] = name
                continue

        # 8-digit detailed line (always present with NNNN.NNNN form)
        m = RE_FULL.match(s)
        if m:
            full = m.group(1)
            name = m.group(2).strip()
            nco04 = m.group(3) or ""
            fulls.append((full, name, nco04))
            current_label = None
            continue

        # Loose-form line (no leading label) — interpret based on current_label
        if current_label == "Sub-Division":
            m = RE_SUB_LOOSE.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                if code not in subs:
                    subs[code] = name
                continue
        if current_label == "Group":
            m = RE_GROUP_LOOSE.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                if code not in groups:
                    groups[code] = name
                continue
        if current_label == "Family":
            m = RE_FAMILY_LOOSE.match(s)
            if m:
                code, name = m.group(1), m.group(2).strip()
                if code not in families:
                    families[code] = name
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
