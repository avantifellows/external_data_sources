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
    {"id": "josaa", "title": "JoSAA engineering admissions (2016-2025)",
     "blurb": "IIT/NIT/IIIT/GFTI opening and closing ranks for every seat bucket and round, consolidated from the official JoSAA portal.",
     "special": "josaa"},
    {"id": "kcet", "title": "KCET 2025 engineering admissions (Karnataka)",
     "blurb": "KEA engineering cutoffs: the official Round-3 documents and the tables extracted from them.",
     "files": [
        ("kcet/raw/KA_engg_2025_GEN_R3.pdf", "Karnataka — Round-3 cutoffs, General pool", "raw", 2025),
        ("kcet/raw/KA_engg_2025_HK_R3.pdf", "Karnataka — Round-3 cutoffs, Hyderabad-Karnataka pool", "raw", 2025),
        ("kcet/raw/KA_engg_2025_draft_seat_matrix.pdf", "Karnataka — Draft seat matrix", "raw", 2025),
        ("kcet/raw/KA_engg_2025_all_cutoffs_R3.csv", "Karnataka — All cutoffs by college and category (Round 3)", "extracted", 2025),
        ("kcet/raw/KA_engg_closing_ranks_govt_2024.csv", "Karnataka — Closing ranks, government colleges only", "extracted", 2024),
     ]},
    {"id": "mhtcet", "title": "MHT-CET 2025 admissions (Maharashtra)",
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
    {"id": "tgeapcet", "title": "TG-EAPCET 2025 engineering admissions (Telangana)",
     "blurb": "The Convener's last-rank statements for all three phases, and the tables extracted from them.",
     "files": [
        ("tgeapcet/raw/pdfs/TGEAPCET_2025_LASTRANKS_FirstPhase.pdf", "Telangana — Last ranks, Phase 1", "raw", 2025),
        ("tgeapcet/raw/pdfs/TGEAPCET_2025_LASTRANKS_SecondPhase.pdf", "Telangana — Last ranks, Phase 2", "raw", 2025),
        ("tgeapcet/raw/pdfs/TGEAPCET_2025_FINALPHASE_LASTRANKS.pdf", "Telangana — Last ranks, Final phase", "raw", 2025),
        ("tgeapcet/raw/TG_engg_all_cutoffs_2025.csv", "Telangana — All cutoffs by college, branch and category", "extracted", 2025),
        ("tgeapcet/raw/TG_engg_closing_ranks_govt_2025.csv", "Telangana — Closing ranks, government colleges only", "extracted", 2025),
        ("tgeapcet/raw/TG_engg_consolidated_5cat_govt_2025.csv", "Telangana — Consolidated closings, 5-category (government colleges)", "extracted", 2025),
     ]},
    {"id": "gujcet", "title": "GUJCET / ACPC admissions (Gujarat)",
     "blurb": "ACPC closure documents for engineering (2025) and pharmacy (2024), and the tables extracted from them.",
     "files": [
        ("gujcet/raw/pdfs/GJ_ACPC_2025_Final_RankAndMarks.pdf", "Gujarat — ACPC final ranks and marks, engineering", "raw", 2025),
        ("gujcet/raw/pdfs/GJ_ACPC_2024_Pharmacy_Closure.pdf", "Gujarat — ACPC pharmacy closure", "raw", 2024),
        ("gujcet/raw/GJ_engg_all_cutoffs_2025.csv", "Gujarat — All cutoffs, engineering", "extracted", 2025),
        ("gujcet/raw/GJ_engg_closing_ranks_govt_2025.csv", "Gujarat — Closing ranks, government colleges only (engineering)", "extracted", 2025),
        ("gujcet/raw/GJ_pharm_all_cutoffs_2024.csv", "Gujarat — All cutoffs, pharmacy", "extracted", 2024),
        ("gujcet/raw/GJ_pharm_closing_ranks_govt_2024.csv", "Gujarat — Closing ranks, government colleges only (pharmacy)", "extracted", 2024),
     ]},
    {"id": "tnea", "title": "TNEA 2025 engineering admissions (Tamil Nadu)",
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
        "id": "neet",
        "title": "NEET-UG 2025 admissions",
        "blurb": "Medical/dental counselling cutoffs: the official documents and the tables we extracted from them, across the All India Quota and 26 state quotas.",
        "files": files,
    }]

    for spec in EXAM_DATASETS:
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

        if spec.get("parquet_as_extracted"):
            import pandas as pd, tempfile, os
            src_pq, dest_csv, title, year = spec["parquet_as_extracted"]
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
        datasets.append({"id": spec["id"], "title": spec["title"],
                         "blurb": spec["blurb"], "files": entries2})

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
