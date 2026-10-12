"""
Branch taxonomy + exam-branch mapping -> BigQuery.

SOURCE: the curated "branch" Google Sheet
(1PAMMolYuj5ThYVoRiJeMv_ByqwTk-cf_NDFN8kiIrL0). Two tabs — address them
by TITLE, the gids rotate when he edits:

  Branch           the taxonomy: parent rows (primary_branch_id empty) and
                   alias rows (raw spellings seen in sources, pointing at a
                   parent). 629 rows, 108 parents (Oct 2026), ids unique (the
                   CIVILENG020 duplicate was fixed in-sheet 2026-09-02).
  branches_to_map  the curated mapping of the 564 cutoff-table strings the
                   taxonomy didn't cover (filled Sep 2026, all valid). The
                   tab has since left the sheet; its snapshot is committed
                   as evidence/branches_to_map_filled.csv and read from there.

exam_branch_mapping is the JOIN PRODUCT: every distinct branch/programme
string in our 13 cutoff sources (JoSAA, KCET, MHT-CET, TG/AP-EAPCET,
GUJCET, TNEA, WBJEE, KEAM, OJEE, CLAT, NEET, college-fees, JAC Chandigarh, AIIMS B.Sc. Nursing, ICAR-UG),
resolved to a
PARENT branch id — via the taxonomy's alias rows where they existed, via
the curated mapping otherwise. The per-exam evidence lives in
evidence/branches_from_cutoff_tables.csv (regenerate with the snippet in
the README if sources change).

Sheets auth: google-sheets-api@avantifellows service account — key at
~/may2022/avanti_code/etl-data-flow/flows/sessionCreator/google_secret.json
(the account Avanti sheets are shared with). BQ/GCS: gcs-handler key.

Usage:  python3 scripts/build_and_load.py [--sheet-csv PATH] [--dry-run]
  --sheet-csv  read the Branch tab from a CSV export instead of the Sheets
               API (no service-account key, and a login without the
               drive/spreadsheets scopes)
  --dry-run    build the parquet files and print the counts; upload nothing
"""
from __future__ import annotations

import argparse
import datetime
from pathlib import Path

import gspread
import pandas as pd
from google.cloud import bigquery, storage
from google.oauth2 import service_account
from oauth2client.service_account import ServiceAccountCredentials

ROOT = Path(__file__).resolve().parent.parent
SHEET_ID = "1PAMMolYuj5ThYVoRiJeMv_ByqwTk-cf_NDFN8kiIrL0"
SHEETS_KEY = Path.home() / "may2022/avanti_code/etl-data-flow/flows/sessionCreator/google_secret.json"
GCP_KEY = ROOT.parent / "avantifellows-61d1fc435ca2.json"
EVIDENCE = ROOT / "evidence/branches_from_cutoff_tables.csv"

