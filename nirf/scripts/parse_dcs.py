"""
Parse the first-party NIRF haul (fetch_dcs.py) into extracted/ CSVs.

A. RANKING PAGES → extracted/nirf_rankings_official.csv
   - main pages: institute_id, name, city, state, score, rank
   - band pages: name, city, state only (NIRF publishes NO ids, scores or
     PDF links for rank-band institutes — the rows here carry rank_band
     like '101-150' and NULL institute_id/score)
   - "ALL" participant pages → extracted/nirf_participants.csv (names only)

B. DCS PDFs ("Data Submitted by Institution") → four CSVs:
   - dcs_placements.csv   per (edition, institute, program level, grad AY)
   - dcs_intake.csv       sanctioned intake per (edition, institute, level, AY)
   - dcs_strength.csv     actual student strength + demographics per level
   - dcs_institution.csv  institute name, PhD pursuing counts, faculty count

Parse notes (the ways this goes wrong):
  - A placement table has 10 columns for levels with lateral entry (UG-4Y)
    and 8 without; the program level is NOT inside the table — it's in the
    page text ("UG [4 Years Program(s)]: Placement & higher studies…"), so
    headers and tables are zipped in page order and a count mismatch is a
    loud warning, not a guess.
  - A placement table that starts at the foot of a page continues at the
    top of the next one WITHOUT its header row (IIT Bombay 2025: the UG-5Y
    table's header on page 1, its three rows on page 2). The continuation
    is joined to the table before it — same column count, rows starting
    with an academic year — instead of being dropped as an unknown table.
  - Median salary prints as '1300000(Thirteen Lakh )' — the leading integer
    is the value; the words are decoration.
  - '-' means "no such program that year", not zero. Kept as NULL.
  - Editions overlap: each PDF reports the 3 trailing academic years, and
    NIRF revises numbers between editions. Nothing is deduplicated here —
    build_clean.py applies the prefer-latest-edition rule.
"""
from __future__ import annotations

import csv
import re
import sys
import warnings
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")  # pdfplumber's CropBox chatter

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "raw" / "dcs" / "pages"
PDFS = ROOT / "raw" / "dcs" / "pdf"
OUT = ROOT / "extracted"

# band-page filename suffix → the rank band it holds, per discipline
# (Medical ranks 50, so its first band page is …Ranking100.html = 51-100)
BANDS = {
    "Engineering": {"150": "101-150", "200": "151-200", "300": "201-300"},
    "Medical": {"100": "51-100", "150": "101-150", "200": "151-200",
                "300": "201-300"},
    "University": {"150": "101-150", "200": "151-200", "300": "201-300"},
    "College": {"150": "101-150", "200": "151-200", "300": "201-300"},
    "Law": {},
}

PROGRAM_RE = re.compile(r"(UG|PG)\s*\[\s*(\d+(?:\.\d+)?)\s*Years?\s*Program")


def norm_level(raw: str) -> str:
    m = PROGRAM_RE.search(raw)
    if m:
        return f"{m.group(1)}-{m.group(2).rstrip('0').rstrip('.')}Y"
    if "integrated" in raw.lower():
        return "PG-Integrated"
    return raw.strip()


def to_int(cell) -> int | None:
    if cell is None:
        return None
    s = str(cell).strip()
    if s in ("", "-", "--", "NA", "N/A"):
        return None
    m = re.match(r"(\d+)", s.replace(",", ""))
    return int(m.group(1)) if m else None


AY_RE = re.compile(r"\d{4}-\d{2}")


# ── A. ranking pages ─────────────────────────────────────────────────────────

def clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.split(" More Details")[0]).strip()


