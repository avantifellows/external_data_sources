"""
Build a programme -> AISHE discipline mapping for the 227 programmes in
Table 34a, using AISHE's own discipline taxonomy from Table 35 (UG) + Table 36 (PG).

The Final Report Excel does not pre-tabulate out-turn at the discipline x social
category cut. Table 34a is at programme level. To produce a discipline-level
rollup we need a programme -> discipline mapping. AISHE's own internal mapping
isn't exposed in the workbook, so this script builds a heuristic mapping
based on programme-name patterns. The mapping is saved as an audit-able CSV
so you can inspect and override it.

Source: raw/aishe_2021-22_final_report.xlsx, sheet '34a' (programme list)
Output: codemaps/programme_to_discipline.csv  (committed; consumed by clean_aishe.py)

Output columns:
  programme            - exact programme name as in Table 34a
  discipline           - mapped AISHE discipline (one of ~40 from Table 35/36)
  matched_pattern      - the pattern that matched (for audit)
  confidence           - 'high' | 'medium' | 'low' (judgment-call notes)
  notes                - short explanation of any judgment call

Heuristic ordering: longest/most-specific patterns are tried first, so e.g.
'B.A.M.S.' (Ayurved Med & Surgery -> Medical Science) is matched before the
generic 'B.A.' (Bachelor of Arts -> Arts) rule.
"""
import csv
import re
import openpyxl
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "raw" / "aishe_2021-22_final_report.xlsx"
OUT = ROOT / "codemaps" / "programme_to_discipline.csv"