# Branch-sheet ids that no longer exist, and where their rows now belong.
# The evidence files and the curated mapping still name them; resolving
# through this keeps every cutoff-table string mapped. Oct 2026: the sheet
# folded BIOSCI, CYBERSEC, EARTHSCI, ENGSCI, NATSCI, PRINTENG and SPACEENG
# into other parents, split ADMIN (MBA / OFFICEADMIN / PUBADMIN), renamed
# PHILOSOPHY to PHILO, gave each parent one name and dropped duplicate
# alias rows (their spellings live on under the ids below).
RETIRED_IDS = {
    "ADMIN": "MBA", "AIML011": "AIML", "AIML015": "STATISTICS",
    "AIML022": "AIML", "ARTS003": "ARTS", "AUTOENG005": "AUTOENG",
    "BIOMEDENG007": "BIOMEDENG", "BIOSCI": "BIO", "BIOSCI001": "BIO",
    "CHEMSCI002": "CHEM", "CHEMSCI003": "CHEM", "CHEMSCI005": "CHEM",
    "CIVILENG023": "CIVILENG", "CIVILENG025": "CIVILENG", "CSIT012": "CSIT",
    "CSIT062": "ELEC", "CSIT067": "CSIT", "CSIT068": "ELEC",
    "CYBERSEC": "CSIT", "EARTHSCI": "GEO", "EARTHSCI001": "GEO",
    "ELEC054": "ELEC", "ELEC058": "ELEC", "ELEC062": "ELEC",
    "ENGSCI": "GENENG", "ENGSCI001": "GENENG", "GEO009": "GEO",
    "INDENG003": "CSIT", "INDENG015": "CSIT", "INSTRENG005": "INSTRENG",
    "INSTRENG007": "INSTRENG", "MARINE002": "MARINE", "MARINE004": "MARINE",
    "MECHENG020": "MECHENG", "MECHENG024": "MECHENG", "NATSCI": "GENSCI",
    "NATSCI001": "GENSCI", "NATSCI002": "GENSCI", "OTHER005": "OTHER",
    "PHILOSOPHY": "PHILO", "PHYSICS006": "PHYSICS", "PHYSICS007": "PHYSICS",
    "PHYSIO003": "PARAMED", "PRINTENG": "PAPERENG", "PRINTENG001": "PAPERENG",
    "PRINTENG002": "PAPERENG", "ROBOENG008": "ROBOENG", "SPACEENG": "AERO",
    "SPACEENG001": "AERO",
}
# single strings whose retired parent split rather than moved whole
STRING_PARENT = {
    ("CLAT", "B.Sc. LL.B. (Hons.) Cyber Security"): "LLB",
    ("BHU-CUET", "Bachelor of Vocation in Modern Office Management"): "OFFICEADMIN",
    ("DU-CUET", "B.A. (Vocational Studies) Office Management and Secretarial Practice"): "OFFICEADMIN",
}

BQ = "avantifellows.external_data_sources"
GCS = "avantifellows-external-data"


