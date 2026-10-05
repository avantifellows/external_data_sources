"""
CUET (UG) merit rules, read from each university's 2025 bulletin.

A rule is a list of combinations; a course's merit score is the best
combination the student's papers can fill. Slots:
    "L"  any language (DU List A)
    "B"  any domain subject (DU List B)
    "G"  the General Aptitude Test
    [ids] one of these papers (e.g. ["maths"], ["english", "hindi"])
Each paper is used once. Every paper is out of 250.

Where one course mixes combinations of different sizes (DU B.A. Program:
4 papers, or language + subject + GAT), DU says "appropriate proration will
be done". We scale the smaller combination up to the larger one's scale
(x 4/3, x 2), the simplest reading; `prorated` marks those rules. Courses
whose combinations are all one size are compared on their natural scale
(B.Sc. Physics: Physics + Chemistry + Maths, out of 750).

`needs_language`: the course counts only science papers but asks the
student to have written a language paper too (DU B.Sc.).

`ref` is where the rule is printed: DU bulletin page, BHU eligibility entry.
"""
from __future__ import annotations

import re

LANGUAGES = ["english", "hindi", "assamese", "bengali", "gujarati", "kannada",
             "malayalam", "marathi", "odia", "punjabi", "sanskrit", "tamil",
             "telugu", "urdu"]
SUBJECTS = ["accountancy", "agriculture", "anthropology", "biology", "business",
            "chemistry", "cs", "economics", "envsci", "finearts", "geography",
            "history", "homesci", "ktpi", "massmedia", "maths", "perfarts",
            "phyed", "physics", "polsci", "psychology", "sociology"]
PAPER_LABEL = {
    "english": "English", "hindi": "Hindi", "assamese": "Assamese",
    "bengali": "Bengali", "gujarati": "Gujarati", "kannada": "Kannada",
    "malayalam": "Malayalam", "marathi": "Marathi", "odia": "Odia",
    "punjabi": "Punjabi", "sanskrit": "Sanskrit", "tamil": "Tamil",
    "telugu": "Telugu", "urdu": "Urdu",
    "accountancy": "Accountancy", "agriculture": "Agriculture",
    "anthropology": "Anthropology", "biology": "Biology",
    "business": "Business Studies", "chemistry": "Chemistry",
    "cs": "Computer Science", "economics": "Economics",
    "envsci": "Environmental Science", "finearts": "Fine Arts",
    "geography": "Geography", "history": "History", "homesci": "Home Science",
    "ktpi": "Knowledge Tradition (KTPI)", "massmedia": "Mass Media",
    "maths": "Maths", "perfarts": "Performing Arts",
    "phyed": "Physical Education", "physics": "Physics",
    "polsci": "Political Science", "psychology": "Psychology",
    "sociology": "Sociology", "gat": "GAT",
}
PAPER_SCORE_MAX = 250

L, B, G = "L", "B", "G"
P, C, M, BIO = ["physics"], ["chemistry"], ["maths"], ["biology"]
EN_HI = ["english", "hindi"]
DU_L3 = [[L, B, B, B], [L, L, B, B]]


def lang_hons(lang, generic=False):
    return [[[lang], B, B, B], [[lang], L, B, B]] + (DU_L3 if generic else [])