# Pattern is matched against the full programme string (case-insensitive, word-boundary aware
# at the head). Order matters: the FIRST matching rule wins.
# Each entry: (pattern_substring_or_regex, discipline, confidence, notes)
RULES: list[tuple[str, str, str, str]] = [
    # ---- Joint degrees with Education -> Education (AISHE convention) ----
    (r"^B\.A\. B\.Ed\.", "Education", "medium", "Joint BA-BEd; AISHE classifies under Education"),
    (r"^B\.Sc\. B\.Ed\.", "Education", "medium", "Joint BSc-BEd; AISHE classifies under Education"),
    (r"^B\.Com\. B\.Ed\.", "Education", "medium", "Joint BCom-BEd; AISHE classifies under Education"),
    (r"^M\.A\. B\.Ed\.", "Education", "medium", "Joint MA-BEd; AISHE classifies under Education"),
    (r"^M\.Com\. B\.Ed\.", "Education", "medium", "Joint MCom-BEd; AISHE classifies under Education"),
    (r"^M\.Sc\. B\.Ed\.", "Education", "medium", "Joint MSc-BEd; AISHE classifies under Education"),
    (r"^M\.Sc\.M\.Ed\.", "Education", "medium", "Joint MSc-MEd"),
    (r"^B\.Ed\. M\.Ed", "Education", "high", "Combined BEd-MEd"),
    (r"^B\.Ed\.", "Education", "high", ""),
    (r"^M\.Ed\.", "Education", "high", ""),
    (r"^D\.Ed\.", "Education", "high", ""),
    (r"^B\.El\.Ed\.", "Education", "high", "Bachelor of Elementary Education"),
    (r"^D\.El\.Ed\.", "Education", "high", ""),
    (r"^Art Education", "Education", "high", ""),
    (r"^Shiksha Shastri", "Education", "high", "Sanskrit-system education degree"),
    (r"^Shiksha Acharya", "Education", "high", "Sanskrit-system education degree"),

    # ---- Joint degrees with Law -> Law ----
    (r"L\.L\.B", "Law", "high", ""),
    (r"^BBA-LLB", "Law", "high", "Joint BBA-LLB; periodless variant"),
    (r"^L\.L\.M\.", "Law", "high", ""),
    (r"^L\.L\.D\.", "Law", "high", ""),
    (r"^M\.L\.", "Law", "high", "Master of Laws"),
    (r"^B\.L\.", "Law", "high", "Bachelor of Law"),
    (r"^B\.G\.L\.", "Law", "high", "Bachelor of General Law"),

    # ---- Medical Science (Indian/Modern medicine) ----
    (r"^M\.B\.B\.S\.", "Medical Science", "high", ""),
    (r"^B\.D\.S\.", "Medical Science", "high", "Dental Surgery"),
    (r"^M\.D\.S\.", "Medical Science", "high", "Master of Dental Surgery"),
    (r"^M\.D\.", "Medical Science", "high", "Doctor of Medicine"),
    (r"^M\.S\.-Master of Surgery", "Medical Science", "high", ""),
    (r"^D\.M\.-Doctor of Medicine", "Medical Science", "high", ""),
    (r"^M\.Ch\.", "Medical Science", "high", "Master of Chirurgiae (surgery)"),
    (r"^B\.A\.M\.S\.", "Medical Science", "high", "Ayurved Medicine & Surgery"),
    (r"^B\.A\.M\.", "Medical Science", "high", "Bachelor of Ayurved Medicine"),
    (r"^M\.A\.M\.S\.", "Medical Science", "high", "Master of Ayurved Med & Surgery"),
    (r"^B\.U\.M\.S\.", "Medical Science", "high", "Unani Medicine & Surgery"),
    (r"^B\.H\.M\.S\.", "Medical Science", "high", "Homeopathic Medicine & Surgery"),
    (r"^M\.H\.M\.S\.", "Medical Science", "high", "Master of Homeopathy"),
    (r"^B\.S\.M\.S\.", "Medical Science", "high", "Sridhar/Siddha Medicine & Surgery"),
    (r"^B\.I\.M\.", "Medical Science", "high", "Bachelor of Indian Medicine"),
    (r"^B\.N\.Y\.S\.", "Medical Science", "high", "Naturopathy & Yogic Sciences"),
    (r"^B\.Nat\.", "Medical Science", "high", "Bachelor of Naturopathy"),
    (r"^Ayurvedacharya", "Medical Science", "high", "Ayurveda Acharya"),
    (r"^Ayurveda Vachaspati", "Medical Science", "high", "PhD in Ayurveda"),
    (r"^B\.S\.Course", "Medical Science", "medium", "Physician Assistant & Trauma Care"),
    (r"^B\.S\. M\.S\.", "Medical Science", "medium", "Joint BSc-MS, medical sciences context"),
    (r"^M\.Sc\.\(Medical", "Medical Science", "high", "Medical sub-disciplines"),
    (r"^B\.Pharm\.\(Ayu\.\)", "Medical Science", "high", "Ayurved Pharmacy"),
    (r"^B\.Pharm\.", "Medical Science", "high", "Pharmacy under Medical Science (no separate AISHE discipline)"),
    (r"^M\.Pharm\.", "Medical Science", "high", "Pharmacy under Medical Science (no separate AISHE discipline)"),
    (r"^Pharm\.D\.", "Medical Science", "high", "Doctor of Pharmacy"),
    (r"^D\.Pharma", "Medical Science", "high", "Diploma in Pharmacy"),
    (r"^B\.H\.A\.", "Medical Science", "medium", "Hospital Admin; AISHE convention groups with Med Sci"),
    (r"^M\.H\.A\.", "Medical Science", "medium", "Master Hospital Admin; AISHE groups with Med Sci"),
    (r"^M\.P\.H\.", "Medical Science", "medium", "Master of Public Health"),

    # ---- Paramedical / Nursing / Allied Health ----
    (r"^A\.N\.M\.", "Paramedical Science", "high", "Auxiliary Nurse & Midwife"),
    (r"^G\.N\.M\.", "Paramedical Science", "high", "General Nursing"),
    (r"^B\.Sc\.\(Nursing\)", "Paramedical Science", "high", ""),
    (r"^B\.Sc\.\(Post Basic\)", "Paramedical Science", "high", "Post-basic nursing"),
    (r"^M\.Sc\. Nursing", "Paramedical Science", "high", ""),
    (r"^B\.M\.L\.T", "Paramedical Science", "high", "Medical Lab Tech"),
    (r"^D\.M\.L\.T", "Paramedical Science", "high", "Diploma Med Lab Tech"),
    (r"^Medical Laboratory Technician", "Paramedical Science", "high", ""),
    (r"^B\.X\.R\.T", "Paramedical Science", "high", "X-Ray Radiographer Tech"),
    (r"^D\.X-ray", "Paramedical Science", "high", ""),
    (r"^D\.O\.T\.A", "Paramedical Science", "high", "Operation Theater Assistant"),
    (r"^B\.O\.T\.", "Paramedical Science", "high", "Occupational Therapy"),
    (r"^M\.O\.T\.", "Paramedical Science", "high", "Master of Occupational Therapy"),
    (r"^B\.P\.T\.", "Paramedical Science", "high", "Physiotherapy"),
    (r"^M\.P\.T\.", "Paramedical Science", "high", "Master of Physiotherapy"),
    (r"^B\.Optom\.", "Paramedical Science", "high", "Optometry"),
    (r"^M\.Optom\.", "Paramedical Science", "high", "Master of Optometry"),
    (r"^B\.P\.O", "Paramedical Science", "high", "Prosthetics & Orthotics"),
    (r"^M\.P\.O", "Paramedical Science", "high", "Master Prosthetics"),
    (r"^B\.A\.S\.L\.P\.", "Paramedical Science", "high", "Audiology & Speech Lang Pathology"),

    # ---- Engineering & Technology ----
    # Be specific so 'B.Tech M.Tech' doesn't hit any other rule
    (r"^B\.Tech M\.Tech", "Engineering & Technology", "high", "Joint BTech-MTech"),
    (r"^B\.Tech\.", "Engineering & Technology", "high", ""),
    (r"^M\.Tech\.", "Engineering & Technology", "high", ""),
    (r"^B\.E\.-Bachelor", "Engineering & Technology", "high", "Bachelor of Engineering"),
    (r"^M\.E\.-Master", "Engineering & Technology", "high", "Master of Engineering"),
    (r"^M\.Sc\. -Master of Science and M\.Tech", "Engineering & Technology", "high", "Joint MSc-MTech"),
    (r"^M\.Sc\. Tech\.", "Engineering & Technology", "high", "MSc in Technology"),
    (r"^B\.C\.E\.", "Engineering & Technology", "high", "Civil Engg"),
    (r"^B\.Ch\.E\.", "Engineering & Technology", "high", "Chemical Engg"),
    (r"^B\.Chem\.Tech\.", "Engineering & Technology", "high", "Chemical Tech"),
    (r"^B\.Architecture", "Engineering & Technology", "medium", "Architecture grouped with E&T per AISHE"),
    (r"^M\.Arch\.", "Engineering & Technology", "medium", "Architecture grouped with E&T per AISHE"),
    (r"^B\.Plan\.", "Engineering & Technology", "medium", "Planning grouped with E&T"),
    (r"^M\.Plan\.", "Engineering & Technology", "medium", ""),
    (r"^M\.U\.P\.", "Engineering & Technology", "medium", "Master of Urban Planning"),
    (r"^Mechatronics", "Engineering & Technology", "high", ""),
    (r"^Automotive Mechatronics", "Engineering & Technology", "high", ""),
    (r"^Robotics and Automation", "Engineering & Technology", "high", ""),
    (r"^M\.B\.A\.\(Pharma\. Tech\.\)", "Management", "medium", "MBA in Pharma Tech - mgmt-leaning"),
    (r"^M\.B\.A\.\(Tech\.\)", "Management", "medium", "MBA in Tech - mgmt-leaning"),

    # ---- IT & Computer ----
    (r"^B\.C\.A\.", "IT & Computer", "high", "Bachelor of Computer Apps"),
    (r"^M\.C\.A\.", "IT & Computer", "high", ""),
    (r"^Integrated M\.C\.A\.", "IT & Computer", "high", ""),
    (r"^B\.SC\. \(IT\) M\.Sc\. \(IT\)", "IT & Computer", "high", "Joint BSc-MSc in IT"),

    # ---- Fashion Technology ----
    (r"^B\.F\.Tech\.", "Fashion Technology", "high", ""),
    (r"^M\.F\.Tech\.", "Fashion Technology", "high", ""),
    (r"^M\.F\.M\.-Master of Fashion Management", "Fashion Technology", "high", "Disambig MFM (fashion vs financial)"),
    (r"^Fashion and Apparel Design", "Fashion Technology", "high", ""),
    (r"^Fashion Art", "Fashion Technology", "high", ""),

    # ---- Footwear Design (separate AISHE discipline) ----
    (r"^B\.Sc\.\(FDP\)", "Footwear  Design", "high", "Footwear Design and Production"),

    # ---- Design ----
    (r"^B\.Des\.", "Design", "high", ""),
    (r"^B\.DES\. \(Communication", "Design", "high", "Communication Design"),
    (r"^M\.Des\.", "Design", "high", ""),
    (r"^Interior Design", "Design", "high", ""),
    (r"^Textile Design", "Design", "high", ""),

    # ---- Management ----
    (r"^B\.B\.A\.", "Management", "high", ""),
    (r"^M\.B\.A\.", "Management", "high", ""),
    (r"^B\.B\.M\.", "Management", "high", ""),
    (r"^B\.B\.S\.", "Management", "medium", "Bachelor of Business Studies"),
    (r"^B\.M\.S\.", "Management", "medium", "Bachelor of Management Studies"),
    (r"^M\.Mgt\.", "Management", "high", ""),
    (r"^M\.H\.R\.D\.", "Management", "high", "Master of HRD"),
    (r"^M\.Mkt\.M\.", "Management", "high", "Master of Marketing Mgt"),
    (r"^M\.F\.M\. -Master of Financial", "Management", "high", "Disambig MFM (financial vs fashion)"),
    (r"^M\.F\.T\.", "Management", "medium", "Foreign Trade"),
    (r"^M\.I\.B\.", "Management", "medium", "Master of International Business"),
    (r"^B\.I\.B\.F\.", "Management", "medium", "International Business & Finance"),
    (r"^EMBA", "Management", "high", ""),
    (r"^P\.G\.D\.M\.", "Management", "high", "PG Diploma in Management"),
    (r"^P\.G\.P\.", "Management", "high", "PG Programme in Management"),
    (r"^PGDBA", "Management", "high", ""),
    (r"^Integrated M\.B\.A\.", "Management", "high", ""),
    (r"^Management Financial Services", "Management", "medium", ""),
    (r"^Management HRM", "Management", "medium", ""),
    (r"^M\.P\.S\. ", "Management", "low", "Master of Population Studies; weak fit"),

    # ---- Hospitality and Tourism ----
    (r"^B\.H\.M\.C\.T\.", "Hospitality and Tourism", "high", "Hotel Mgt & Catering Tech"),
    (r"^B\.H\.M\.T\.T\.", "Hospitality and Tourism", "high", ""),
    (r"^B\.H\.T\.M\.", "Hospitality and Tourism", "high", ""),
    (r"^B\.H\.M\.", "Hospitality and Tourism", "high", "Bachelor of Hotel Management"),
    (r"^BTTM MTTM", "Hospitality and Tourism", "high", ""),
    (r"^MBA in Travel and Tourism", "Hospitality and Tourism", "high", ""),
    (r"^Master of Travel & Tourism", "Hospitality and Tourism", "high", ""),

    # ---- Commerce ----
    (r"^B\.Com\.", "Commerce", "high", ""),
    (r"^M\.Com\.", "Commerce", "high", ""),

    # ---- Library & Information Science ----
    (r"^B\.Lib\.I\.Sc\.", "Library & Information Science", "high", ""),
    (r"^B\.Lib\.Sc\.", "Library & Information Science", "high", ""),
    (r"^M\.L\.I\.Sc\.", "Library & Information Science", "high", ""),
    (r"^M\.Lib\.Sc\.", "Library & Information Science", "high", ""),

    # ---- Journalism & Mass Communication ----
    (r"^B\.J\.M\.C\.", "Journalism & Mass Communication", "high", ""),
    (r"^M\.J\.M\.C\.", "Journalism & Mass Communication", "high", ""),
    (r"^B\.J\.-Bachelor", "Journalism & Mass Communication", "high", ""),
    (r"^M\.J\.-Master", "Journalism & Mass Communication", "high", ""),
    (r"^B\.M\.M\.", "Journalism & Mass Communication", "high", "Bachelor of Multi Media"),
    (r"^M\.M\.C\.", "Journalism & Mass Communication", "high", "Master of Mass Comm"),

    # ---- Physical Education ----
    (r"^B\.P\.E\.", "Physical Education", "high", ""),
    (r"^B\.P\.Ed\.", "Physical Education", "high", ""),
    (r"^M\.P\.E\.", "Physical Education", "high", ""),
    (r"^M\.P\.Ed\.", "Physical Education", "high", ""),

    # ---- Fine Arts (incl. Music, Dance, Visual & Performing Arts) ----
    (r"^B\.F\.A\.", "Fine Arts", "high", ""),
    (r"^M\.F\.A\.", "Fine Arts", "high", ""),
    (r"^B\.V\.A\.", "Fine Arts", "high", "Visual Arts"),
    (r"^M\.V\.A\.", "Fine Arts", "high", "Master of Visual Arts"),
    (r"^B\.Mus\.", "Fine Arts", "high", ""),
    (r"^M\.Mus\.", "Fine Arts", "high", ""),
    (r"^D\.Mus\.", "Fine Arts", "high", ""),
    (r"^B\.Dance", "Fine Arts", "high", ""),
    (r"^M\.Dance", "Fine Arts", "high", ""),
    (r"^B\.P\.A\.", "Fine Arts", "high", "Performing Arts"),
    (r"^M\.P\.A\.", "Fine Arts", "high", ""),

    # ---- Veterinary & Animal Sciences ----
    (r"^B\.V\.Sc\.", "Veterinary & Animal Sciences", "high", ""),
    (r"^M\.V\.Sc\.", "Veterinary & Animal Sciences", "high", ""),

    # ---- Agriculture ----
    (r"^B\.Agri\.", "Agriculture", "high", ""),
    (r"^B\.Sc\.\(Sericulture\)", "Agriculture", "medium", "Sericulture grouped with Agriculture"),

    # ---- Fisheries Science ----
    (r"^B\.F\.Sc\.", "Fisheries Science", "high", ""),
    (r"^M\.F\.Sc\.", "Fisheries Science", "high", ""),

    # ---- Social Work ----
    (r"^B\.S\.W\.", "Social Work", "high", ""),
    (r"^M\.S\.W\.", "Social Work", "high", ""),
    (r"^Samaj Karya Parangat", "Social Work", "high", "Sanskrit-system Social Work"),

    # ---- Social Science ----
    (r"^B\.S\.S\.", "Social Science", "high", "Bachelor in Social Sciences"),
    (r"^Samaj Vidya Parangat", "Social Science", "medium", "Sanskrit-system Social Science"),
    (r"^Samaj Vidya Visharad", "Social Science", "medium", "Sanskrit-system Social Science"),
    (r"^Public Services", "Social Science", "low", "ambiguous; Social Science best fit"),

    # ---- Indian Language / Oriental Learning (Sanskrit-system degrees) ----
    (r"^B\.O\.L\.", "Oriental Learning", "high", ""),
    (r"^M\.O\.L\.", "Oriental Learning", "high", ""),
    (r"^Hindi Shiksha Visharad", "Indian Language", "high", "Hindi-language teacher cert"),
    (r"^Acharya-Acharya", "Oriental Learning", "high", "Sanskrit-system PG"),
    (r"^Shastri-Shastri", "Oriental Learning", "high", "Sanskrit-system UG"),
    (r"^Vachaspati-Vachaspati", "Oriental Learning", "high", "Sanskrit-system PhD"),
    (r"^Vidya Vachaspati", "Oriental Learning", "high", ""),
    (r"^Vidya Varidhi", "Oriental Learning", "high", ""),
    (r"^Visharad-Visharad", "Oriental Learning", "high", ""),
    (r"^Vidhyalankar", "Oriental Learning", "high", ""),
    (r"^Alankar-Alankar", "Oriental Learning", "high", ""),
    (r"^Bachelor in Astrology", "Oriental Learning", "medium", "No strict AISHE category; Oriental Learning best fit"),

    # ---- Arts (general) — must come AFTER Education/Law/Medical/Mgt joint-degree rules ----
    (r"^B\.A\.\(Hons\)", "Arts", "high", ""),
    (r"^B\.A\.-Bachelor", "Arts", "high", ""),
    (r"^M\.A\.-Master", "Arts", "high", ""),
    (r"^Integrated M\.A\.", "Arts", "high", ""),
    (r"^B\.Litt\.", "Arts", "high", ""),
    (r"^M\.Litt\.", "Arts", "high", ""),
    (r"^D\.Litt\.", "Arts", "high", ""),

    # ---- Science (general) — broad bucket; must come AFTER Medical/Nursing/IT/Footwear rules ----
    (r"^B\.Sc\.\(Hons\)", "Science", "high", ""),
    (r"^B\.Sc\.-Bachelor", "Science", "high", ""),
    (r"^B\.Stat\.", "Science", "high", ""),
    (r"^M\.Stat\.", "Science", "high", ""),
    (r"^M\.S\.-Master of Science", "Science", "high", ""),
    (r"^M\.Sc\.-Master of Science", "Science", "high", ""),
    (r"^M\.Sc\. in Biosciences", "Science", "high", ""),
    (r"^Integrated M\.Sc\.", "Science", "high", ""),
    (r"^MSc\. -Master of Science and Ph\.D", "Science", "high", "Joint MSc-PhD"),
    (r"^D\.Sc\.", "Science", "high", "Doctor of Science"),
    (r"^B\.P\.S\.", "Science", "low", "Bachelor of Professional Studies, ambiguous; default Science"),

    # ---- 'Others' bucket: catch-all genericdegrees ----
    (r"^Ph\.D\.", "Others", "high", "PhD discipline-agnostic; AISHE tracks elsewhere"),
    (r"^D\.Phil\.", "Others", "high", "PhD discipline-agnostic"),
    (r"^M\.Phil\.", "Others", "high", "M.Phil. discipline-agnostic"),
    (r"^Integrated Ph\.D", "Others", "high", "PhD discipline-agnostic"),
    (r"^Certificate-Certificate", "Others", "high", "Generic Certificate"),
    (r"^PG Diploma", "Others", "high", "Generic PG Diploma"),
    (r"^Diploma-Diploma", "Others", "high", "Generic Diploma"),
    (r"^B\.Voc\.", "Others", "high", "Vocational; no separate AISHE discipline"),
    (r"^D\.Voc\.", "Others", "high", "Vocational"),
    (r"^Master of Vocational", "Others", "high", "Vocational"),
    (r"^Entrepreneurship", "Others", "medium", "Could be Management; AISHE often groups under Others"),
]


