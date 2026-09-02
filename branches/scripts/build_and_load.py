"""
Branch taxonomy + exam-branch mapping -> BigQuery.

SOURCE: the "branch" Google Sheet Amogh curates
(1PAMMolYuj5ThYVoRiJeMv_ByqwTk-cf_NDFN8kiIrL0). Two tabs — address them
by TITLE, the gids rotate when he edits:

  Branch           the taxonomy: parent rows (primary_branch_id empty) and
                   alias rows (raw spellings seen in sources, pointing at a
                   parent). 635 rows, ~100 parents, ids unique (the
                   CIVILENG020 duplicate was fixed in-sheet 2026-09-02).
  branches_to_map  Amogh's mapping of the 564 cutoff-table strings the
                   taxonomy didn't cover (filled Sep 2026, all valid).

exam_branch_mapping is the JOIN PRODUCT: every distinct branch/programme
string in our 13 cutoff sources (JoSAA, KCET, MHT-CET, TG/AP-EAPCET,
GUJCET, TNEA, WBJEE, KEAM, OJEE, CLAT, NEET, college-fees), resolved to a
PARENT branch id — via the taxonomy's alias rows where they existed, via
Amogh's mapping otherwise. The per-exam evidence lives in
~/jan2023/branches_from_cutoff_tables.csv (regenerate with the snippet in
the README if sources change).

Sheets auth: google-sheets-api@avantifellows service account — key at
~/may2022/avanti_code/etl-data-flow/flows/sessionCreator/google_secret.json
(the account Avanti sheets are shared with). BQ/GCS: gcs-handler key.

Usage:  python3 scripts/build_and_load.py
"""
from __future__ import annotations

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
EVIDENCE = Path.home() / "jan2023/branches_from_cutoff_tables.csv"

BQ = "avantifellows.external_data_sources"
GCS = "avantifellows-external-data"


def fetch_sheet():
    scope = ["https://spreadsheets.google.com/feeds",
             "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(str(SHEETS_KEY), scope)
    sh = gspread.authorize(creds).open_by_key(SHEET_ID)

    def tab(title):
        vals = sh.worksheet(title).get_all_values()
        df = pd.DataFrame(vals[1:], columns=vals[0]).replace("", pd.NA)
        return df.dropna(how="all")

    return tab("Branch"), tab("branches_to_map")


def main() -> None:
    stamp = datetime.date.today().isoformat()
    branch, to_map = fetch_sheet()
    branch = branch[[c for c in branch.columns if c]]  # drop unnamed spill cols
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

    new_map = dict(to_map[["branch_clean", "maps_to_branch_id"]].dropna().values)
    ev = pd.read_csv(EVIDENCE)
    rows = []
    for _, r in ev.iterrows():
        if r.status == "already in branch sheet":
            pid, pnm = parent_of.get(str(r.existing_branch_id).strip(), (None, None))
            via = "taxonomy alias row"
        else:
            pid, pnm = parent_of.get(new_map.get(r.branch_clean), (None, None))
            via = "curated mapping (Sep 2026)"
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
    raw = ROOT / f"raw/branch_sheet_{stamp}.csv"
    branch.to_csv(raw, index=False)

    creds = service_account.Credentials.from_service_account_file(GCP_KEY)
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