def parse_pages() -> None:
    rankings, participants = [], []
    for disc_dir in sorted(PAGES.iterdir()):
        disc = disc_dir.name
        for f in sorted(disc_dir.glob("*.html")):
            m = re.match(r"(\d{4})_[A-Za-z]+Ranking(\w*)\.html", f.name)
            year, suffix = int(m.group(1)), m.group(2)
            soup = BeautifulSoup(f.read_text(errors="ignore"), "lxml")
            tbl = next((t for t in soup.find_all("table")
                        if not t.find_parent("table")), None)
            if tbl is None:
                continue
            body = tbl.find("tbody") or tbl
            for tr in body.find_all("tr", recursive=False):
                cells = [td.get_text(" ", strip=True)
                         for td in tr.find_all("td", recursive=False)]
                if not cells:
                    continue
                if suffix == "ALL":
                    # participant rows: [name, city, state] (sometimes a
                    # leading serial column)
                    row = cells[-3:] if len(cells) >= 3 else None
                    if row and row[0] and not row[0].isdigit():
                        participants.append([year, disc, clean_name(row[0]),
                                             row[1], row[2]])
                elif suffix == "":
                    if cells[0].startswith("IR") and len(cells) >= 6:
                        rankings.append([year, disc, cells[0],
                                         clean_name(cells[1]), cells[2],
                                         cells[3], cells[4], cells[5], None])
                else:
                    band = BANDS.get(disc, {}).get(suffix)
                    if band and len(cells) >= 3 and cells[-3]:
                        rankings.append([year, disc, None,
                                         clean_name(cells[-3]), cells[-2],
                                         cells[-1], None, None, band])
    OUT.mkdir(exist_ok=True)
    with open(OUT / "nirf_rankings_official.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ranking_year", "discipline", "institute_id",
                    "institute_name", "city", "state", "score", "rank",
                    "rank_band"])
        w.writerows(rankings)
    with open(OUT / "nirf_participants.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ranking_year", "discipline", "institute_name", "city",
                    "state"])
        w.writerows(participants)
    print(f"rankings: {len(rankings)} rows, participants: {len(participants)}")


# ── B. DCS PDFs ──────────────────────────────────────────────────────────────

def classify(table: list[list]) -> str:
    head = " ".join((c or "") for c in table[0]).replace("\n", " ")
    if "No. of Male" in head:
        return "strength"
    if "first year students" in head:
        return "placement"
    if head.startswith("Academic Year") and any(
            "Program" in (r[0] or "") for r in table[1:]):
        return "intake"
    return "other"


