#!/usr/bin/env python3
"""
Publish curated datasets to the PUBLIC bucket (gs://avantifellows-open-data/).

Publication is a deliberate act: nothing reaches the public bucket except what
this script copies; the private bucket's IAM never changes (it holds
student-level data that must never be exposed).

What is shared, per dataset: RAW official documents (verbatim — they are public
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
    "andhra.pdf": "Andhra Pradesh — state counselling cutoffs",
    "gujarat.pdf": "Gujarat — state counselling cutoffs",
    "himachal.pdf": "Himachal Pradesh — state counselling cutoffs",
    "karnataka.pdf": "Karnataka — state counselling cutoffs",
    "kerala.pdf": "Kerala — state counselling cutoffs",
    "kerala_ranklist.pdf": "Kerala — state rank list",
    "maharashtra.pdf": "Maharashtra — state counselling cutoffs (Round 3)",
    "mp.pdf": "Madhya Pradesh — state counselling cutoffs",
    "punjab.pdf": "Punjab — state counselling cutoffs",
    "telangana.pdf": "Telangana — state counselling cutoffs",
    "tg_meritlist.pdf": "Telangana — state merit list",
    "westbengal.pdf": "West Bengal — state counselling cutoffs",
    "chandigarh-gmch32-2025-admitted-list.pdf": "Chandigarh — GMCH-32 admitted-student list",
    "mizoram-2025-neet-seat-matrix.pdf": "Mizoram — NEET seat matrix",
    "mizoram-2026-provisional-merit-list.pdf": "Mizoram — provisional merit list (2026 cycle)",
    "ladakh-2025-central-pool-selected-list.pdf": "Ladakh — central-pool selected list",
    "arunachal-2025-r1-allotment.pdf": "Arunachal Pradesh — Round-1 allotment",
    "manipur-2025-r2-state-quota-allotment.pdf": "Manipur — Round-2 state-quota allotment",
    "meghalaya-2025-mbbs-selected-list.pdf": "Meghalaya — MBBS selected list",
    "nagaland-2025-final-selected-list.pdf": "Nagaland — final selected list",
    "tripura-2025-r1-allotment.pdf": "Tripura — Round-1 allotment",
    "haryana-neet-ug-2025-round1-allotment.pdf": "Haryana — Round-1 allotment",
    "rajasthan-neet-merit-list.pdf": "Rajasthan — state merit list",
    "191568Odisha R3 MBBS Cutoff 2025.pdf": "Odisha — Round-3 MBBS cutoffs",
    "599136R1 Allotment 2025.pdf": "Odisha — Round-1 allotment",
    "2025072943.pdf": "Uttarakhand — state counselling document",
    "JH_R1_2025.pdf": "Jharkhand — Round-1 allotment",
    "JH_R3_2025.pdf": "Jharkhand — Round-3 allotment",
    "nmc-dci-roster-2025-26/mbbs_all_colleges_2025-26.csv": "NMC roster — all MBBS colleges with management type (2025-26)",
    "nmc-dci-roster-2025-26/bds_all_colleges_2025-26.csv": "DCI roster — all BDS colleges with management type (2025-26)",
}
ZIP_BUNDLES = {  # prefix -> (zip name, title)
    "mizoram-zmch-2025-admitted/": (
        "mizoram-zmch-2025-admitted-register.zip",
        "Mizoram — ZMCH admitted-student register (10 page images, zipped)"),
}
EXCLUDE_RAW = {"NTA NEET 2025.xlsx"}

EXTRACTED_TITLES = {
    "neet_aiq_2025_cutoffs.csv": "All India Quota — closing ranks by college & category",
    "neet_andhra_2025_r3_cutoffs.csv": "Andhra Pradesh — closing ranks by college & category (Round 3)",
    "neet_gujarat_2025_cutoffs.csv": "Gujarat — closing ranks by college & category",
    "neet_himachal_2025_r3_cutoffs.csv": "Himachal Pradesh — closing ranks by college & category (Round 3)",
    "neet_karnataka_2025_r3_cutoffs.csv": "Karnataka — closing ranks by college & category (Round 3)",
    "neet_kerala_2025_cutoffs.csv": "Kerala — closing ranks by college & category",
    "neet_maharashtra_2025_r3_cutoffs.csv": "Maharashtra — closing ranks by college & category (Round 3)",
    "neet_mp_2025_cutoffs.csv": "Madhya Pradesh — closing ranks by college & category",
    "neet_punjab_2025_cutoffs.csv": "Punjab — closing ranks by college & category",
    "neet_telangana_2025_cutoffs.csv": "Telangana — closing ranks by college & category",
    "neet_westbengal_2025_cutoffs.csv": "West Bengal — closing ranks by college & category",
    "AP_closing_ranks_state_govt_2025.csv": "Andhra Pradesh — government-college closing ranks",
    "AS_all_allotments_2025.csv": "Assam — full allotment list",
    "BR_closing_ranks_state_govt_2025.csv": "Bihar — government-college closing ranks (Round 3)",
    "CG_all_allotments_2025.csv": "Chhattisgarh — full allotment list",
    "HP_closing_ranks_state_govt_2025.csv": "Himachal Pradesh — government-college closing ranks (Round 3)",
    "JK_closing_ranks_state_govt_2025.csv": "Jammu & Kashmir — government-college closing ranks",
    "JK_meritlist_state_rank_air.csv": "Jammu & Kashmir — state-rank to All-India-Rank bridge",
    "KA_closing_ranks_state_govt_2025.csv": "Karnataka — government-college closing ranks",
    "KA_college_govt_classification.csv": "Karnataka — government / private college classification",
    "TG_closing_ranks_state_govt_2025.csv": "Telangana — government-college closing ranks",
    "TN_closing_ranks_state_govt_2025.csv": "Tamil Nadu — government-college closing ranks & marks",
    "UK_closing_ranks_state_govt_2025.csv": "Uttarakhand — government-college closing ranks (Round 3)",
    "UP_closing_ranks_state_govt_2025.csv": "Uttar Pradesh — government-college closing ranks",
    "national_closing_ranks_unified_AIR_2025.csv": "All states — unified closing ranks on the All-India-Rank scale",
    "govt_medical_closing_ranks_r1_2025.csv": "All India Quota — government-college closing ranks (Round 1)",
    "govt_medical_closing_ranks_r1_2025_pivot.csv": "All India Quota — government-college closing ranks, pivoted (Round 1)",
    "haryana-hr_closing_2025.csv": "Haryana — closing ranks & marks by college (Round 1)",
    "haryana-hr_allotments_2025.csv": "Haryana — allotment list (Round 1)",
    "odisha-od_closing_2025.csv": "Odisha — closing ranks by college (Round 3)",
    "odisha-od_allotments_2025.csv": "Odisha — allotment list (Round 3)",
    "odisha-od_rank_air_bridge_2025.csv": "Odisha — state-rank to All-India-Rank bridge (5,817 pairs)",
    "rajasthan-rj_closing_2025.csv": "Rajasthan — closing ranks by college (Round 1)",
    "rajasthan-rj_allotments_2025.csv": "Rajasthan — allotment list (Round 1)",
    "rajasthan-rj_meritlist_2025.csv": "Rajasthan — state merit list (marks & ranks)",
    "AR_2025_allotments.csv": "Arunachal Pradesh — Round-1 allotments (transcribed)",
    "ML_2025_selected_list.csv": "Meghalaya — selected list (transcribed)",
    "MN_allotments_ocr.csv": "Manipur — Round-2 allotments (transcribed)",
    "NL_2025_selected_list.csv": "Nagaland — selected list (partially recovered scan)",
    "mizoram-zmch_2025_admitted.csv": "Mizoram — ZMCH admitted-student register (transcribed)",
    "tripura-tripura_2025_r1_allotments.csv": "Tripura — Round-1 allotments (transcribed)",
}
EXCLUDE_EXTRACTED = {"neet_2026_matrix_all.csv"}    # a derived projection, not shared


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
    manifest = {
        "generated": str(date.today()),
        "license": "CC BY 4.0 (our compilations); raw documents are mirrored government publications",
        "datasets": [{
            "id": "neet",
            "title": "NEET-UG 2025 admissions",
            "blurb": "Medical/dental counselling cutoffs: the official documents and the tables we extracted from them, across the All India Quota and 26 state quotas.",
            "files": files,
        }],
    }
    dst.blob("manifest.json").upload_from_string(
        json.dumps(manifest, indent=1), content_type="application/json")
    print(f"\n{len(files)} files -> https://storage.googleapis.com/{DST_BUCKET}/manifest.json")


if __name__ == "__main__":
    main()
