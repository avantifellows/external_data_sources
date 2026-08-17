#!/usr/bin/env python3
"""
End-to-end reproduction of the NEET-2026 minimum-marks matrix: durable sources in,
370 rows out, diffed against the published sheet.

    python3 reproduce.py [--college-predictor PATH] [--keep]

WHAT IT PROVES. That the 370-row matrix in BigQuery is a *function of preserved inputs
plus committed code* — not of anyone's laptop. It materializes every input the builders
read, runs the pipeline (shift fit → AIQ + 27 state builders → merge), and diffs the
result against the published `neet_2026_matrix_all.csv`. PASS means byte-value equality
on all 370 rows.

WHERE INPUTS COME FROM, in resolution order per file:
  1. gs://avantifellows-external-data/neet/          (the canonical home)
  2. gs://avantifellows-external-data/neet_matrix/   (legacy prefix, pre-consolidation)
  3. a local college-predictor clone                 (flagged PENDING-UPLOAD: these are
     files whose GCS staging is blocked on the org's GCP billing being restored)
Two artifacts are pinned to the college-predictor repo rather than GCS, because they are
committed and versioned there: public/data/NEETUG/NEETUG.json and score_rank_model.json.
Without a local clone they are fetched from raw.githubusercontent.com.

WHAT IT DOES NOT RE-RUN, and why: the PDF/OCR parsers. Their outputs are preserved in
GCS extracted/, and OCR (tesseract) is not deterministic across machines — a pipeline
that claims reproducibility must not have a nondeterministic stage inside the claim.
Re-running the parsers for audit is `neet/matrix/parsers/` + `scrape/`, documented in
matrix/docs/. The reproducibility contract starts at the extracted layer.

Layout it materializes (all gitignored) around the builders, which resolve inputs
relative to their own location (REPO = matrix/):
  matrix/public/data/NEETUG/            the two pinned artifacts
  matrix/amogh-csv/...                  the handoff-family CSVs + the two PDFs builders parse
  matrix/builders/{haryana,odisha,rajasthan}_2025_out/   our parser outputs, from extracted/
  matrix/scripts/neet_matrix_out/       where the shift fit writes; mirrored into
  matrix/builders/neet_matrix_out/      where the builders read it (same dir in the old
                                        layout; the move split them)
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../neet
MATRIX = HERE / "matrix"
BUILDERS = MATRIX / "builders"

BUCKET = "avantifellows-external-data"
PREFIXES = ["neet", "neet_matrix"]              # canonical, then legacy
CP_RAW = "https://raw.githubusercontent.com/avantifellows/college-predictor/main"

# ── the input manifest: (dest relative to matrix/, source key) ────────────────
# source key: "gcs:<name-in-raw-or-extracted>" | "cp:<path-in-college-predictor>"
PINNED = [
    ("public/data/NEETUG/NEETUG.json", "public/data/NEETUG/NEETUG.json"),
    ("public/data/NEETUG/score_rank_model.json", "public/data/NEETUG/score_rank_model.json"),
]
# handoff-family CSVs (state_medical + mcc extracts) and the anchors workbook.
# GCS staging of these is PENDING (billing); until then the college-predictor
# clone is the fallback and reproduce says so out loud.
AMOGH = [
    "medical-state-counselling/extracted_data/AP_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/AS_all_allotments_2025.csv",
    "medical-state-counselling/extracted_data/BR_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/CG_all_allotments_2025.csv",
    "medical-state-counselling/extracted_data/HP_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/JK_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/JK_meritlist_state_rank_air.csv",
    "medical-state-counselling/extracted_data/KA_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/KA_college_govt_classification.csv",
    "medical-state-counselling/extracted_data/TG_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/TN_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/UK_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/UP_closing_ranks_state_govt_2025.csv",
    "medical-state-counselling/extracted_data/national_closing_ranks_unified_AIR_2025.csv",
    "medical-national-ranks/extracted_data/govt_medical_closing_ranks_r1_2025.csv",
    "medical-national-ranks/extracted_data/govt_medical_closing_ranks_r1_2025_pivot.csv",
    "NTA NEET 2025.xlsx",
]
# source documents builders parse directly. Chandigarh's is preserved in GCS raw/;
# Jharkhand's three JCECEB round PDFs ride the same PENDING-UPLOAD path as the CSVs.
AMOGH_FROM_RAW = [
    "chandigarh-gmch32-2025-admitted-list.pdf",
]
JH_SOURCE = ["JH_R1_2025.pdf", "JH_R3_2025.pdf"]
# our parser outputs, preserved in GCS extracted/ under '<state>-<file>' names,
# read by builders from '<state>_2025_out/<file>'
PARSER_OUT = [
    "haryana-hr_closing_2025.csv",
    "haryana-hr_allotments_2025.csv",
    "odisha-od_closing_2025.csv",
    "odisha-od_allotments_2025.csv",
    "odisha-od_rank_air_bridge_2025.csv",
    "rajasthan-rj_closing_2025.csv",
    "rajasthan-rj_allotments_2025.csv",
    "rajasthan-rj_meritlist_2025.csv",
]

# run order: models first, AIQ, then states, merge last
MODEL_SCRIPTS = ["neet_2026_shift_fit.py"]
MERGE = "neet_matrix_merge_all.py"


def gcs_client():
    from google.cloud import storage
    return storage.Client().bucket(BUCKET)


def fetch(bucket, tier: str, name: str, dest: Path) -> str | None:
    """Try each prefix for <prefix>/<tier>/<name>. Returns the URI used, or None.

    Degrades to the LOCAL mirror of the same tier (neet/raw, neet/extracted on disk)
    when GCS is unreachable — as of 2026-08-18 the org's GCP billing account is
    delinquent and even reads 403. Local hits are flagged so the run's verdict says
    which resolution paths still await verification against the bucket."""
    if bucket is not None:
        for pre in PREFIXES:
            try:
                blob = bucket.blob(f"{pre}/{tier}/{name}")
                ok = blob.exists()
            except Exception:
                ok = False
            if ok:
                dest.parent.mkdir(parents=True, exist_ok=True)
                blob.download_to_filename(dest)
                return f"gs://{BUCKET}/{pre}/{tier}/{name}"
    local = HERE / tier / name
    if local.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, dest)
        return f"LOCAL {local}  ** GCS-UNVERIFIED **"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--college-predictor", type=Path, default=None,
                    help="local clone (else pinned artifacts come from GitHub raw, and "
                         "PENDING-UPLOAD files cannot be resolved)")
    ap.add_argument("--keep", action="store_true", help="keep the materialized inputs")
    args = ap.parse_args()
    cp = args.college_predictor

    try:
        bucket = gcs_client()
        bucket.blob("neet/README-probe").exists()          # one probe; else offline mode
    except Exception as e:
        print(f"── GCS unreachable ({type(e).__name__}) — running from local mirrors")
        bucket = None
    pending = []

    print("── materializing inputs")
    for rel, cppath in PINNED:
        dest = MATRIX / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if cp and (cp / cppath).exists():
            shutil.copy2(cp / cppath, dest)
            src = f"college-predictor(local)/{cppath}"
        else:
            urllib.request.urlretrieve(f"{CP_RAW}/{cppath}", dest)
            src = f"github:college-predictor/{cppath}"
        print(f"   {rel}  <-  {src}")

    for rel in AMOGH:
        name = rel.split("/")[-1]
        dest = MATRIX / "amogh-csv" / rel
        used = fetch(bucket, "extracted", name, dest) or fetch(bucket, "raw", name, dest)
        if not used:
            local = (cp / "amogh-csv" / rel) if cp else None
            if local and local.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local, dest)
                used = f"LOCAL {local}  ** PENDING-UPLOAD **"
                pending.append(name)
            else:
                sys.exit(f"cannot resolve input: {rel}")
        print(f"   amogh-csv/{rel}  <-  {used}")

    for name in JH_SOURCE:
        rel = f"medical-state-counselling/source/JH/{name}"
        dest = MATRIX / "amogh-csv" / rel
        used = fetch(bucket, "raw", name, dest)
        if not used and cp and (cp / "amogh-csv" / rel).exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cp / "amogh-csv" / rel, dest)
            used = "LOCAL college-predictor  ** PENDING-UPLOAD **"
            pending.append(name)
        if not used:
            sys.exit(f"cannot resolve JH source: {name}")
        print(f"   amogh-csv/{rel}  <-  {used}")

    for name in AMOGH_FROM_RAW:
        dest = MATRIX / "amogh-csv" / name
        used = fetch(bucket, "raw", name, dest)
        if not used:
            sys.exit(f"cannot resolve raw document: {name}")
        print(f"   amogh-csv/{name}  <-  {used}")

    for gname in PARSER_OUT:
        state, fname = gname.split("-", 1)
        dest = BUILDERS / f"{state}_2025_out" / fname
        used = fetch(bucket, "extracted", gname, dest)
        if not used:
            sys.exit(f"cannot resolve parser output: {gname}")
        print(f"   builders/{state}_2025_out/{fname}  <-  {used}")

    # ── run the pipeline ──────────────────────────────────────────────────────
    (MATRIX / "scripts/neet_matrix_out").mkdir(parents=True, exist_ok=True)
    out_dir = BUILDERS / "neet_matrix_out"
    out_dir.mkdir(exist_ok=True)

    def run(script: str):
        r = subprocess.run([sys.executable, script], cwd=BUILDERS,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout[-1200:])
            print(r.stderr[-1200:])
            sys.exit(f"FAILED: {script}")
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""

    print("\n── shift fit")
    print("   " + run(MODEL_SCRIPTS[0]))
    # the fit writes to scripts/neet_matrix_out (the old layout's shared dir);
    # builders read from builders/neet_matrix_out — bridge the split.
    fitted = MATRIX / "scripts/neet_matrix_out/shift_2026.json"
    shutil.copy2(fitted, out_dir / "shift_2026.json")

    print("\n── builders")
    skip = {MERGE, "neet_2026_mapping.py", *MODEL_SCRIPTS}
    builders = sorted(p.name for p in BUILDERS.glob("neet_*.py") if p.name not in skip)
    # AIQ first: some states cite its floor
    builders.sort(key=lambda n: (n != "neet_matrix_build.py", n))
    for b in builders:
        print(f"   {b:34} {run(b)[:76]}")

    print("\n── merge")
    print("   " + run(MERGE))

    # ── the verdict ───────────────────────────────────────────────────────────
    print("\n── diff vs published")
    ref = HERE / "_published_reference.csv"
    used = fetch(bucket, "extracted", "neet_2026_matrix_all.csv", ref)
    got = list(csv.DictReader(open(out_dir / "neet_2026_matrix_all.csv")))
    want = list(csv.DictReader(open(ref)))
    ref.unlink()
    diffs = []
    key = lambda r: (r["state"], r["category"])
    wmap = {key(r): r for r in want}
    for g in got:
        w = wmap.get(key(g))
        if w is None:
            diffs.append((key(g), "row not in published"))
            continue
        for col in g:
            if g.get(col, "") != w.get(col, ""):
                diffs.append((key(g), f"{col}: built={g[col]!r} published={w[col]!r}"))
    for k in set(wmap) - {key(g) for g in got}:
        diffs.append((k, "row missing from build"))

    print(f"   built {len(got)} rows, published {len(want)} rows ({used})")
    if pending:
        print(f"   NOTE: {len(pending)} inputs came from a LOCAL clone, pending GCS upload:")
        for n in pending:
            print(f"     - {n}")
    if diffs:
        print(f"\n   ✗ {len(diffs)} differences:")
        for k, d in diffs[:30]:
            print(f"     {k}: {d}")
        sys.exit(1)
    print("\n   ✓ PASS — all 370 rows identical to the published matrix")

    if not args.keep:
        for d in [MATRIX / "public", MATRIX / "amogh-csv", MATRIX / "scripts/neet_matrix_out"]:
            shutil.rmtree(d, ignore_errors=True)
        for g in PARSER_OUT:
            shutil.rmtree(BUILDERS / f"{g.split('-',1)[0]}_2025_out", ignore_errors=True)


if __name__ == "__main__":
    main()