def parse_pdf(path: Path, edition: int, disc: str,
              placements, intakes, strengths, institutions) -> None:
    pdf = pdfplumber.open(path)
    inst_id = path.stem
    text0 = pdf.pages[0].extract_text() or ""
    # the portal's "Full Report" print (some institutes post that one on their
    # websites) puts the name on its own line, without the "[IR-…]" after it
    m = (re.search(r"Institute Name:\s*(.+?)\s*\[IR", text0)
         or re.search(r"Institute Name:\s*(.+)", text0))
    inst_name = re.sub(r"\s+", " ", m.group(1)).strip() if m else None

    phd_ft = phd_pt = faculty = None
    placement_hdrs: list[str] = []
    # the placement table a page ended on: (level_raw, level, wide)
    carry: tuple | None = None

    def add_placement_rows(rows, level_raw, level, wide):
        for row in rows:
            if not row[0] or not AY_RE.search(row[0]):
                continue
            if wide:
                (ay_in, fy_intake, fy_adm, ay_lat, lat_adm,
                 ay_grad, grad, placed, salary, higher) = row[:10]
            else:
                (ay_in, fy_intake, fy_adm,
                 ay_grad, grad, placed, salary, higher) = row[:8]
                ay_lat = lat_adm = None
            # the "Full Report" print brackets years: "(2019-20)"
            ay_in, ay_lat, ay_grad = (a.strip("() ") if isinstance(a, str) else a
                                      for a in (ay_in, ay_lat, ay_grad))
            placements.append([
                edition, disc, inst_id, inst_name, level,
                re.sub(r"\s+", " ", level_raw).strip(),
                ay_in, to_int(fy_intake), to_int(fy_adm),
                ay_lat, to_int(lat_adm),
                ay_grad, to_int(grad), to_int(placed),
                to_int(salary), to_int(higher)])

    for page in pdf.pages:
        text = page.extract_text() or ""
        # placement section headers, in page order
        # 2023 editions print "Higher Studies" in title case — match
        # case-insensitively or a whole edition parses level-less.
        placement_hdrs += [l for l in text.splitlines()
                           if "placement & higher studies" in l.lower()
                           and "Program" in l]
        mm = re.search(r"Number of faculty members entered\s+(\d+)", text)
        if mm:
            faculty = int(mm.group(1))
        if "Ph.D" in text:
            mm = re.search(r"Full Time\s+(\d+)", text)
            if mm and phd_ft is None:
                phd_ft = int(mm.group(1))
            mm = re.search(r"Part Time\s+(\d+)", text)
            if mm and phd_pt is None:
                phd_pt = int(mm.group(1))

        tables = [t for t in page.extract_tables() if t and t[0]]
        last_placement = None
        for ti, table in enumerate(tables):
            kind = classify(table)
            # a headerless continuation of the last page's placement table
            if (ti == 0 and carry and kind == "other"
                    and len(table[0]) == (10 if carry[2] else 8)
                    and AY_RE.search(table[0][0] or "")):
                add_placement_rows(table, *carry)
                carry = None
                continue
            if kind == "intake":
                ays = [c.strip() for c in table[0][1:] if c]
                for row in table[1:]:
                    level = norm_level(row[0] or "")
                    for ay, cell in zip(ays, row[1:]):
                        if AY_RE.fullmatch(ay) and to_int(cell) is not None:
                            intakes.append([edition, disc, inst_id, inst_name,
                                            level, row[0].replace("\n", " "),
                                            ay, to_int(cell)])
            elif kind == "strength":
                for row in table[1:]:
                    if not row[0] or "Program" not in row[0]:
                        continue
                    vals = [to_int(c) for c in row[1:13]]
                    vals += [None] * (12 - len(vals))
                    strengths.append([edition, disc, inst_id, inst_name,
                                      norm_level(row[0]),
                                      row[0].replace("\n", " ")] + vals)
            elif kind == "placement":
                if placement_hdrs:
                    level_raw = placement_hdrs.pop(0).split(":")[0]
                else:
                    level_raw = "UNKNOWN"
                    print(f"  WARN {path.name}: placement table with no "
                          f"section header on page {page.page_number}")
                level = norm_level(level_raw)
                wide = len(table[0]) == 10  # has the lateral-entry AY pair
                add_placement_rows(table[1:], level_raw, level, wide)
                if ti == len(tables) - 1:
                    last_placement = (level_raw, level, wide)
        # only a placement table that ENDS the page can continue on the next
        carry = last_placement
    if placement_hdrs:
        print(f"  WARN {path.name}: {len(placement_hdrs)} placement header(s) "
              f"had no matching table")
    institutions.append([edition, disc, inst_id, inst_name,
                         phd_ft, phd_pt, faculty])
    pdf.close()


def _sources() -> list[tuple[Path, str, str]]:
    """(pdf, pdf_source, source_url) for NIRF's CDN copies and the
    institutes' own website copies (fetch_website_dcs.py). A website copy of
    a PDF NIRF also hosts is skipped: nirfindia.org wins."""
    from sources import WEBSITE_MANIFEST, WEBSITE_PDFS
    out = []
    for path in sorted(PDFS.glob("*/*/*.pdf")):
        disc, edition = path.parent.parent.name, path.parent.name
        out.append((path, "nirf_cdn",
                    f"https://www.nirfindia.org/nirfpdfcdn/{edition}/pdf/{disc}/{path.name}"))
    urls = {}
    if WEBSITE_MANIFEST.exists():
        with open(WEBSITE_MANIFEST, newline="") as fh:
            for r in csv.DictReader(fh):
                urls[(r["discipline"], r["edition_year"], r["institute_id"])] = r["url"]
    for path in sorted(WEBSITE_PDFS.glob("*/*/*.pdf")):
        disc, edition = path.parent.parent.name, path.parent.name
        key = (disc, edition, path.stem)
        if (PDFS / disc / edition / path.name).exists():
            continue
        if key not in urls:
            raise SystemExit(f"{path} is not in {WEBSITE_MANIFEST.name}: add it with "
                             f"fetch_website_dcs.py so its URL is on record")
        out.append((path, "institute_website", urls[key]))
    return out


