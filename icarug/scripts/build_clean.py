#!/usr/bin/env python3
"""
Build icarug_fact_cutoffs from ICAR's 2025 ICAR-UG (CUET) cut-off list.

Built from the team's CSV extraction and CHECKED against the official PDF:
every (category, marks start, marks end, rank start, rank end) group of the
CSV must equal the PDF's, in order, once the rows the PDF prints twice
across page breaks are removed. A mismatch fails the build.

Labels are cleaned, the source text kept in *_raw columns:
- university: the full printed name + address -> a display name, city and
  state (UNIVERSITIES below; spelling fixed: Parmer -> Parmar, Wayand ->
  Wayanad, Chandra Shekar -> Chandra Shekhar, Junagarh -> Junagadh, ...)
- course: "Nutural Farming" -> "Natural Farming"
- home_state: "(U.T.)" suffixes dropped
Home state is the allottees' domicile: one row per group of students from a
state who got that seat. Allotment is on the all-India ICAR-UG rank, so a
seat's closing rank is the MAX over home states.

Usage:
  python3 scripts/build_clean.py            # build + write parquet
  python3 scripts/build_clean.py --dry-run  # build + report only
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import CLEAN, GCS_BUCKET, RAW, RAW_FILES, TABLES, YEAR

ROUNDS = {"First Round": 1, "Second Round": 2, "Third Round": 3,
          "Fourth Round": 4, "Mop-up Round": 5}
CATEGORIES = {"UR", "OBC", "SC", "ST", "EWS", "UPS", "PwD"}
COURSE_FIX = {"B.Sc. (Hons.) Nutural Farming": "B.Sc. (Hons.) Natural Farming"}

# distinctive part of the printed string -> (display name, city, state)
UNIVERSITIES = {
    "Dr. Rajendra Prasad Central Agricultural University": ("Dr. Rajendra Prasad Central Agricultural University, Pusa", "Samastipur", "Bihar"),
    "Tamil Nadu Agricultural University": ("Tamil Nadu Agricultural University, Coimbatore", "Coimbatore", "Tamil Nadu"),
    "Rani Lakshmi Bai Central Agricultural University": ("Rani Lakshmi Bai Central Agricultural University, Jhansi", "Jhansi", "Uttar Pradesh"),
    "Acharya N G Ranga Agricultural University": ("Acharya N G Ranga Agricultural University, Guntur", "Guntur", "Andhra Pradesh"),
    "Vasantrao Naik Marathwada Krishi Vidyapeeth": ("Vasantrao Naik Marathwada Krishi Vidyapeeth, Parbhani", "Parbhani", "Maharashtra"),
    "Dr. Panjabrao Deshmukh Krishi Vidyapeeth": ("Dr. Panjabrao Deshmukh Krishi Vidyapeeth, Akola", "Akola", "Maharashtra"),
    "Punjab Agricultural University": ("Punjab Agricultural University, Ludhiana", "Ludhiana", "Punjab"),
    "Central Agricultural University, Iroisemba": ("Central Agricultural University, Imphal", "Imphal", "Manipur"),
    "Acharya Narendra Dev University of Agriculture": ("Acharya Narendra Dev University of Agriculture & Technology, Ayodhya", "Ayodhya", "Uttar Pradesh"),
    "Sher-e-Kashmir University of Agricultural Sciences and Technology of Kashmir": ("Sher-e-Kashmir University of Agricultural Sciences & Technology of Kashmir, Srinagar", "Srinagar", "Jammu and Kashmir"),
    "Indira Gandhi Krishi Vishwavidyalaya": ("Indira Gandhi Krishi Vishwavidyalaya, Raipur", "Raipur", "Chhattisgarh"),
    "University of Agricultural Sciences, GKVK": ("University of Agricultural Sciences, Bengaluru", "Bengaluru", "Karnataka"),
    "Mahatma Phule Krishi Vidyapeeth": ("Mahatma Phule Krishi Vidyapeeth, Rahuri", "Rahuri", "Maharashtra"),
    "Chandra Shekar Azad University": ("Chandra Shekhar Azad University of Agriculture & Technology, Kanpur", "Kanpur", "Uttar Pradesh"),
    "Banda University of Agriculture": ("Banda University of Agriculture & Technology, Banda", "Banda", "Uttar Pradesh"),
    "Orissa University of Agriculture": ("Odisha University of Agriculture & Technology, Bhubaneswar", "Bhubaneswar", "Odisha"),
    "Professor Jayashankar Agriculture University": ("Professor Jayashankar Telangana Agricultural University, Hyderabad", "Hyderabad", "Telangana"),
    "University of Agricultural Sciences, Krishi Nagar, Dharwad": ("University of Agricultural Sciences, Dharwad", "Dharwad", "Karnataka"),
    "Navsari Agricultural University": ("Navsari Agricultural University, Navsari", "Navsari", "Gujarat"),
    "Dr. Balasaheb Sawant Konkan Krishi Vidyapeeth": ("Dr. Balasaheb Sawant Konkan Krishi Vidyapeeth, Dapoli", "Dapoli", "Maharashtra"),
    "Maharana Pratap University of Agriculture": ("Maharana Pratap University of Agriculture & Technology, Udaipur", "Udaipur", "Rajasthan"),
    "University of Horticultural Sciences, Udyanagiri": ("University of Horticultural Sciences, Bagalkot", "Bagalkot", "Karnataka"),
    "Anand Agricultural University": ("Anand Agricultural University, Anand", "Anand", "Gujarat"),
    "Kerala Agricultural University": ("Kerala Agricultural University, Thrissur", "Thrissur", "Kerala"),
    "Keladi Shivappa Nayaka University": ("Keladi Shivappa Nayaka University of Agricultural & Horticultural Sciences, Shivamogga", "Shivamogga", "Karnataka"),
    "Sardarkrushinagar Dantiwada Agricultural University": ("Sardarkrushinagar Dantiwada Agricultural University, Banaskantha", "Sardarkrushinagar", "Gujarat"),
    "G.B. Pant University of Agriculture": ("G.B. Pant University of Agriculture & Technology, Pantnagar", "Pantnagar", "Uttarakhand"),
    "Junagarh Agricultural University": ("Junagadh Agricultural University, Junagadh", "Junagadh", "Gujarat"),
    "Jawahar Lal Nehru Krishi Vishwa Vidyalaya": ("Jawaharlal Nehru Krishi Vishwa Vidyalaya, Jabalpur", "Jabalpur", "Madhya Pradesh"),
    "Chaudhary Charan Singh Haryana Agricultural University": ("Chaudhary Charan Singh Haryana Agricultural University, Hisar", "Hisar", "Haryana"),
    "ICAR-National Dairy Research Institute": ("ICAR-National Dairy Research Institute, Karnal", "Karnal", "Haryana"),
    "Agriculture University, Borkhera": ("Agriculture University, Kota", "Kota", "Rajasthan"),
    "University of Agricultural Sciences, Raichur": ("University of Agricultural Sciences, Raichur", "Raichur", "Karnataka"),
    "Assam Agricultural University": ("Assam Agricultural University, Jorhat", "Jorhat", "Assam"),
    "Bihar Agricultural University": ("Bihar Agricultural University, Sabour", "Bhagalpur", "Bihar"),
    "Maharashtra Animal & Fishery Sciences University": ("Maharashtra Animal & Fishery Sciences University, Nagpur", "Nagpur", "Maharashtra"),
    "Rajmata Vijayaraje Scindia Krishi Vishwa Vidyalaya": ("Rajmata Vijayaraje Scindia Krishi Vishwa Vidyalaya, Gwalior", "Gwalior", "Madhya Pradesh"),
    "Sardar Vallabh Bhai Patel University": ("Sardar Vallabhbhai Patel University of Agriculture & Technology, Meerut", "Meerut", "Uttar Pradesh"),
    "Birsa Agricultural University": ("Birsa Agricultural University, Ranchi", "Ranchi", "Jharkhand"),
    "Dr.Y.S.R Horticultural University": ("Dr. Y.S.R. Horticultural University, Venkataramannagudem", "West Godavari", "Andhra Pradesh"),
    "ICAR- Indian Veterinary Research Institute": ("ICAR-Indian Veterinary Research Institute, Izatnagar", "Bareilly", "Uttar Pradesh"),
    "Swami Keshwanand Rajasthan Agricultural University": ("Swami Keshwanand Rajasthan Agricultural University, Bikaner", "Bikaner", "Rajasthan"),
    "Dr. Y.S. Parmer University": ("Dr. Y.S. Parmar University of Horticulture & Forestry, Nauni", "Solan", "Himachal Pradesh"),
    "Dau Shri Vasudev Chandrakar Kamdhenu Vishwavidyalaya": ("Dau Shri Vasudev Chandrakar Kamdhenu Vishwavidyalaya, Durg", "Durg", "Chhattisgarh"),
    "Kamdhenu University": ("Kamdhenu University, Gandhinagar", "Gandhinagar", "Gujarat"),
    "Bidhan Chandra Krishi Vishwavidyalaya": ("Bidhan Chandra Krishi Vishwavidyalaya, Mohanpur", "Nadia", "West Bengal"),
    "IARI Assam Hub": ("ICAR-IARI Assam Hub", "Dhemaji", "Assam"),
    "Institute of Agricultural Sciences, BHU": ("Institute of Agricultural Sciences, BHU, Varanasi", "Varanasi", "Uttar Pradesh"),
    "Sri Konda Laxman Telangana State Horticultural University": ("Sri Konda Laxman Telangana Horticultural University, Hyderabad", "Hyderabad", "Telangana"),
    "IARI Jharkhand Hub": ("ICAR-IARI Jharkhand Hub", "Hazaribagh", "Jharkhand"),
    "Karnataka Veterinary, Animal and Fisheries Sciences University": ("Karnataka Veterinary, Animal and Fisheries Sciences University, Bidar", "Bidar", "Karnataka"),
    "Sri Karan Narendra Agriculture University": ("Sri Karan Narendra Agriculture University, Jobner", "Jaipur", "Rajasthan"),
    "VCSG Uttarakhand Univ": ("VCSG Uttarakhand University of Horticulture & Forestry, Bharsar", "Bharsar", "Uttarakhand"),
    "Agriculture University, Mandor": ("Agriculture University, Jodhpur", "Jodhpur", "Rajasthan"),
    "NDRI Bengaluru Hub": ("ICAR-NDRI Bengaluru Hub", "Bengaluru", "Karnataka"),
    "West Bengal University of Animal & Fishery Sciences": ("West Bengal University of Animal & Fishery Sciences, Kolkata", "Kolkata", "West Bengal"),
    "Uttar Banga Krishi Viswavidyalaya": ("Uttar Banga Krishi Viswavidyalaya, Cooch Behar", "Cooch Behar", "West Bengal"),
    "Sher-e- Kashmir University of Agricultural Sciences & Technology of Jammu": ("Sher-e-Kashmir University of Agricultural Sciences & Technology of Jammu", "Jammu", "Jammu and Kashmir"),
    "Maharana Pratap Horticultural University": ("Maharana Pratap Horticultural University, Karnal", "Karnal", "Haryana"),
    "Guru Angad Dev Veterinary and Animal Sciences University": ("Guru Angad Dev Veterinary and Animal Sciences University, Ludhiana", "Ludhiana", "Punjab"),
    "Faculty of Agricultural Science, Aligarh Muslim University": ("Faculty of Agricultural Sciences, Aligarh Muslim University", "Aligarh", "Uttar Pradesh"),
    "Kerala University of Fisheries and Ocean Studies": ("Kerala University of Fisheries and Ocean Studies, Kochi", "Kochi", "Kerala"),
    "CSK Himachal Pradesh Krishi Vishvavidyalaya": ("CSK Himachal Pradesh Krishi Vishvavidyalaya, Palampur", "Palampur", "Himachal Pradesh"),
    "Nagaland University": ("Nagaland University (SAS), Medziphema", "Medziphema", "Nagaland"),
    "Nanaji Deshmukh Veterinary Science University": ("Nanaji Deshmukh Veterinary Science University, Jabalpur", "Jabalpur", "Madhya Pradesh"),
    "Tamil Nadu Dr. J. Jayalalithaa Fisheries University": ("Tamil Nadu Dr. J. Jayalalithaa Fisheries University, Nagapattinam", "Nagapattinam", "Tamil Nadu"),
    "Kerala Veterinary & Animal Sciences University": ("Kerala Veterinary & Animal Sciences University, Pookode", "Wayanad", "Kerala"),
    "PV Narsimha Rao Telangana State University": ("PV Narsimha Rao Telangana Veterinary University, Hyderabad", "Hyderabad", "Telangana"),
    "Palli Siksha Bhavana, Visva-Bharati": ("Palli Siksha Bhavana, Visva-Bharati, Santiniketan", "Santiniketan", "West Bengal"),
    "Sri Venkateswara Veterinary University": ("Sri Venkateswara Veterinary University, Tirupati", "Tirupati", "Andhra Pradesh"),
    "Tamil Nadu Veterinary & Animal Science University": ("Tamil Nadu Veterinary & Animal Sciences University, Chennai", "Chennai", "Tamil Nadu"),
    "Lala Lajpat Rai University of Veterinary & Animal Sciences": ("Lala Lajpat Rai University of Veterinary & Animal Sciences, Hisar", "Hisar", "Haryana"),
}
CAT_TOK = r"(?:UR|OBC|SC|ST|EWS|UPS|PwD)"


def fetch_raw() -> None:
    """GCS is canonical; download any raw file missing locally."""
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.local_path.relative_to(RAW.parent)} from {rf.gcs_uri}")


def university_of(raw: str) -> tuple[str, str, str]:
    hits = [v for k, v in UNIVERSITIES.items() if k in raw]
    if len(hits) != 1:
        raise SystemExit(f"university {raw!r} matched {len(hits)} UNIVERSITIES keys")
    return hits[0]


def pdf_groups(pdf: Path) -> list[tuple]:
    """(category, marks start, marks end, rank start, rank end) in PDF order,
    watermark fragments ('ICAR', 'IC', 'AR', sometimes glued to a number)
    stripped, page-break duplicates removed."""
    text = subprocess.run(["pdftotext", "-raw", str(pdf), "-"],
                          capture_output=True, text=True, check=True).stdout
    toks = [re.sub(r"^(ICAR|IC|AR)(?=\d)", "", t) for t in text.split()
            if t not in ("ICAR", "IC", "AR")]
    num = re.compile(r"^\d+(\.\d+)?$")
    out, i = [], 0
    while i < len(toks) - 4:
        a, b, c, d, e = toks[i:i + 5]
        if a in CATEGORIES and num.match(b) and num.match(c) and d.isdigit() and e.isdigit():
            out.append((a, round(float(b), 4), round(float(c), 4), int(d), int(e)))
            i += 5
        else:
            i += 1
    return out


def check_against_pdf(df: pd.DataFrame, pdf: Path) -> int:
    pdf_rows = pdf_groups(pdf)
    csv_rows = [(r.category, round(r.marks_start, 4), round(r.marks_end, 4),
                 r.rank_start, r.rank_end) for r in df.itertuples()]
    # walk both in order; the PDF may repeat a row next to itself at a page
    # break — skip exactly those, anything else is a mismatch
    i = dup = 0
    for j, row in enumerate(csv_rows):
        while i < len(pdf_rows) and pdf_rows[i] != row:
            prev_or_next = (i > 0 and pdf_rows[i] == pdf_rows[i - 1]) or \
                           (i + 1 < len(pdf_rows) and pdf_rows[i] == pdf_rows[i + 1])
            if not prev_or_next:
                raise SystemExit(f"CSV row {j} {row} not found in PDF order (PDF has {pdf_rows[i]})")
            i += 1
            dup += 1
        if i == len(pdf_rows):
            raise SystemExit(f"CSV row {j} {row} missing from the PDF")
        i += 1
    dup += len(pdf_rows) - i
    return dup


def build(path: Path) -> pd.DataFrame:
    s = pd.read_csv(path)
    s.columns = ["round", "home_state", "course", "university", "category",
                 "marks_start", "marks_end", "rank_start", "rank_end"]
    assert set(s["round"]) <= set(ROUNDS), set(s["round"]) - set(ROUNDS)
    assert set(s.category) <= CATEGORIES, set(s.category) - CATEGORIES
    uni = s.university.map(university_of)
    return pd.DataFrame({
        "year": YEAR,
        "round": s["round"].str.replace(" Round", ""),
        "round_order": s["round"].map(ROUNDS),
        "home_state_raw": s.home_state,
        "home_state": s.home_state.str.replace(r"\s*\(U\.T\.?\)", "", regex=True)
                       .str.replace("Jammu & Kashmir", "Jammu and Kashmir"),
        "course_raw": s.course,
        "course": s.course.replace(COURSE_FIX),
        "university_raw": s.university,
        "university": uni.map(lambda x: x[0]),
        "university_city": uni.map(lambda x: x[1]),
        "university_state": uni.map(lambda x: x[2]),
        "category": s.category,
        "marks_start": s.marks_start,
        "marks_end": s.marks_end,
        "rank_start": s.rank_start.astype(int),
        "rank_end": s.rank_end.astype(int),
    })


def check(df: pd.DataFrame) -> None:
    grain = ["round", "home_state", "course", "university_raw", "category"]
    assert not df.duplicated(grain).any(), "duplicate grain rows"
    assert (df.marks_start <= df.marks_end).all() and (df.rank_start <= df.rank_end).all()
    assert df.university_raw.groupby(df.university).nunique().max() == 1, \
        "two printed universities share a display name"
    # higher marks -> better (lower) rank within a cell
    assert ((df.rank_start == df.rank_end) == (df.marks_start == df.marks_end)).mean() > 0.99


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Build + report; write nothing")
    args = ap.parse_args()

    fetch_raw()
    pdf, csv = RAW_FILES[0].local_path, RAW_FILES[1].local_path
    df = build(csv)
    check(df)
    dup = check_against_pdf(df, pdf)
    print(f"icarug_fact_cutoffs: {len(df):,} rows, {df.university.nunique()} universities, "
          f"{df.course.nunique()} courses; every number matches the PDF "
          f"({dup} page-break repeats skipped)")
    if args.dry_run:
        return
    t = TABLES[0]
    CLEAN.mkdir(parents=True, exist_ok=True)
    df.to_parquet(t.local_path, index=False)
    print(f"  wrote {t.local_path.relative_to(CLEAN.parent)}")


if __name__ == "__main__":
    main()
