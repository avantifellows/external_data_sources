"""
University of Allahabad UG admission (CUET) cut-offs — source configuration,
the single source of truth.

Source: the university's 2025-26 UG admission pages (Arts, Science, Commerce
faculties: allduniv.ac.in/p/692, /693, /694), one cut-off notice per
programme per round, plus its "Guidelines and eligibility criteria" (which
CUET papers each programme's merit counts). Every file the pipeline reads is
listed in RAW_FILES with the URL it was downloaded from on 2026-10-05.

roles:
  text      cut-off notice with a text layer, read by scripts/parse_notices.py
  manual    scanned, or laid out so a parser can't pair labels with marks
            (B.P.A. prints a round per category): transcribed by eye into
            extracted/manual_transcriptions.csv, one row per printed cell
  rules     the merit / eligibility guideline (no cut-offs)
  excluded  read and left out, reason in `note`

has_names: the file lists named candidates (shortlists, quota lists). Kept
in the private bucket for provenance; never published (open_data excludes
them) and never transcribed beyond a printed cut-off line.

GCS layout:
    gs://avantifellows-external-data/allahabadug/raw/<file>
    gs://avantifellows-external-data/allahabadug/extracted/manual_transcriptions.csv
    gs://avantifellows-external-data/allahabadug/clean/<table>.parquet
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
EXTRACTED = ROOT / "extracted"
CLEAN = ROOT / "clean"

GCS_BUCKET = "avantifellows-external-data"
GCS_PREFIX = "allahabadug"

BQ_PROJECT = "avantifellows"
BQ_DATASET = "external_data_sources"
BQ_LOCATION = "asia-south1"

MANUAL = EXTRACTED / "manual_transcriptions.csv"
MANUAL_GCS = f"{GCS_PREFIX}/extracted/manual_transcriptions.csv"


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str
    role: str
    has_names: bool = False
    note: str = ""

    @property
    def local_path(self) -> Path:
        return RAW / self.name

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/raw/{self.name}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"


RAW_FILES = [
    RawFile('13_final.pdf',
            'https://allduniv.ac.in/upload/file_collection/13_final.pdf',
            'text', has_names=False),
    RawFile('1st cut of facs.pdf',
            'https://allduniv.ac.in/upload/file_collection/1st%20cut%20of%20facs.pdf',
            'excluded', has_names=True,
            note='named shortlist with no printed cut-off'),
    RawFile('2nd cut off facs1208.pdf',
            'https://allduniv.ac.in/upload/file_collection/2nd%20cut%20off%20facs1208.pdf',
            'excluded', has_names=True,
            note='named shortlist with no printed cut-off'),
    RawFile('3rd Cutoff BBA-MBA.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/3rd%20Cutoff%20BBA-MBA.pdf',
            'text', has_names=False),
    RawFile('5_year_evs.pdf',
            'https://allduniv.ac.in/upload/file_collection/5_year_evs.pdf',
            'manual', has_names=False),
    RawFile('5th Cutoff BBA-MBA.pdf',
            'https://allduniv.ac.in/upload/file_collection/5th%20Cutoff%20BBA-MBA.pdf',
            'text', has_names=False),
    RawFile('B.com WU notice 2025-26.pdf',
            'https://allduniv.ac.in/upload/file_collection/B.com%20WU%20notice%202025-26.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('B.Com_5th list 1408.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/B.Com_5th%20list%201408.pdf',
            'text', has_names=False),
    RawFile('B_Com 7th List.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/B_Com%207th%20List.pdf',
            'text', has_names=False),
    RawFile('BA Admission Fifth Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission%20Fifth%20Merit.pdf',
            'text', has_names=False),
    RawFile('BA Admission Fourth Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission%20Fourth%20Merit.pdf',
            'text', has_names=False),
    RawFile('BA Admission Second Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission%20Second%20Merit.pdf',
            'text', has_names=False),
    RawFile('BA Admission Third Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission%20Third%20Merit.pdf',
            'text', has_names=False),
    RawFile('BA Admission_6th cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission_6th%20cutoff.pdf',
            'text', has_names=False),
    RawFile('BA Admission_7th cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission_7th%20cutoff.pdf',
            'text', has_names=False),
    RawFile('BA Admission_8th cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission_8th%20cutoff.pdf',
            'text', has_names=False),
    RawFile('BA Admission_9th cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission_9th%20cutoff.pdf',
            'text', has_names=False),
    RawFile('BA Admission_Sports_ cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA%20Admission_Sports_%20cutoff.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('BA_First Merit (1).pdf',
            'https://allduniv.ac.in/upload/file_collection/BA_First%20Merit%20(1).pdf',
            'manual', has_names=False),
    RawFile('BA_First Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BA_First%20Merit.pdf',
            'text', has_names=False),
    RawFile('Bba mba Notice_1st.pdf',
            'https://allduniv.ac.in/upload/file_collection/Bba%20mba%20Notice_1st.pdf',
            'text', has_names=False),
    RawFile('Bba mba Notice_2nd.pdf',
            'https://allduniv.ac.in/upload/file_collection/Bba%20mba%20Notice_2nd.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA 10th Cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA%2010th%20Cutoff.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA 4th_Cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA%204th_Cutoff.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA_11th Cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA_11th%20Cutoff.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA_12th Cutoff.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BBA-MBA_12th%20Cutoff.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA_6TH CUTOFF.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA_6TH%20CUTOFF.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA_7th.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA_7th.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA_8th_Cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA_8th_Cutoff.pdf',
            'text', has_names=False),
    RawFile('BBA-MBA_9th_Cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/BBA-MBA_9th_Cutoff.pdf',
            'text', has_names=False),
    RawFile('BCom 10th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%2010th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 11th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%2011th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 12th List.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BCom%2012th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 13th List.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BCom%2013th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 14th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%2014th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 15th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%2015th%20List.pdf',
            'text', has_names=False),
    RawFile('BCOM 2ND 0408.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCOM%202ND%200408.pdf',
            'text', has_names=False),
    RawFile('Bcom 3rd merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/Bcom%203rd%20merit.pdf',
            'text', has_names=False),
    RawFile('BCom 4th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%204th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 6th List 1808.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BCom%206th%20List%201808.pdf',
            'text', has_names=False),
    RawFile('BCom 8th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%208th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom 9th List.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%209th%20List.pdf',
            'text', has_names=False),
    RawFile('BCom Admission Under PwD Category 2025-26.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BCom%20Admission%20Under%20PwD%20Category%202025-26.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('BCom Admission Under Sports Category 2025-26.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BCom%20Admission%20Under%20Sports%20Category%202025-26.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('BCom Notice_1st.pdf',
            'https://allduniv.ac.in/upload/file_collection/BCom%20Notice_1st.pdf',
            'text', has_names=False),
    RawFile('BFA 21 Aug 2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BFA%2021%20Aug%202025.pdf',
            'excluded', has_names=False,
            note='BFA admits after a practical test'),
    RawFile('BFA Aug 29, 202.pdf',
            'https://allduniv.ac.in/upload/file_collection/BFA%20Aug%2029,%20202.pdf',
            'excluded', has_names=False,
            note='BFA admits after a practical test'),
    RawFile('BFA_NOTICE 2nd merit list2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BFA_NOTICE%202nd%20merit%20list2025.pdf',
            'excluded', has_names=False,
            note='BFA admits after a practical test'),
    RawFile('BFA_NOTICE 3rd merit list2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BFA_NOTICE%203rd%20merit%20list2025.pdf',
            'excluded', has_names=False,
            note='BFA admits after a practical test'),
    RawFile('BPA 2nd Music obc_sc_ Merit .pdf',
            'https://allduniv.ac.in/upload/file_collection/BPA%202nd%20Music%20obc_sc_%20Merit%20.pdf',
            'manual', has_names=False),
    RawFile('BPA MUSIC 2ND CUTOFF MERIT .pdf',
            'https://allduniv.ac.in/upload/file_collection/BPA%20MUSIC%202ND%20CUTOFF%20MERIT%20.pdf',
            'manual', has_names=False),
    RawFile('BPA Music 5th Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BPA%20Music%205th%20Merit.pdf',
            'manual', has_names=False),
    RawFile('BPA_Music Merit.pdf',
            'https://allduniv.ac.in/upload/file_collection/BPA_Music%20Merit.pdf',
            'manual', has_names=False),
    RawFile('BPA_MUSIC_4THCUTOFF.pdf',
            'https://allduniv.ac.in/upload/file_collection/BPA_MUSIC_4THCUTOFF.pdf',
            'manual', has_names=False),
    RawFile('BSc Bio Notice  2 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%20%202%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice  3 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%20%203%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice (Cut off list).pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%20(Cut%20off%20list).pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 10 cutoff list.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%2010%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 11 cutoff list.docx.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%2011%20cutoff%20list.docx.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 12 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%2012%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 4 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%204%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 5 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%205%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 6 cutoff list (1).pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%206%20cutoff%20list%20(1).pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 7 cutoff list.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%207%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 8 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%208%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Bio Notice 9 cutoff list.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Bio%20Notice%209%20cutoff%20list.pdf',
            'text', has_names=False),
    RawFile('BSc Math Meritlist to PRO 21 August 2025.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BSc%20Math%20Meritlist%20to%20PRO%2021%20August%202025.pdf',
            'text', has_names=False),
    RawFile('BSC Math teacher employee WU Notice.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSC%20Math%20teacher%20employee%20WU%20Notice.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('BSc Maths Cut-off and Fee Submission Schedule -4Sept 2025.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BSc%20Maths%20Cut-off%20and%20Fee%20Submission%20Schedule%20-4Sept%202025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Cut-off and Fee Submission Schedule -8Sept 2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Cut-off%20and%20Fee%20Submission%20Schedule%20-8Sept%202025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist cutoff 5 August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20cutoff%205%20August2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist to PRO-11August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20to%20PRO-11August2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist to PRO-11September2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20to%20PRO-11September2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist to PRO-12 September2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20to%20PRO-12%20September2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist to PRO-14August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20to%20PRO-14August2025.pdf',
            'text', has_names=False),
    RawFile('BSc MATHS Meritlist to PRO-18August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20MATHS%20Meritlist%20to%20PRO-18August2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist to PRO-1Sept 2025.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20to%20PRO-1Sept%202025.pdf',
            'text', has_names=False),
    RawFile('BSc MATHS Meritlist to PRO-25August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20MATHS%20Meritlist%20to%20PRO-25August2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist to PRO-29August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist%20to%20PRO-29August2025.pdf',
            'text', has_names=False),
    RawFile('BSc Maths Meritlist- 10September2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc%20Maths%20Meritlist-%2010September2025.pdf',
            'text', has_names=False),
    RawFile('BSc(Maths) Meritlist to PRO-8August2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/BSc(Maths)%20Meritlist%20to%20PRO-8August2025.pdf',
            'text', has_names=False),
    RawFile('Cutoff_2_CVSSD.pdf',
            'https://allduniv.ac.in/upload/file_collection/Cutoff_2_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('Cutoff_7_CVSSD.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/Cutoff_7_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('Cutoff_Fourth_CVSSD.pdf',
            'https://allduniv.ac.in/upload/file_collection/Cutoff_Fourth_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('Cutoff_Tenth_CVSSD.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/Cutoff_Tenth_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('CVSSD1stCutoff25-26.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/CVSSD1stCutoff25-26.pdf',
            'manual', has_names=False),
    RawFile('CVSSD_Doc_Ver_Notice.pdf',
            'https://allduniv.ac.in/upload/file_collection/CVSSD_Doc_Ver_Notice.pdf',
            'excluded', has_names=False,
            note='document verification schedule'),
    RawFile('CVSSD_Eleventh_Cutoffs.pdf',
            'https://allduniv.ac.in/upload/file_collection/CVSSD_Eleventh_Cutoffs.pdf',
            'manual', has_names=False),
    RawFile('CVSSD_Ninth_cutoff.pdf',
            'https://allduniv.ac.in/upload/file_collection/CVSSD_Ninth_cutoff.pdf',
            'manual', has_names=False),
    RawFile('Disaster managment  and Env Studies  ....Notice_5th  Merit List.pdf',
            'https://allduniv.ac.in/upload/file_collection/Disaster%20managment%20%20and%20Env%20Studies%20%20....Notice_5th%20%20Merit%20List.pdf',
            'text', has_names=False),
    RawFile('Disaster managment and Env Studies---  Notice_7TH.pdf',
            'https://allduniv.ac.in/upload/file_collection/Disaster%20managment%20and%20Env%20Studies---%20%20Notice_7TH.pdf',
            'text', has_names=False),
    RawFile('Disaster managment and Env Studies..... Notice_6th Merit list.pdf',
            'https://allduniv.ac.in/upload/file_collection/Disaster%20managment%20and%20Env%20Studies.....%20Notice_6th%20Merit%20list.pdf',
            'text', has_names=False),
    RawFile('Disaster managment and Environmental Studies_2nd notice.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/Disaster%20managment%20and%20Environmental%20Studies_2nd%20notice.pdf',
            'text', has_names=False),
    RawFile('Disaster managment and ES  Notice_4th list.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/Disaster%20managment%20and%20ES%20%20Notice_4th%20list.pdf',
            'text', has_names=False),
    RawFile('DisasterEnvironmentalStudies--Notice_3rd.pdf',
            'https://allduniv.ac.in/upload/file_collection/DisasterEnvironmentalStudies--Notice_3rd.pdf',
            'text', has_names=False,
            note='a 2026-27 notice (CUET-UG-2026) on the 2025 page; kept with year 2026'),
    RawFile('Eighth_Cutoff_CVSSD.pdf',
            'https://allduniv.ac.in/upload/file_collection/Eighth_Cutoff_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('employee ward admission jk 2508.pdf',
            'https://allduniv.ac.in/upload/file_collection/employee%20ward%20admission%20jk%202508.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('Fifth_Cutoff_CVSSD.pdf',
            'https://allduniv.ac.in/upload/file_collection/Fifth_Cutoff_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('homescience 3rd merit 1408.pdf',
            'https://allduniv.ac.in/upload/file_collection/homescience%203rd%20merit%201408.pdf',
            'manual', has_names=True),
    RawFile('Meritlist-BSc Maths to PRO-1 August 2025.pdf',
            'https://allduniv.ac.in/upload/file_collection/Meritlist-BSc%20Maths%20to%20PRO-1%20August%202025.pdf',
            'text', has_names=False),
    RawFile('MUSIC BPA CUTOFF.pdf',
            'https://allduniv.ac.in/upload/file_collection/MUSIC%20BPA%20CUTOFF.pdf',
            'manual', has_names=False),
    RawFile('Notification_TeacherEmployeeQuota B.A. Admission.pdf',
            'https://allduniv.ac.in/upload/file_collection/Notification_TeacherEmployeeQuota%20B.A.%20Admission.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('Sixth_Cutoff_CVSSD.pdf',
            'https://allduniv.ac.in/upload/file_collection/Sixth_Cutoff_CVSSD.pdf',
            'manual', has_names=False),
    RawFile('sports quota ug 1208.pdf',
            'https://allduniv.ac.in/upload/file_collection/sports%20quota%20ug%201208.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('Teacher Quota-1.pdf',
            'https://allduniv.ac.in/upload/file_collection/Teacher%20Quota-1.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),
    RawFile('Third_Cutoff_CVSSD1808.pdf',
            'https://www.allduniv.ac.in/upload/file_collection/Third_Cutoff_CVSSD1808.pdf',
            'manual', has_names=False),
    RawFile('WU.pdf',
            'https://allduniv.ac.in/upload/file_collection/WU.pdf',
            'excluded', has_names=True,
            note='special-quota notice / named list'),    RawFile('GuidelinesEligibilityRevised.pdf',
            'https://allduniv.ac.in/upload/file_collection/GuidelinesEligibilityRevised.pdf',
            'rules'),
]


@dataclass(frozen=True)
class Table:
    bq_name: str
    parquet: str
    grain: str

    @property
    def gcs_path(self) -> str:
        return f"{GCS_PREFIX}/clean/{self.parquet}"

    @property
    def gcs_uri(self) -> str:
        return f"gs://{GCS_BUCKET}/{self.gcs_path}"

    @property
    def local_path(self) -> Path:
        return CLEAN / self.parquet

    @property
    def bq_table_id(self) -> str:
        return f"{BQ_PROJECT}.{BQ_DATASET}.{self.bq_name}"


TABLES = [
    Table("allahabadug_fact_cutoffs", "allahabadug_fact_cutoffs.parquet",
          "(year, program, round, category, source_file)"),
]
