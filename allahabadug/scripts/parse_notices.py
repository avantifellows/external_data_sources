"""
Read one University of Allahabad UG cut-off notice (text PDF).

Each notice is one programme x one round: a table of social category ->
CUET-UG computed marks. The marks are printed as a number ("519.28"), a
range ("362 - 371", "276 to 278": the band admitted that round; the low end
is the cut-off), "378 & Above" / "312 and Above", or "All" (every
registered candidate in that category was offered a seat).

Quirks handled here:
- the programme is read from the notice's heading, never the file name
  ("BA_First Merit (1).pdf" is the B.P.A. Music notice);
- B.A. notices are bilingual; the English table is parsed;
- a category label can wrap onto the next line ("Unreserved\\n(UR)", "UR
  Category\\n(Unreserved)"), with the marks on either line;
- the fee-window dates and times ("02/08/2025", "6:00 PM", "14th August
  2025") sit on the same lines and are removed before reading marks;
- some notices carry no round number (B.Sc. Maths): build_clean.py orders
  those by notice date.

Scanned notices (no text layer) are not read here: build_clean.py takes
them from the reviewed transcription in extracted/.
"""
from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
           "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
           "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
           "fifteenth": 15}

# heading text -> programme (first match wins)
PROGRAMS = [
    (r"B\.\s?P\.\s?A\.", "B.P.A. (Music)"),
    (r"Programme in Management|BBA\s*&\s*MBA", "BBA-MBA (5-year integrated)"),
    (r"DISASTER MANAGEMENT|Disaster Management", "Disaster Management and Environmental Studies (5-year integrated)"),
    (r"B\.Sc\.\s*\(Maths\)", "B.Sc. (Maths)"),
    (r"B\.Sc\.\s*Biology|Science \(Bio\)", "B.Sc. (Biology)"),
    (r"B\.\s?Com", "B.Com"),
    (r"B\.A\. Admission", "B.A."),
]

CATEGORY = [
    (r"\bUR\b|Unreserved", "UR"),
    (r"\bEWS\b|Economically Weaker", "EWS"),
    (r"\bOBC(?:-NCL)?\b|Other Backward", "OBC"),
    (r"\bSC\b|Schedule[d]? Caste", "SC"),
    (r"\bST\b|Schedule[d]? Tribe", "ST"),
]
NUM = r"\d{2,3}(?:\.\d+)?"
MARKS = re.compile(
    rf"(?P<lo>{NUM})\s*(?:-|–|to)\s*(?P<hi>{NUM})"
    rf"|(?P<one>{NUM})(?:\s*(?:&|and)\s*A(?:bo|vo)ve)?"
    rf"|(?P<all>\bAll\b)", re.I)
NOISE = re.compile(
    r"\d{1,2}/\d{1,2}/\d{4}"                              # 02/08/2025
    r"|\d{1,2}:\d{2}\s*(?:AM|PM)?(?:\s*\(Midnight\))?"     # 6:00 PM
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:July|Aug|Sept?|Oct)[a-z]*\.?(?:\s*,?\s*\d{4})?"
    r"|\(?\d{2}:\d{2}\s*(?:AM|PM)\)?"
    r"|\b20\d\d\b", re.I)
MONTH = {"07": 7, "08": 8, "09": 9, "10": 10}


def text_of(pdf: Path) -> str:
    return subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout


def program_of(text: str) -> str | None:
    head = text[:3000]
    return next((p for pat, p in PROGRAMS if re.search(pat, head)), None)


def table_part(text: str, program: str | None) -> str:
    """The English cut-off table: B.A. notices print Hindi first."""
    if program == "B.A.":
        i = text.find("Merit / Cut-off Marks")
        if i >= 0:
            return text[i:]
    m = re.search(r"Cut-?off Marks|CUET-UG[- ]?20\d\d\s*marks|Social Category", text, re.I)
    return text[m.start():] if m else text