def parse_pdfs(website_only: bool = False) -> None:
    """Parse every DCS PDF into extracted/. website_only: parse just the
    institute-website PDFs and splice them into the existing CSVs — NIRF's
    own rows stay as parsed (only tagged nirf_cdn + their CDN URL), so adding
    a state takes seconds instead of a full re-parse."""
    placements, intakes, strengths, institutions = [], [], [], []
    files = _sources()
    if website_only:
        files = [f for f in files if f[1] == "institute_website"]
    print(f"parsing {len(files)} DCS pdfs "
          f"({sum(1 for f in files if f[1] == 'institute_website')} from institute websites)")
    for i, (path, source, url) in enumerate(files):
        disc = path.parent.parent.name
        edition = int(path.parent.name)
        before = [len(x) for x in (placements, intakes, strengths, institutions)]
        try:
            parse_pdf(path, edition, disc,
                      placements, intakes, strengths, institutions)
        except Exception as e:
            print(f"  FAIL {source} {disc}/{edition}/{path.name}: {e}")
        # every row says where its PDF came from
        for rows, n in zip((placements, intakes, strengths, institutions), before):
            for row in rows[n:]:
                row += [source, url]
        if (i + 1) % 200 == 0:
            print(f"  …{i + 1}/{len(files)}")

    OUT.mkdir(exist_ok=True)
    heads = {
        "dcs_placements.csv": (placements, [
            "edition_year", "discipline", "institute_id", "institute_name",
            "program_level", "program_level_raw",
            "intake_academic_year", "first_year_intake",
            "first_year_admitted", "lateral_academic_year",
            "lateral_admitted", "graduating_academic_year",
            "graduated_on_time", "students_placed", "median_salary",
            "higher_studies_selected", "pdf_source", "source_url"]),
        "dcs_intake.csv": (intakes, [
            "edition_year", "discipline", "institute_id", "institute_name",
            "program_level", "program_level_raw", "academic_year",
            "sanctioned_intake", "pdf_source", "source_url"]),
        "dcs_strength.csv": (strengths, [
            "edition_year", "discipline", "institute_id", "institute_name",
            "program_level", "program_level_raw", "male", "female", "total",
            "within_state", "outside_state", "outside_country",
            "economically_backward", "socially_challenged",
            "fee_reimb_government", "fee_reimb_institution",
            "fee_reimb_private", "no_fee_reimbursement", "pdf_source", "source_url"]),
        "dcs_institution.csv": (institutions, [
            "edition_year", "discipline", "institute_id", "institute_name",
            "phd_full_time_pursuing", "phd_part_time_pursuing",
            "faculty_count", "pdf_source", "source_url"]),
    }
    if website_only:
        import pandas as pd
        for name, (rows, header) in heads.items():
            old_df = pd.read_csv(OUT / name, dtype=str, keep_default_na=False)
            if "pdf_source" not in old_df.columns:
                old_df["pdf_source"] = "nirf_cdn"
                old_df["source_url"] = ("https://www.nirfindia.org/nirfpdfcdn/" + old_df.edition_year
                                        + "/pdf/" + old_df.discipline + "/" + old_df.institute_id + ".pdf")
            old_df = old_df[old_df.pdf_source != "institute_website"][header]
            new_df = pd.DataFrame(rows, columns=header).astype(str).replace({"None": ""})
            pd.concat([old_df, new_df]).to_csv(OUT / name, index=False)
            print(f"{name}: {len(old_df)} NIRF rows kept + {len(new_df)} institute-website rows")
        return
    for name, (rows, header) in heads.items():
        with open(OUT / name, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("all", "pages"):
        parse_pages()
    if which in ("all", "pdfs"):
        parse_pdfs()
    if which == "website":
        parse_pdfs(website_only=True)