def fetch_sheet(sheet_csv=None):
    if sheet_csv:
        df = pd.read_csv(sheet_csv, dtype=str, keep_default_na=False)
        df = df.replace("", pd.NA).dropna(how="all")
        return df, pd.read_csv(ROOT / "evidence/branches_to_map_filled.csv")
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    if SHEETS_KEY.exists():
        creds = ServiceAccountCredentials.from_json_keyfile_name(str(SHEETS_KEY), scope)
        client = gspread.authorize(creds)
    else:
        # no key file: the person's own Google login (gcloud auth
        # application-default login with the drive/spreadsheets scopes)
        import google.auth
        creds, _ = google.auth.default(scopes=scope)
        client = gspread.authorize(creds)
    sh = client.open_by_key(SHEET_ID)

    def tab(title):
        vals = sh.worksheet(title).get_all_values()
        df = pd.DataFrame(vals[1:], columns=vals[0]).replace("", pd.NA)
        return df.dropna(how="all")

    # the curated mapping was a one-off, finished job: read its committed
    # snapshot, not a tab that can move (it left the sheet in Sep 2026)
    return tab("Branch"), pd.read_csv(ROOT / "evidence/branches_to_map_filled.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-csv")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stamp = datetime.date.today().isoformat()
    branch, to_map = fetch_sheet(args.sheet_csv)
    branch = branch[[c for c in branch.columns if c]]  # drop unnamed spill cols
    # Known sheet slips, corrected here by exact match and printed; any other
    # duplicate id still fails below. Structural Engineering was re-id'd
    # CIVILENG020 -> CIVILENG025 on 2026-09-02 (CIVILENG020 is Transportation
    # Engineering); a later edit of the sheet brought the old id back.
    KNOWN_SHEET_FIXES = [("CIVILENG020", "Structural Engineering", "CIVILENG025")]
    for bid, name, fixed in KNOWN_SHEET_FIXES:
        hit = (branch.branch_id == bid) & (branch.branch_name == name)
        if hit.any() and not (branch.branch_id == fixed).any():
            branch.loc[hit, "branch_id"] = fixed
            print(f"  sheet fix: {name} {bid} -> {fixed}")
    assert branch.branch_id.is_unique, "duplicate branch_id in the sheet"

    dim = branch.assign(
        is_parent=branch.primary_branch_id.isna(),
        as_of=stamp,
    )
    parents = dim[dim.is_parent]
    print(f"branch_dim: {len(dim)} rows, {len(parents)} parents")

    # resolve any id (parent or alias) to its parent
    pname = dict(parents[["branch_id", "branch_name"]].values)
    parent_of = {}
    for _, r in dim.iterrows():
        pid = r.branch_id if r.is_parent else r.primary_branch_id
        parent_of[r.branch_id] = (pid, pname.get(pid))

    def resolve(bid):
        bid = str(bid).strip()
        if bid not in parent_of and bid in RETIRED_IDS:
            bid = RETIRED_IDS[bid]
        return parent_of.get(bid, (None, None))

    new_map = dict(to_map[["branch_clean", "maps_to_branch_id"]].dropna().values)
    ev = pd.read_csv(EVIDENCE)
    rows = []
    for _, r in ev.iterrows():
        if r.status == "already in branch sheet":
            pid, pnm = resolve(r.existing_branch_id)
            via = "taxonomy alias row"
        elif r.status in ("taxonomy parent by name", "nearest parent, needs review"):
            # ICAR-UG (Sep 2026): the course IS a taxonomy parent's name, or
            # no parent fits and the nearest one is used until the taxonomy
            # gets a branch for it
            pid, pnm = resolve(r.existing_branch_id)
            via = r.status
        elif r.status == "same string mapped for another exam":
            # a later source (JAC Chandigarh, AIIMS nursing; Sep 2026) whose cleaned strings
            # all match ones already mapped for other exams
            pid, pnm = resolve(r.existing_branch_id)
            via = "same string as another exam"
        else:
            pid, pnm = resolve(new_map.get(r.branch_clean))
            via = "curated mapping (Sep 2026)"
        if (r.exam, r.branch_raw) in STRING_PARENT:
            pid, pnm = resolve(STRING_PARENT[(r.exam, r.branch_raw)])
        rows.append(dict(exam=r.exam, branch_raw=r.branch_raw,
                         branch_clean=r.branch_clean, branch_id=pid,
                         branch_name=pnm, n_rows=int(r.n_rows),
                         n_colleges=int(r.n_colleges), mapped_via=via,
                         as_of=stamp))
    m = pd.DataFrame(rows)
    assert m.branch_id.notna().all(), "unmapped branch strings"
    print(f"exam_branch_mapping: {len(m)} rows, 100% mapped")

    dim_pq = ROOT / "clean/branch_dim.parquet"
    map_pq = ROOT / "clean/exam_branch_mapping.parquet"
    dim.to_parquet(dim_pq, index=False)
    m.to_parquet(map_pq, index=False)
    if args.dry_run:
        print(f"  dry run: wrote {dim_pq.name}, {map_pq.name}; nothing uploaded")
        return
    raw = ROOT / f"raw/branch_sheet_{stamp}.csv"
    branch.to_csv(raw, index=False)

    # the service-account key if it's here, else the person's own login
    creds = (service_account.Credentials.from_service_account_file(GCP_KEY)
             if GCP_KEY.exists() else None)
    bucket = storage.Client(credentials=creds, project="avantifellows").bucket(GCS)
    for p, dest in [(raw, f"branches/raw/{raw.name}"),
                    (dim_pq, "branches/clean/branch_dim.parquet"),
                    (map_pq, "branches/clean/exam_branch_mapping.parquet")]:
        bucket.blob(dest).upload_from_filename(str(p))
        print(f"  {p.name} -> gs://{GCS}/{dest}")

    bq = bigquery.Client(credentials=creds, project="avantifellows")
    cfg = bigquery.LoadJobConfig(
        write_disposition="WRITE_TRUNCATE",
        source_format=bigquery.SourceFormat.PARQUET,
    )
    for pq, table in [(dim_pq, f"{BQ}.branch_dim"),
                      (map_pq, f"{BQ}.exam_branch_mapping")]:
        with open(pq, "rb") as fh:
            bq.load_table_from_file(fh, table, job_config=cfg,
                                    location="asia-south1").result()
        print(f"  loaded {table}")


if __name__ == "__main__":
    main()