def round_of(text: str, name: str) -> int | None:
    for src in (text, name.replace("_", " ")):
        if src is not text:
            # file names carry the round bare: "Notice_7TH", "BPA_MUSIC_4THCUTOFF"
            m = re.search(r"(?<![\d/])(\d{1,2})\s*(?:st|nd|rd|th)(?=\W|cut|merit|list|$)", src, re.I)
            if m:
                return int(m.group(1))
        m = re.search(r"\b(\d{1,2})\s*(?:st|nd|rd|th)\b\s*(?:Merit|Cut[- ]?off|cutoff|list)", src, re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"\b(" + "|".join(ORDINAL) + r")\b\s*(?:Merit|Cut[- ]?off|list)", src, re.I)
        if m:
            return ORDINAL[m.group(1).lower()]
    return None


def year_of(text: str) -> int | None:
    m = re.search(r"CUET[- ]UG[- ]?(20\d\d)", text)
    return int(m.group(1)) if m else None


def date_of(text: str) -> date | None:
    m = re.search(r"Date\s*[:\-]?\s*(\d{1,2})[./](\d{1,2})[./](20\d\d)", text)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.search(r"(July|August|September|October)\s+(\d{1,2}),\s*(20\d\d)", text)
    if m:
        return date(int(m.group(3)), ["July", "August", "September", "October"].index(m.group(1)) + 7, int(m.group(2)))
    return None


def _cat(line: str) -> str | None:
    return next((c for pat, c in CATEGORY if re.search(pat, line)), None)


def _marks(line: str):
    head = NOISE.sub(" ", line)
    head = re.sub(r"^\s*\d+\.\s*", "", head)      # serial number "1."
    head = re.sub(r"\((?:[A-Z\-]+|Unreserved)\)", " ", head)  # "(OBC-NCL)"
    m = None
    for m in MARKS.finditer(head):
        pass
    return m


def _cell_like(line: str) -> bool:
    """a table row's spill-over (marks, dates, times), not prose or a URL"""
    if "http" in line or "@" in line:
        return False
    words = re.findall(r"[A-Za-z]{3,}", NOISE.sub(" ", line))
    ok = {"and", "above", "avobe", "from", "till", "schedule", "scheduled", "caste",
          "tribe", "other", "backward", "classes", "economically", "weaker", "section"} | set(ORDINAL)
    return len([w for w in words if w.lower() not in ok]) <= 1


def rows_of(text: str) -> list[dict]:
    lines = [l for l in text.splitlines() if l.strip()]
    # table headings and notice titles ("Cut-off Marks for OBC and Schedule
    # Caste ...") name categories but carry no marks of their own
    lines = [l for l in lines if not re.search(
        r"Category\s+.*(Marks|Cut-?off)|Sl\. No\.|Start Date|Cut-?off Marks (for|and)|Merit or Cut", l, re.I)]
    used, out = set(), []
    for i, line in enumerate(lines):
        cat, m = _cat(line), _marks(line)
        if cat is None or i in used:
            continue
        if m is None:
            # wrapped label: the marks sit on the line above or below, which
            # carries no category of its own
            # labels wrap DOWNWARD from the marks line ("Other  Fourth  201 and
            # above" / "Backward" / "Caste (OBC"), so look up first, two lines
            # at most when the line between is only label text
            above2 = i >= 2 and _marks(lines[i - 1]) is None
            for j in (i - 1, *( [i - 2] if above2 else [] ), i + 1):
                if 0 <= j < len(lines) and j not in used and _cat(lines[j]) is None \
                        and _cell_like(lines[j]):
                    m = _marks(lines[j])
                    if m:
                        used.add(j)
                        break
        if m is None:
            continue
        used.add(i)
        if m["all"]:
            out.append({"category": cat, "low": None, "high": None, "all": True})
        elif m["lo"]:
            lo, hi = float(m["lo"]), float(m["hi"])
            out.append({"category": cat, "low": min(lo, hi), "high": max(lo, hi), "all": False})
        else:
            out.append({"category": cat, "low": float(m["one"]), "high": None, "all": False})
    return out


def parse(pdf: Path) -> dict:
    text = text_of(pdf)
    program = program_of(text)
    table = table_part(text, program)
    return {"file": pdf.name, "program": program, "year": year_of(text),
            "round_printed": round_of(table if program == "B.A." else text, pdf.name),
            "date": date_of(text), "rows": _dedupe(rows_of(table)), "chars": len(text.strip())}


def _dedupe(rows):
    """bilingual notices print the same table twice"""
    seen, out = set(), []
    for r in rows:
        k = tuple(sorted(r.items()))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out