# rule_id -> university, combos, needs_language, ref
RULES = {
    "DU_L3": ("DU", DU_L3, False, "p. 21-42 (most B.A. Hons), p. 84 (B.El.Ed.)"),
    "DU_BA_PROG": ("DU", DU_L3 + [[L, B, G]], False,
                   "p. 43 (B.A. Program), p. 62 (B.Sc. Pass Home Science), p. 76-78 (B.Voc, B.A. Vocational)"),
    "DU_BCOM": ("DU", [[L, B, B, B], [L, B, G]], False, "p. 71"),
    "DU_VOC_SOFTWARE": ("DU", [[L, M, B, B], [L, L, M, B], [L, M, G]], False, "p. 77"),
    "DU_LANG_ENGLISH": ("DU", lang_hons("english"), False, "p. 22"),
    "DU_LANG_HINDI": ("DU", lang_hons("hindi"), False, "p. 24"),
    "DU_LANG_URDU": ("DU", lang_hons("urdu"), False, "p. 30"),
    "DU_LANG_BENGALI": ("DU", lang_hons("bengali", True), False, "p. 21"),
    "DU_LANG_PUNJABI": ("DU", lang_hons("punjabi", True), False, "p. 27"),
    "DU_LANG_SANSKRIT": ("DU", [[L, ["sanskrit"], B, B], [["sanskrit"], B, B, B]], False, "p. 28"),
    "DU_ECONOMICS": ("DU", [[L, M, B, B]], False, "p. 33"),
    "DU_HINDI_PATRAKARITA": ("DU", [[["hindi"], B, B, B], [["hindi"], G]], False, "p. 35"),
    "DU_JOURNALISM": ("DU", [[["english"], B, B, B], [["english"], G]], False, "p. 38"),
    "DU_JOURNALISM_5YR": ("DU", [[L, ["massmedia"], G], [L, G]], False, "p. 39"),
    "DU_MULTIMEDIA": ("DU", [[L, B, G]], False, "p. 39"),
    "DU_L_MATH_GAT": ("DU", [[L, M, G]], False, "p. 60 (B.Tech IT & MI), p. 72-73 (Business Economics, BBA FIA, BMS)"),
    "DU_L_MATH_2": ("DU", [[L, M, B, B], [L, L, M, B]], False, "p. 50, 55, 59, 63"),
    "DU_BCOM_HONS": ("DU", [[L, M, B, B], [L, ["accountancy"], B, B]], False, "p. 69"),
    "DU_PCB": ("DU", [[P, C, BIO]], True, "p. 47-49, 57, 59, 61, 63"),
    "DU_PCM": ("DU", [[P, C, M]], True, "p. 49, 57-58, 61-62, 65"),
    "DU_BIOCHEM": ("DU", [[C, BIO, P], [C, BIO, M]], True, "p. 48"),
    "DU_PM_C_OR_CS": ("DU", [[P, M, C], [P, M, ["cs"]]], True, "p. 51, 55, 66"),
    "DU_PC_B_OR_M": ("DU", [[P, C, BIO], [P, C, M]], True, "p. 52-53"),
    "DU_GEOLOGY": ("DU", [[P, C, M], [P, C, ["geography"]], [P, C, BIO]], True, "p. 54"),
    "DU_HOME_SCIENCE": ("DU", [[BIO, P, B], [BIO, C, B]], True, "p. 54"),

    "BHU_L_GAT": ("BHU", [[EN_HI, G]], False, "entries 1, 2, 9, 10, 12, 14"),
    "BHU_L_BIO": ("BHU", [[EN_HI, BIO]], False, "entry 13"),
    "BHU_BCOM": ("BHU", [[["accountancy"], ["business"], G]], False, "entry 3"),
    "BHU_PCM": ("BHU", [[C, M, P]], False, "entries 6, 7, 8"),
    "BHU_PCB": ("BHU", [[BIO, C, P]], False, "entries 5, 19"),
    "BHU_PCM_OR_PCB": ("BHU", [[C, M, P], [BIO, C, P]], False, "entries 5-6 (Geography / Earth Science in both groups), 18"),
    "BHU_AGRI": ("BHU", [[C, M, P], [BIO, C, P], [["agriculture"], BIO, C]], False, "entries 4, 11"),
    "BHU_SHASTRI": ("BHU", [[["sanskrit"]]], False, "entry 17"),
}