def map_programme(prog: str) -> tuple[str, str, str, str]:
    """Returns (discipline, matched_pattern, confidence, notes)."""
    for pat, disc, conf, notes in RULES:
        if re.search(pat, prog, flags=re.IGNORECASE):
            return disc, pat, conf, notes
    return "Others", "<no match>", "low", "Unmatched programme; defaulted to Others"


def main() -> None:
    wb = openpyxl.load_workbook(SRC, data_only=True)
    ws = wb["34a"]

    progs = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        if row[1]:
            progs.append(str(row[1]).strip())

    rows_out = []
    unmatched = []
    for prog in progs:
        disc, pat, conf, notes = map_programme(prog)
        rows_out.append(
            {"programme": prog, "discipline": disc, "matched_pattern": pat, "confidence": conf, "notes": notes}
        )
        if pat == "<no match>":
            unmatched.append(prog)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["programme", "discipline", "matched_pattern", "confidence", "notes"])
        w.writeheader()
        w.writerows(rows_out)

    # Diagnostics
    from collections import Counter

    by_disc = Counter(r["discipline"] for r in rows_out)
    by_conf = Counter(r["confidence"] for r in rows_out)
    print(f"Wrote {len(rows_out)} programme mappings -> {OUT}")
    print(f"  Disciplines covered: {len(by_disc)}; programmes per discipline (top 12):")
    for d, n in by_disc.most_common(12):
        print(f"    {d:35s} {n:4d}")
    print(f"  Confidence: {dict(by_conf)}")
    if unmatched:
        print(f"  UNMATCHED ({len(unmatched)}) - defaulted to 'Others':")
        for p in unmatched:
            print(f"    - {p}")


if __name__ == "__main__":
    main()
