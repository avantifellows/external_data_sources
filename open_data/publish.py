#!/usr/bin/env python3
"""
Publish curated datasets to the PUBLIC bucket (gs://avantifellows-open-data/).

Publication is a deliberate act: nothing reaches the public bucket except what
this script copies; the private bucket's IAM never changes (it holds
student-level data that must never be exposed).

What is shared, per dataset: RAW official documents (verbatim — They are public
government publications; provenance is the point) and EXTRACTED tables (our
parsers' output). Processed/derived artifacts (projections, models) are NOT
shared — those are editorial work, not source data.

Scrubbing: extracted CSVs sometimes carry person-identifier columns (name /
roll numbers / raw OCR lines embedding names). Those columns are dropped at
publish time and every drop is recorded in the manifest.

Every file gets a human TITLE with the convention "<Group> — <what it is>",
where Group is the state or authority ("Karnataka", "All India Quota"). The
Datasets page groups raw documents and extracted tables side by side per Group
by splitting on the em-dash, so keep the convention. Filenames are secondary. Multi-part documents (page-image registers) are zipped
into one archive.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import date

from google.cloud import storage

SRC_BUCKET = "avantifellows-external-data"
DST_BUCKET = "avantifellows-open-data"

PII_COLS = {"name", "roll", "neet_roll", "regno", "reg_no", "raw"}

# ── NEET: file -> human title ─────────────────────────────────────────────────
RAW_TITLES = {
    "aiq.pdf": "All India Quota — MCC allotment, Round 3",
    "aiq_r1.pdf": "All India Quota — MCC allotment, Round 1",
    "andhra.pdf": "Andhra Pradesh — State counselling cutoffs",
    "gujarat.pdf": "Gujarat — State counselling cutoffs",
    "himachal.pdf": "Himachal Pradesh — State counselling cutoffs",
    "karnataka.pdf": "Karnataka — State counselling cutoffs",
    "kerala.pdf": "Kerala — State counselling cutoffs",
    "kerala_cee_2025_mbbs_p1_lastranks.pdf": "Kerala — 2025 MBBS/BDS last ranks (CEE), Phase 1",
    "kerala_cee_2025_mbbs_p2_lastranks.pdf": "Kerala — 2025 MBBS/BDS last ranks (CEE), Phase 2",
    "kerala_cee_2025_mbbs_p3_lastranks.pdf": "Kerala — 2025 MBBS/BDS last ranks (CEE), Phase 3 (final)",
    "kerala_cee_2025_allied_p1_lastranks.pdf": "Kerala — 2025 AYUSH and allied last ranks (CEE), Phase 1",
    "kerala_cee_2025_allied_p2_lastranks.pdf": "Kerala — 2025 AYUSH and allied last ranks (CEE), Phase 2",
    "kerala_cee_2025_allied_p3_lastranks.pdf": "Kerala — 2025 AYUSH and allied last ranks (CEE), Phase 3 (final)",
    "kerala_ranklist.pdf": "Kerala — State rank list",
    "maharashtra.pdf": "Maharashtra — State counselling cutoffs (Round 3)",
    "mp.pdf": "Madhya Pradesh — State counselling cutoffs",
    "punjab.pdf": "Punjab — State counselling cutoffs",
    "telangana.pdf": "Telangana — State counselling cutoffs",
    "tg_meritlist.pdf": "Telangana — State merit list",
    "westbengal.pdf": "West Bengal — State counselling cutoffs",
    "chandigarh-gmch32-2025-admitted-list.pdf": "Chandigarh — GMCH-32 admitted-student list",
    "mizoram-2025-neet-seat-matrix.pdf": "Mizoram — NEET seat matrix",
    "mizoram-2026-provisional-merit-list.pdf": "Mizoram — Provisional merit list (2026 cycle)",
    "ladakh-2025-central-pool-selected-list.pdf": "Ladakh — Central-pool selected list",
    "arunachal-2025-r1-allotment.pdf": "Arunachal Pradesh — Round-1 allotment",
    "manipur-2025-r2-state-quota-allotment.pdf": "Manipur — Round-2 state-quota allotment",
    "meghalaya-2025-mbbs-selected-list.pdf": "Meghalaya — MBBS selected list",
    "nagaland-2025-final-selected-list.pdf": "Nagaland — Final selected list",
    "tripura-2025-r1-allotment.pdf": "Tripura — Round-1 allotment",
    "haryana-neet-ug-2025-round1-allotment.pdf": "Haryana — Round-1 allotment",
    "rajasthan-neet-merit-list.pdf": "Rajasthan — State merit list",
    "191568Odisha R3 MBBS Cutoff 2025.pdf": "Odisha — Round-3 MBBS cutoffs",
    "599136R1 Allotment 2025.pdf": "Odisha — Round-1 allotment",
    "2025072943.pdf": "Uttarakhand — State counselling cutoffs",
    "JH_R1_2025.pdf": "Jharkhand — Round-1 allotment",
    "JH_R3_2025.pdf": "Jharkhand — Round-3 allotment",
    "nmc-dci-roster-2025-26/mbbs_all_colleges_2025-26.csv": "NMC roster — All MBBS colleges with management type (2025-26)",
    "nmc-dci-roster-2025-26/bds_all_colleges_2025-26.csv": "DCI roster — All BDS colleges with management type (2025-26)",
}
ZIP_BUNDLES = {  # prefix -> (zip name, title)
    "mizoram-zmch-2025-admitted/": (
        "mizoram-zmch-2025-admitted-register.zip",
        "Mizoram — ZMCH admitted-student register (10 page images, zipped)"),
}
EXCLUDE_RAW = {"NTA NEET 2025.xlsx"}

EXTRACTED_TITLES = {
    "neet_aiq_2025_cutoffs.csv": "All India Quota — Closing ranks by college and category (all college types)",
    "neet_andhra_2025_r3_cutoffs.csv": "Andhra Pradesh — Closing ranks by college and category (all college types, Round 3)",
    "neet_gujarat_2025_cutoffs.csv": "Gujarat — Closing ranks by college and category (all college types)",
    "neet_himachal_2025_r3_cutoffs.csv": "Himachal Pradesh — Closing ranks by college and category (all college types, Round 3)",
    "neet_karnataka_2025_r3_cutoffs.csv": "Karnataka — Closing ranks by college and category (all college types, Round 3)",
    "neet_kerala_2025_cutoffs.csv": "Kerala — Closing ranks by college and category (all college types)",
    "neet_maharashtra_2025_r3_cutoffs.csv": "Maharashtra — Closing ranks by college and category (all college types, Round 3)",
    "neet_mp_2025_cutoffs.csv": "Madhya Pradesh — Closing ranks by college and category (all college types)",
    "neet_punjab_2025_cutoffs.csv": "Punjab — Closing ranks by college and category (all college types)",
    "neet_telangana_2025_cutoffs.csv": "Telangana — Closing ranks by college and category (all college types)",
    "neet_westbengal_2025_cutoffs.csv": "West Bengal — Closing ranks by college and category (all college types)",
    "AP_closing_ranks_state_govt_2025.csv": "Andhra Pradesh — Closing ranks, government colleges only",
    "AS_all_allotments_2025.csv": "Assam — Full allotment list",
    "BR_closing_ranks_state_govt_2025.csv": "Bihar — Closing ranks, government colleges only (Round 3)",
    "CG_all_allotments_2025.csv": "Chhattisgarh — Full allotment list",
    "HP_closing_ranks_state_govt_2025.csv": "Himachal Pradesh — Closing ranks, government colleges only (Round 3)",
    "JK_closing_ranks_state_govt_2025.csv": "Jammu & Kashmir — Closing ranks, government colleges only",
    "JK_meritlist_state_rank_air.csv": "Jammu & Kashmir — State-rank to All-India-Rank bridge",
    "KA_closing_ranks_state_govt_2025.csv": "Karnataka — Closing ranks, government colleges only",
    "KA_college_govt_classification.csv": "Karnataka — Government / private college classification",
    "TG_closing_ranks_state_govt_2025.csv": "Telangana — Closing ranks, government colleges only",
    "TN_closing_ranks_state_govt_2025.csv": "Tamil Nadu — Closing ranks and marks, government colleges only",
    "UK_closing_ranks_state_govt_2025.csv": "Uttarakhand — Closing ranks, government colleges only (Round 3)",
    "UP_closing_ranks_state_govt_2025.csv": "Uttar Pradesh — Closing ranks, government colleges only",
    "national_closing_ranks_unified_AIR_2025.csv": "All states — Unified closing ranks on the All-India-Rank scale",
    "govt_medical_closing_ranks_r1_2025.csv": "All India Quota — Closing ranks, government colleges only (Round 1)",
    "govt_medical_closing_ranks_r1_2025_pivot.csv": "All India Quota — Closing ranks, government colleges only, pivoted (Round 1)",
    "haryana-hr_closing_2025.csv": "Haryana — Closing ranks and marks by college (Round 1)",
    "haryana-hr_allotments_2025.csv": "Haryana — Allotment list (Round 1)",
    "odisha-od_closing_2025.csv": "Odisha — Closing ranks by college (Round 3)",
    "odisha-od_allotments_2025.csv": "Odisha — Allotment list (Round 3)",
    "odisha-od_rank_air_bridge_2025.csv": "Odisha — State-rank to All-India-Rank bridge (5,817 pairs)",
    "rajasthan-rj_closing_2025.csv": "Rajasthan — Closing ranks by college (Round 1)",
    "rajasthan-rj_allotments_2025.csv": "Rajasthan — Allotment list (Round 1)",
    "rajasthan-rj_meritlist_2025.csv": "Rajasthan — State merit list (marks & ranks)",
    "AR_2025_allotments.csv": "Arunachal Pradesh — Round-1 allotments (transcribed)",
    "ML_2025_selected_list.csv": "Meghalaya — Selected list (transcribed)",
    "MN_allotments_ocr.csv": "Manipur — Round-2 allotments (transcribed)",
    "NL_2025_selected_list.csv": "Nagaland — Selected list (partially recovered scan)",
    "mizoram-zmch_2025_admitted.csv": "Mizoram — ZMCH admitted-student register (transcribed)",
    "tripura-tripura_2025_r1_allotments.csv": "Tripura — Round-1 allotments (transcribed)",
}
EXCLUDE_EXTRACTED = {"neet_2026_matrix_all.csv"}    # a derived projection, not shared


# ── other exams: (src_path, title, kind, year) — raw docs verbatim, extracted tables scrubbed
EXAM_DATASETS = [
    {"id": "josaa", "category": "admissions", "title": "JoSAA engineering admissions (2016-2025)",
     "source": {"label": "josaa.admissions.nic.in", "url": "https://josaa.admissions.nic.in/"},
     "blurb": "IIT/NIT/IIIT/GFTI opening and closing ranks for every seat bucket and round, consolidated from the official JoSAA portal.",
     "special": "josaa"},
    {"id": "kcet", "category": "admissions", "title": "KCET 2025 engineering admissions (Karnataka)",
     "source": {"label": "KEA, cetonline.karnataka.gov.in", "url": "https://cetonline.karnataka.gov.in/keawebentry456/ugcet2025/"},
     "blurb": "KEA engineering cutoffs: the official Round-3 documents and the tables extracted from them.",
     "files": [
        ("kcet/raw/KA_engg_2025_GEN_R3.pdf", "Karnataka — Round-3 cutoffs, General pool", "raw", 2025),
        ("kcet/raw/KA_engg_2025_HK_R3.pdf", "Karnataka — Round-3 cutoffs, Hyderabad-Karnataka pool", "raw", 2025),
        ("kcet/raw/KA_engg_2025_draft_seat_matrix.pdf", "Karnataka — Draft seat matrix", "raw", 2025),
        ("kcet/raw/KA_engg_2025_all_cutoffs_R3.csv", "Karnataka — All cutoffs by college and category (Round 3)", "extracted", 2025),
        ("kcet/raw/KA_engg_closing_ranks_govt_2024.csv", "Karnataka — Closing ranks, government colleges only", "extracted", 2024),
     ]},
    {"id": "mhtcet", "category": "admissions", "title": "MHT-CET 2025 admissions (Maharashtra)",
     "source": {"label": "State CET Cell CAP portals, mahacet.org", "url": "https://fe2025.mahacet.org/"},
     "blurb": "State-quota closing ranks across engineering, pharmacy, architecture and B.Design, with the per-institute cutoff documents zipped by stream.",
     "files": [
        ("mhtcet/raw/MH_engg_state_quota_closing_ranks_2025.csv", "Maharashtra — State-quota closing ranks, engineering", "extracted", 2025),
        ("mhtcet/raw/MH_pharm_state_quota_closing_ranks_2025.csv", "Maharashtra — State-quota closing ranks, pharmacy", "extracted", 2025),
        ("mhtcet/raw/MH_arch_state_quota_closing_ranks_2025.csv", "Maharashtra — State-quota closing ranks, architecture", "extracted", 2025),
        ("mhtcet/raw/MH_bdesign_state_quota_closing_ranks_2025.csv", "Maharashtra — State-quota closing ranks, B.Design", "extracted", 2025),
     ],
     "zips": [
        ("mhtcet/raw/pdfs/engineering/", "mhtcet/raw/MH_engineering_institute_pdfs.zip", "Maharashtra — Institute cutoff documents, engineering (zipped)"),
        ("mhtcet/raw/pdfs/pharmacy/", "mhtcet/raw/MH_pharmacy_institute_pdfs.zip", "Maharashtra — Institute cutoff documents, pharmacy (zipped)"),
        ("mhtcet/raw/pdfs/architecture/", "mhtcet/raw/MH_architecture_institute_pdfs.zip", "Maharashtra — Institute cutoff documents, architecture (zipped)"),
        ("mhtcet/raw/pdfs/bdesign/", "mhtcet/raw/MH_bdesign_institute_pdfs.zip", "Maharashtra — Institute cutoff documents, B.Design (zipped)"),
     ]},
    {"id": "tgeapcet", "category": "admissions", "title": "TG-EAPCET 2025 engineering admissions (Telangana)",
     "source": {"label": "tgeapcetd.nic.in", "url": "https://tgeapcetd.nic.in/"},
     "blurb": "The Convener's last-rank statements for all three phases, and the tables extracted from them.",
     "files": [
        ("tgeapcet/raw/pdfs/TGEAPCET_2025_LASTRANKS_FirstPhase.pdf", "Telangana — Last ranks, Phase 1", "raw", 2025),
        ("tgeapcet/raw/pdfs/TGEAPCET_2025_LASTRANKS_SecondPhase.pdf", "Telangana — Last ranks, Phase 2", "raw", 2025),
        ("tgeapcet/raw/pdfs/TGEAPCET_2025_FINALPHASE_LASTRANKS.pdf", "Telangana — Last ranks, Final phase", "raw", 2025),
        ("tgeapcet/raw/TG_engg_all_cutoffs_2025.csv", "Telangana — All cutoffs by college, branch and category", "extracted", 2025),
        ("tgeapcet/raw/TG_engg_closing_ranks_govt_2025.csv", "Telangana — Closing ranks, government colleges only", "extracted", 2025),
        ("tgeapcet/raw/TG_engg_consolidated_5cat_govt_2025.csv", "Telangana — Consolidated closings, 5-category (government colleges)", "extracted", 2025),
     ]},
    {"id": "gujcet", "category": "admissions", "title": "GUJCET / ACPC admissions (Gujarat)",
     "blurb": "ACPC closure documents for engineering (2025) and pharmacy (2024), and the tables extracted from them.",
     "files": [
        ("gujcet/raw/pdfs/GJ_ACPC_2025_Final_RankAndMarks.pdf", "Gujarat — ACPC final ranks and marks, engineering", "raw", 2025),
        ("gujcet/raw/pdfs/GJ_ACPC_2024_Pharmacy_Closure.pdf", "Gujarat — ACPC pharmacy closure", "raw", 2024),
        ("gujcet/raw/GJ_engg_all_cutoffs_2025.csv", "Gujarat — All cutoffs, engineering", "extracted", 2025),
        ("gujcet/raw/GJ_engg_closing_ranks_govt_2025.csv", "Gujarat — Closing ranks, government colleges only (engineering)", "extracted", 2025),
        ("gujcet/raw/GJ_pharm_all_cutoffs_2024.csv", "Gujarat — All cutoffs, pharmacy", "extracted", 2024),
        ("gujcet/raw/GJ_pharm_closing_ranks_govt_2024.csv", "Gujarat — Closing ranks, government colleges only (pharmacy)", "extracted", 2024),
     ]},
    {"id": "tnea", "category": "admissions", "title": "TNEA 2025 engineering admissions (Tamil Nadu)",
     "source": {"label": "cutoff.tneaonline.org", "url": "https://cutoff.tneaonline.org/"},
     "blurb": "Final-round cutoff marks and state merit ranks for every college and branch, pulled from the official TNEA portal.",
     "files": [
        ("tnea/raw/TN_TNEA_2025_cutoff_marks.csv", "Tamil Nadu — Cutoff marks by college and branch (TNEA portal)", "raw", 2025),
        ("tnea/raw/TN_TNEA_2025_state_merit_ranks.csv", "Tamil Nadu — State merit ranks by college and branch (TNEA portal)", "raw", 2025),
     ],
     # the pipeline's final table IS the extraction here (marks and ranks joined,
     # the seven communities unpacked, college types from the official DOTE codes)
     "parquet_as_extracted": ("tnea/clean/tnea_fact_cutoffs.parquet",
        "tnea/extracted/tnea_cutoffs_2025.csv",
        "Tamil Nadu — Cutoff marks and merit ranks, by college, branch and community", 2025)},
    {"id": "wbjee", "category": "admissions", "title": "WBJEE engineering admissions, 2021-2026 (West Bengal)",
     "source": {"label": "wbjeeb.nic.in/ewbjee", "url": "https://wbjeeb.nic.in/ewbjee/"},
     "blurb": "Six years of WBJEEB's opening and closing ranks - including the live 2026 counselling - as the official ORCR pages and as one extracted table.",
     "files": [
        ("wbjee/raw/WBJEE_2021_ORCR.html", "West Bengal — 2021 ORCR page, engineering", "raw", 2021),
        ("wbjee/raw/WBJEE_2022_ORCR.html", "West Bengal — 2022 ORCR page, engineering", "raw", 2022),
        ("wbjee/raw/WBJEE_2023_ORCR.html", "West Bengal — 2023 ORCR page, engineering", "raw", 2023),
        ("wbjee/raw/WBJEE_2024_ORCR.html", "West Bengal — 2024 ORCR page, engineering", "raw", 2024),
        ("wbjee/raw/WBJEE_2025_ORCR.html", "West Bengal — 2025 ORCR page, engineering", "raw", 2025),
        ("wbjee/raw/WBJEE_2026_ORCR.html", "West Bengal — 2026 ORCR page, engineering (live cycle)", "raw", 2026),
        ("wbjee/raw/WBJEE_pharmacy_2026_ORCR.html", "West Bengal — 2026 ORCR page, pharmacy (live cycle)", "raw", 2026),
     ],
     # one table across all six years: every round x institute x program x
     # seat-type x quota x category bucket, categories kept in each year's own
     # vocabulary plus a canonical column
     "parquet_as_extracted": ("wbjee/clean/wbjee_fact_cutoffs.parquet",
        "wbjee/extracted/wbjee_cutoffs_2021_2026.csv",
        "West Bengal — Opening and closing ranks, all rounds and categories (2021-2026)", 2026)},
    {"id": "keam", "category": "admissions", "title": "KEAM admissions, 2025-2026 (Kerala)",
     "source": {"label": "cee.kerala.gov.in", "url": "https://cee.kerala.gov.in/keam2026/last_rank"},
     "blurb": "CEE Kerala's last-rank tables for the KEAM-exam streams - engineering, architecture, pharmacy - including the live 2026 counselling, plus the extracted engineering table. Kerala's NEET-based medical rounds are under the NEET-UG dataset above. CEE keeps only the last two cycles online.",
     "files": [
        ("keam/raw/KEAM_2026_engg_trial.pdf", "Kerala — 2026 engineering last ranks, Trial allotment (live cycle)", "raw", 2026),
        ("keam/raw/KEAM_2026_engg_p1.pdf", "Kerala — 2026 engineering last ranks, Phase 1 (live cycle)", "raw", 2026),
        ("keam/raw/KEAM_2026_engg_p2.pdf", "Kerala — 2026 engineering last ranks, Phase 2 (live cycle)", "raw", 2026),
        ("keam/raw/KEAM_2026_arch_p1.pdf", "Kerala — 2026 architecture last ranks, Phase 1", "raw", 2026),
        ("keam/raw/KEAM_2026_arch_p2_provisional.pdf", "Kerala — 2026 architecture last ranks, Phase 2 (provisional)", "raw", 2026),
        ("keam/raw/KEAM_2026_bpharm_p1.pdf", "Kerala — 2026 B.Pharm last ranks, Phase 1", "raw", 2026),
        ("keam/raw/KEAM_2026_bpharm_p2.pdf", "Kerala — 2026 B.Pharm last ranks, Phase 2", "raw", 2026),
        ("keam/raw/KEAM_2025_engg_p1.pdf", "Kerala — 2025 engineering last ranks, Phase 1", "raw", 2025),
        ("keam/raw/KEAM_2025_engg_p2.pdf", "Kerala — 2025 engineering last ranks, Phase 2 (final)", "raw", 2025),
        ("keam/raw/KEAM_2025_arch_p1.pdf", "Kerala — 2025 architecture last ranks, Phase 1", "raw", 2025),
        ("keam/raw/KEAM_2025_bpharm_p1.pdf", "Kerala — 2025 B.Pharm last ranks, Phase 1", "raw", 2025),
        ("keam/raw/KEAM_2025_bpharm_p2.pdf", "Kerala — 2025 B.Pharm last ranks, Phase 2", "raw", 2025),
     ],
     "parquet_as_extracted": ("keam/clean/keam_fact_cutoffs.parquet",
        "keam/extracted/keam_engineering_last_ranks_2025_2026.csv",
        "Kerala — Engineering last ranks, all phases and categories (2025-2026)", 2026)},
    {"id": "apeapcet", "category": "admissions", "title": "AP EAPCET 2025 engineering admissions (Andhra Pradesh)",
     "source": {"label": "APSCHE Common Admissions Portal, cap.apcfss.in", "url": "https://cap.apcfss.in/"},
     "blurb": "APSCHE's consolidated last-rank statement - every college, branch, category and gender pool - and the table extracted from it. Archived here because APSCHE's past-year URLs rot quickly.",
     "files": [
        ("apeapcet/raw/AP_EAPCET_2025_lastranks.pdf", "Andhra Pradesh — 2025 consolidated last ranks (all colleges and categories)", "raw", 2025),
     ],
     "parquet_as_extracted": ("apeapcet/clean/apeapcet_fact_cutoffs.parquet",
        "apeapcet/extracted/apeapcet_last_ranks_2025.csv",
        "Andhra Pradesh — Last ranks by college, branch, category and gender (2025)", 2025)},
    {"id": "ojee", "category": "admissions", "title": "OJEE 2025 B.Tech admissions (Odisha)",
     "source": {"label": "ojee.nic.in", "url": "https://ojee.nic.in/opening-closing-rank/"},
     "blurb": "The OJEE Cell's opening and closing ranks for B.Tech counselling - the ranks are JEE (Main) ranks, since Odisha admits first-year B.Tech on JEE Main - plus the extracted table.",
     "files": [
        ("ojee/raw/OD_OJEE_2025_btech_orcr.pdf", "Odisha — 2025 B.Tech opening and closing ranks (JEE Main ranks)", "raw", 2025),
     ],
     "parquet_as_extracted": ("ojee/clean/ojee_fact_cutoffs.parquet",
        "ojee/extracted/ojee_btech_last_ranks_2025.csv",
        "Odisha — Opening and closing ranks by college, programme and category (2025)", 2025)},
]



# ── institutions & education statistics (all public government sources) ──────
AISHE_REPORT_YEARS = ["2012-13","2013-14","2014-15","2015-16","2016-17","2017-18",
                      "2018-19","2019-20","2020-21","2021-22","2022-23","2023-24"]
STAT_DATASETS = [
    {"id": "collegefees", "category": "admissions",
     "title": "College fees and hostel charges (JoSAA + KCET, 2025-26)",
     "blurb": "Tuition, total institute fees and hostel/mess charges per college, course and seat category, hand-collected from each college's own published fee structure — the source link travels on every row. JoSAA colleges effectively complete; KCET partial (25 colleges); entry-year figures.",
     "parquet_as_extracted": [
        ("collegefees/clean/collegefees_fees.parquet", "collegefees/extracted/collegefees_fees.csv", "College fees — Tuition, total and hostel by college, course and category", "2025-26"),
     ]},

    {"id": "aishe", "category": "education-statistics",
     "title": "AISHE higher-education survey",
     "blurb": "The Ministry of Education's All India Survey on Higher Education: every annual report since 2012-13, the full institution directories, and the tables we extracted from them.",
     "source": {"label": "aishe.gov.in", "url": "https://aishe.gov.in/"},
     "files": (
        [(f"aishe/raw/aishe_{y}_final_report.pdf", f"Final reports — AISHE {y}", "raw", int(y[:4])+1) for y in AISHE_REPORT_YEARS] +
        [("aishe/raw/institution_directory/College-ALL COLLEGE.xlsx", "Institution directory — All colleges", "raw", 2024),
         ("aishe/raw/institution_directory/University-ALL UNIVERSITIES.xlsx", "Institution directory — All universities", "raw", 2024),
         ("aishe/raw/institution_directory/Standalone-ALL_STANDALONE_with_URLs.xlsx", "Institution directory — Standalone institutions", "raw", 2024),
         ("aishe/raw/institution_directory/R & D Institutes.xlsx", "Institution directory — Research institutions", "raw", 2024)]),
     "parquet_as_extracted": [
        ("aishe/clean/aishe_dim_colleges.parquet", "aishe/extracted/aishe_colleges.csv", "Extracted tables — Colleges", 2024),
        ("aishe/clean/aishe_dim_universities.parquet", "aishe/extracted/aishe_universities.csv", "Extracted tables — Universities", 2024),
        ("aishe/clean/aishe_dim_standalone_institutions.parquet", "aishe/extracted/aishe_standalone.csv", "Extracted tables — Standalone institutions", 2024),
        ("aishe/clean/aishe_dim_research_institutions.parquet", "aishe/extracted/aishe_research.csv", "Extracted tables — Research institutions", 2024),
        ("aishe/clean/higher_ed.parquet", "aishe/extracted/aishe_higher_ed_timeseries.csv", "Extracted tables — Enrolment time series", "2012-2022"),
     ]},
    {"id": "nirf", "category": "education-statistics",
     "title": "NIRF rankings and institute metrics",
     "blurb": "National Institutional Ranking Framework: ranks, bands and scores by category and year, plus the placement, salary, intake and student-strength figures institutes file — parsed first-party from NIRF's own pages and per-institute PDFs for Engineering and Medical.",
     "source": {"label": "nirfindia.org", "url": "https://www.nirfindia.org/"},
     "files": [
        ("nirf/raw/dcs/ranking_pages.zip", "NIRF — Ranking, band and participant pages, as published", "raw", "2016-2025"),
        ("nirf/raw/dcs/dcs_pdfs_engineering_2019-2025.zip", "NIRF — Institute data-submission PDFs, Engineering", "raw", "2019-2025"),
        ("nirf/raw/dcs/dcs_pdfs_medical_2019-2025.zip", "NIRF — Institute data-submission PDFs, Medical", "raw", "2019-2025"),
        ("nirf/raw/dcs/dcs_pdfs_university_2019-2025.zip", "NIRF — Institute data-submission PDFs, University track", "raw", "2019-2025"),
     ],
     # NOT published: nirf_aggregate (a derived pivot of master — policy says
     # derived artifacts stay out) and the Dataful strength extract for the
     # two categories the first-party tables cover better. One file per
     # distinct thing; scope in the title.
     "parquet_as_extracted": [
        ("nirf/clean/nirf_rankings.parquet", "nirf/extracted/nirf_rankings.csv", "NIRF — Rankings and bands by category and year", "2016-2025"),
        ("nirf/clean/nirf_master.parquet", "nirf/extracted/nirf_master.csv", "NIRF — All submitted metrics, 9 categories (third-party extract)", "2019-2025"),
        ("nirf/clean/nirf_strength.parquet", "nirf/extracted/nirf_strength.csv", "NIRF — Student strength, 9 categories (third-party extract)", "2016-2025"),
        ("nirf/clean/nirf_dcs_placements.parquet", "nirf/extracted/nirf_dcs_placements.csv", "NIRF — Placements and median salary, institute-filed (Engineering, Medical, University)", "2019-2025"),
        ("nirf/clean/nirf_dcs_intake.parquet", "nirf/extracted/nirf_dcs_intake.csv", "NIRF — Sanctioned intake by program level (Engineering, Medical, University)", "2019-2025"),
        ("nirf/clean/nirf_dcs_strength.parquet", "nirf/extracted/nirf_dcs_strength.csv", "NIRF — Student strength and demographics, institute-filed (all three tracks)", "2019-2025"),
        ("nirf/clean/nirf_dcs_institution.parquet", "nirf/extracted/nirf_dcs_institution.csv", "NIRF — PhD and faculty counts, institute-filed (all three tracks)", "2019-2025"),
        ("nirf/clean/nirf_participants.parquet", "nirf/extracted/nirf_participants.csv", "NIRF — All participating institutes (Engineering + Medical)", "2016-2025"),
     ]},
    {"id": "naac", "category": "education-statistics",
     "title": "NAAC accreditation",
     "blurb": "Accredited institutions with grades, CGPA and cycle, as published by NAAC.",
     "source": {"label": "naac.gov.in", "url": "http://naac.gov.in/"},
     "files": [
        ("naac/raw/Institutions_accredited_by_NAAC_having_valid_accreditation-as_on_14082025_1.xlsx",
         "NAAC — Accredited institutions (as on 14 Aug 2025)", "raw", 2025)],
     "parquet_as_extracted": [
        ("naac/clean/naac_dim_colleges.parquet", "naac/extracted/naac_colleges.csv", "NAAC — Colleges with grade and CGPA", 2025),
        ("naac/clean/naac_dim_universities.parquet", "naac/extracted/naac_universities.csv", "NAAC — Universities with grade and CGPA", 2025),
     ]},
    {"id": "aicte", "category": "education-statistics",
     "title": "AICTE approved-institution intake",
     "blurb": "Sanctioned intake across AICTE-approved institutions, as national, state and institution-type panels.",
     "source": {"label": "aicte-india.org", "url": "https://www.aicte-india.org/"},
     "files": [
        ("aicte/raw/panel_national.csv", "AICTE — National intake panel", "raw", 2025),
        ("aicte/raw/panel_state.csv", "AICTE — State intake panel", "raw", 2025),
        ("aicte/raw/panel_inst_type.csv", "AICTE — Institution-type intake panel", "raw", 2025)]},
    {"id": "nmc", "category": "education-statistics",
     "title": "NMC medical seat matrix",
     "blurb": "The National Medical Commission's MBBS seat matrix: every medical college with intake and management type.",
     "source": {"label": "nmc.org.in", "url": "https://www.nmc.org.in/"},
     "files": [
        ("nmc/raw/nmc_mbbs_seat_matrix_2024-25.pdf", "NMC — MBBS seat matrix 2024-25", "raw", 2024)],
     "parquet_as_extracted": [
        ("nmc/clean/mbbs_seats.parquet", "nmc/extracted/nmc_mbbs_seats.csv", "NMC — MBBS seats by college", 2024)]},
    {"id": "udise", "category": "education-statistics",
     "title": "UDISE+ school enrolment",
     "blurb": "School enrolment from the Ministry of Education's UDISE+ system.",
     "source": {"label": "udiseplus.gov.in", "url": "https://udiseplus.gov.in/"},
     "files": [
        ("udise/raw/udise_2024-25_enrolment.xlsx", "UDISE+ — Enrolment 2024-25", "raw", 2025)],
     "parquet_as_extracted": [
        ("udise/clean/enrolment.parquet", "udise/extracted/udise_enrolment.csv", "UDISE+ — Enrolment, extracted", 2025)]},
    {"id": "moe", "category": "education-statistics",
     "title": "Board examination results (MoE)",
     "blurb": "Class X and XII results across all Indian boards, from the Ministry of Education's annual publications.",
     "source": {"label": "education.gov.in", "url": "https://www.education.gov.in/"},
     "files": [
        ("moe/raw/moe_results_secondary_hs_2020.pdf", "MoE reports — Results of secondary and higher-secondary examinations, 2020", "raw", 2020),
        ("moe/raw/moe_results_secondary_hs_2021.pdf", "MoE reports — Results of secondary and higher-secondary examinations, 2021", "raw", 2021),
        ("moe/raw/moe_results_secondary_hs_2022.pdf", "MoE reports — Results of secondary and higher-secondary examinations, 2022", "raw", 2022),
        ("moe/raw/moe_results_secondary_hs_2024.pdf", "MoE reports — Results of secondary and higher-secondary examinations, 2024", "raw", 2024)],
     "parquet_as_extracted": [
        ("moe/clean/moe_fact_board_exam_results.parquet", "moe/extracted/moe_board_results.csv", "MoE reports — Board results, extracted (no 2023)", "2020-2024")]},
    {"id": "nas", "category": "education-statistics",
     "title": "National Achievement Survey 2021",
     "blurb": "NCERT's NAS 2021 learning-outcome survey, with our extracted state-level proficiency table.",
     "source": {"label": "nas.gov.in", "url": "https://nas.gov.in/"},
     "zips": [
        ("nas/raw/", "nas/raw/NAS_2021_all_data.zip", "NAS 2021 — All published data files (zipped)")],
     "parquet_as_extracted": [
        ("nas/clean/state_proficiency.parquet", "nas/extracted/nas_state_proficiency.csv", "NAS 2021 — State proficiency, extracted", 2021)]},
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scrub_csv(data: bytes) -> tuple[bytes, list[str]]:
    rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        return data, []
    drop = [i for i, c in enumerate(rows[0]) if c.strip().lower() in PII_COLS]
    if not drop:
        return data, []
    keep = [i for i in range(len(rows[0])) if i not in drop]
    out = io.StringIO()
    w = csv.writer(out)
    for r in rows:
        w.writerow([r[i] if i < len(r) else "" for i in keep])
    return out.getvalue().encode(), [rows[0][i] for i in drop]


def main():
    c = storage.Client()
    src, dst = c.bucket(SRC_BUCKET), c.bucket(DST_BUCKET)

    # clean slate: the manifest is the truth, no stale objects
    for b in dst.list_blobs(prefix="neet/"):
        b.delete()

    files = []

    def add(dest, data, title, kind, year, fmt, removed=None):
        blob = dst.blob(dest)
        ctype = {"pdf": "application/pdf", "csv": "text/csv", "zip": "application/zip"}.get(fmt, "application/octet-stream")
        blob.upload_from_string(data, content_type=ctype)
        e = {"title": title, "path": dest, "kind": kind, "year": year,
             "format": fmt.upper(), "bytes": len(data), "sha256": sha(data),
             "url": f"https://storage.googleapis.com/{DST_BUCKET}/{dest}"}
        if removed:
            e["columns_removed"] = removed
        files.append(e)
        print(f"  {kind:9} {title}")

    # raw: zip bundles first
    for prefix, (zip_name, title) in ZIP_BUNDLES.items():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for b in src.list_blobs(prefix=f"neet/raw/{prefix}"):
                z.writestr(b.name.split("/")[-1], b.download_as_bytes())
        add(f"neet/raw/{zip_name}", buf.getvalue(), title, "raw", 2025, "zip")

    # raw: single documents
    for b in src.list_blobs(prefix="neet/raw/"):
        name = b.name.split("neet/raw/", 1)[1]
        if not name or name in EXCLUDE_RAW or any(name.startswith(p) for p in ZIP_BUNDLES):
            continue
        title = RAW_TITLES.get(name, name)
        add(f"neet/raw/{name}", b.download_as_bytes(), title, "raw", 2025,
            name.rsplit(".", 1)[-1].lower())

    # extracted
    for b in src.list_blobs(prefix="neet/extracted/"):
        name = b.name.split("neet/extracted/", 1)[1]
        if not name.endswith(".csv") or name in EXCLUDE_EXTRACTED:
            continue
        data, removed = scrub_csv(b.download_as_bytes())
        add(f"neet/extracted/{name}", data, EXTRACTED_TITLES.get(name, name),
            "extracted", 2025, "csv", removed)

    files.sort(key=lambda f: (f["kind"], f["title"]))
    datasets = [{
        "id": "neet", "category": "admissions",
        "title": "NEET-UG 2025 admissions",
        "category": "admissions",
        # each group here is one state whose document and table sit together, so an
        # extracted-only group genuinely means the source was never archived
        "note_missing_source": True,
        "source": {"label": "MCC (mcc.nic.in) and the state counselling authorities",
                   "url": "https://mcc.nic.in/"},
        "blurb": "Medical/dental counselling cutoffs: the official documents and the tables we extracted from them, across the All India Quota and 26 state quotas.",
        "files": files,
    }]

    for spec in EXAM_DATASETS + STAT_DATASETS:
        entries2 = []

        def add2(dest, data, title, kind, year, fmt, removed=None):
            blob = dst.blob(dest)
            ctype = {"pdf": "application/pdf", "csv": "text/csv", "zip": "application/zip"}.get(fmt, "application/octet-stream")
            blob.upload_from_string(data, content_type=ctype)
            e = {"title": title, "path": dest, "kind": kind, "year": year,
                 "format": fmt.upper(), "bytes": len(data), "sha256": sha(data),
                 "url": f"https://storage.googleapis.com/{DST_BUCKET}/{dest}"}
            if removed:
                e["columns_removed"] = removed
            entries2.append(e)
            print(f"  {kind:9} {title}")

        for prefix, dest, title in spec.get("zips", []):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for b in src.list_blobs(prefix=prefix):
                    z.writestr(b.name.split("/")[-1], b.download_as_bytes())
            add2(dest.replace("raw/", "raw/", 1), buf.getvalue(), title, "raw", 2025, "zip")

        for src_path, title, kind, year in spec.get("files", []):
            data = src.blob(src_path).download_as_bytes()
            removed = []
            if src_path.endswith(".csv") and kind != "raw":
                data, removed = scrub_csv(data)
            fmt = src_path.rsplit(".", 1)[-1].lower()
            add2(src_path, data, title, kind, year, fmt, removed)

        pae = spec.get("parquet_as_extracted")
        if pae:
            import pandas as pd, tempfile, os
            for src_pq, dest_csv, title, year in ([pae] if isinstance(pae, tuple) else pae):
                tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False).name
                src.blob(src_pq).download_to_filename(tmp)
                data = pd.read_parquet(tmp).to_csv(index=False).encode()
                os.unlink(tmp)
                add2(dest_csv, data, title, "extracted", year, "csv")

        if spec.get("special") == "josaa":
            # the consolidated table IS the extraction: opening/closing ranks verbatim
            # from the portal across every year and round -- no modelling, no editing
            import pandas as pd, tempfile, os
            tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False).name
            src.blob("josaa/clean/josaa_fact_cutoffs.parquet").download_to_filename(tmp)
            data = pd.read_parquet(tmp).to_csv(index=False).encode()
            os.unlink(tmp)
            add2("josaa/extracted/josaa_all_rounds_2016_2025.csv", data,
                 "JoSAA — Opening and closing ranks, every seat bucket and round",
                 "extracted", "2016-2025", "csv")

        entries2.sort(key=lambda f: (f["kind"], f["title"]))
        ds_entry = {"id": spec["id"], "category": spec.get("category", "admissions"),
                    "title": spec["title"], "blurb": spec["blurb"], "files": entries2}
        if spec.get("source"):
            ds_entry["source"] = spec["source"]
        datasets.append(ds_entry)

    manifest = {
        "generated": str(date.today()),
        "license": "CC BY 4.0 (our compilations); raw documents are mirrored government publications",
        "datasets": datasets,
    }
    mb = dst.blob("manifest.json")
    # the manifest is the mutable pointer — never let caches hold an old shape;
    # the files it points to are immutable-ish and can cache normally
    mb.cache_control = "no-cache"
    mb.upload_from_string(json.dumps(manifest, indent=1), content_type="application/json")
    total = sum(len(d["files"]) for d in datasets)
    print(f"\n{len(datasets)} datasets, {total} files -> https://storage.googleapis.com/{DST_BUCKET}/manifest.json")


if __name__ == "__main__":
    main()