# course string (as in the cutoff fact) -> rule. First match wins.
DU_PROGRAMS = [
    (r"^B\.?A\.? ?Program", "DU_BA_PROG"),
    (r"^B\.A\. \(Vocational Studies\)", "DU_BA_PROG"),
    (r"^B\.Voc\.? Software", "DU_VOC_SOFTWARE"),
    (r"^B\.Voc", "DU_BA_PROG"),
    (r"^B\.Sc \(Pass\) Home Science", "DU_BA_PROG"),
    (r"^Five Year Integrated Program in Journalism", "DU_JOURNALISM_5YR"),
    (r"Hindi Patrakarita", "DU_HINDI_PATRAKARITA"),
    (r"^B\.A\. \(Hons\.\) Journalism", "DU_JOURNALISM"),
    (r"Multi ?Media and Mass Communication", "DU_MULTIMEDIA"),
    (r"^B\.A\. \(Hons\.\) Business Economics", "DU_L_MATH_GAT"),
    (r"^B\.A\. \(Hons\.\) Economics", "DU_ECONOMICS"),
    (r"^B\.A\. \(Hons\.\) English", "DU_LANG_ENGLISH"),
    (r"^B\.A\. \(Hons\.\) Hindi", "DU_LANG_HINDI"),
    (r"^B\.A\. \(Hons\.\) Urdu", "DU_LANG_URDU"),
    (r"^B\.A\. \(Hons\.\) Bengali", "DU_LANG_BENGALI"),
    (r"^B\.A\. \(Hons\.\) Punjabi", "DU_LANG_PUNJABI"),
    (r"^B\.A\. \(Hons\.\) Sanskrit", "DU_LANG_SANSKRIT"),
    (r"^B\.A\. \(Hons\.\)", "DU_L3"),
    (r"^Bachelor of Elementary Education", "DU_L3"),
    (r"^Bachelor of Management Studies", "DU_L_MATH_GAT"),
    (r"^Bachelor of Business Administration", "DU_L_MATH_GAT"),
    (r"^B\.Tech\. Information Technology", "DU_L_MATH_GAT"),
    (r"^B\.Com \(Hons\.\)", "DU_BCOM_HONS"),
    (r"^B\.Com$", "DU_BCOM"),
    (r"Bio-?Chemistry", "DU_BIOCHEM"),
    (r"Electronics|Instrumentation|Physical Science with Computer", "DU_PM_C_OR_CS"),
    (r"Environmental Science|Food Technology", "DU_PC_B_OR_M"),
    (r"Geology", "DU_GEOLOGY"),
    (r"Home Science", "DU_HOME_SCIENCE"),
    (r"Computer Science|Mathematic|Statistics", "DU_L_MATH_2"),
    (r"Anthropology|Biological|Biomedical|Botany|Microbiology|Zoology|Life Science", "DU_PCB"),
    (r"Chemistry|Physics|Polymer|Applied Physical Science", "DU_PCM"),
]

BHU_BIO = r"Botany|Zoology|Home Science"
BHU_MATH = r"Mathematics|Statistics|Computer Science|Physics"


def bhu_rule(p: str) -> str | None:
    if p.startswith("Shastri"):
        return "BHU_SHASTRI"
    if p.startswith("Bachelor of Arts"):  # B.A. (Hons) and B.A. LL.B.
        return "BHU_L_GAT"
    if p.startswith("Bachelor of Commerce"):
        return "BHU_BCOM"
    if "Agriculture" in p or "Food Processing" in p:
        return "BHU_AGRI"
    if "Medical Lab Technology" in p:
        return "BHU_L_BIO"
    if p.startswith("Bachelor of Vocation"):
        return "BHU_L_GAT"
    if p.startswith("Bachelor of Technology"):
        return "BHU_PCM"
    if "Radiotherapy" in p:
        return "BHU_PCM_OR_PCB"
    if "Radiology" in p:
        return "BHU_PCB"
    if p.startswith("Bachelor of Science"):
        subj = p.split(" in ", 1)[1]
        if re.search(BHU_BIO, subj):
            return "BHU_PCB"
        if re.search(BHU_MATH, subj):
            return "BHU_PCM"
        return "BHU_PCM_OR_PCB"  # Geography with Earth Science: either group
    return None  # Fine / Performing Arts: practical test, no CUET-only rule


def du_rule(p: str) -> str | None:
    return next((rule for pat, rule in DU_PROGRAMS if re.search(pat, p)), None)


RULE_OF = {"DU": du_rule, "BHU": bhu_rule}
