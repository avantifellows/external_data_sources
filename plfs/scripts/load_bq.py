"""
Load all PLFS clean data into BigQuery.

Reads from:
  - clean/{release_id}/*.csv         (parsed unit-level data; see parse_data.py)
  - codemaps/*.csv                   (code → label lookups; see build_codemaps.py)
  - scripts/releases.py              (release registry — single source of truth)

Writes 6 tables to the target dataset (default: `plfs`):
  - {ds}.persons       (~10.5M rows, fact)
  - {ds}.households    (~2.5M rows, fact)
  - {ds}.releases      (11 rows, registry)
  - {ds}.dim_nco       (~2.7k rows, full occupation hierarchy in one wide table)
  - {ds}.dim_nic       (~1.3k rows, full industry hierarchy in one wide table)
  - {ds}.dim_geo       (~700 rows, state + district)

Labels for small enums (sex, religion, sector, marital_status, education levels,
activity status, enterprise type, job contract, social security, …) are
denormalized as `*_label` columns directly on the fact tables. No per-enum
dim table.

Idempotent: each table is fully replaced on every run (WRITE_TRUNCATE for the
first release, WRITE_APPEND for subsequent — but the truncate makes the whole
load atomic per table).

Usage:
  python3 scripts/load_bq.py                              # full load to plfs
  python3 scripts/load_bq.py --project my-gcp-project     # override project
  python3 scripts/load_bq.py --dataset plfs_dev           # write to a dev dataset
  python3 scripts/load_bq.py --release calendar_2025      # one release only (facts)
  python3 scripts/load_bq.py --dims-only                  # just dim + registry
  python3 scripts/load_bq.py --dry-run                    # build parquet locally, no upload
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from releases import RELEASES, ROOT
from weights import get_weight_fn, weight_rule_of

CODEMAPS = ROOT / "codemaps"
CLEAN = ROOT / "clean"
DEFAULT_DATASET = "plfs"

# Household join key columns. Both qtr (annual / pre-CY2025) and month (CY2025)
# are included — exactly one is populated per row depending on release.
HH_KEY_COLS = ("qtr", "month", "visit", "sec", "st", "dc", "mfsu", "sss", "ssu")

# Activity codes the analyses agree mean "employed".  Kept here as a comment
# rather than a derived column — analyses still filter on raw pas/aps_cws.
# EMPLOYED_PAS = {'11','12','21','31','41','42','51'}


# ─── Codemap loaders ────────────────────────────────────────────────────────

def _read_codemap(name: str) -> dict[str, str]:
    """Read codemaps/{name}.csv into a {code: description} dict."""
    path = CODEMAPS / f"{name}.csv"
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["code"]] = row["description"]
    return out


def load_label_maps() -> dict[str, dict[str, str]]:
    """All small-enum codemaps, keyed by the codemap name."""
    return {
        name: _read_codemap(name)
        for name in (
            "sex",
            "sector",
            "religion",
            "social_group",
            "marital_status",
            "relation_to_head",
            "general_education",
            "technical_education",
            "vocational_training_received",
            "activity_status",
            "enterprise_type",
            "social_security",
            "job_contract",
            "no_of_workers",
            "household_type_rural",
            "household_type_urban",
        )
    }


# ─── Dim builders ────────────────────────────────────────────────────────────

def build_dim_nco() -> pd.DataFrame:
    """
    Wide NCO hierarchy:
        code_full (8-digit) → family (4) → group (3) → subdivision (2) → division (1)

    NCO 2015 codes are zero-padded text. Each level's code is a prefix of the
    one below it (with a '.' between family and the sub-family digits).
    Example: '2512.0100' → family '2512' → group '251' → subdivision '25' → division '2'.
    """
    full = pd.read_csv(CODEMAPS / "nco_full.csv", dtype=str).rename(
        columns={"code": "code_full", "description": "label_full"}
    )
    family = pd.read_csv(CODEMAPS / "nco_family.csv", dtype=str).rename(
        columns={"code": "code_family", "description": "label_family"}
    )
    group = pd.read_csv(CODEMAPS / "nco_group.csv", dtype=str).rename(
        columns={"code": "code_group", "description": "label_group"}
    )
    subdiv = pd.read_csv(CODEMAPS / "nco_subdivision.csv", dtype=str).rename(
        columns={"code": "code_subdivision", "description": "label_subdivision"}
    )
    division = pd.read_csv(CODEMAPS / "nco_division.csv", dtype=str).rename(
        columns={"code": "code_division", "description": "label_division"}
    )

    # Derive hierarchy prefixes from code_full.
    full["code_family"] = full["code_full"].str.replace(".", "", regex=False).str[:4]
    full["code_group"] = full["code_family"].str[:3]
    full["code_subdivision"] = full["code_family"].str[:2]
    full["code_division"] = full["code_family"].str[:1]

    df = (
        full.merge(family, on="code_family", how="left")
        .merge(group, on="code_group", how="left")
        .merge(subdiv, on="code_subdivision", how="left")
        .merge(division, on="code_division", how="left")
    )
    return df[
        [
            "code_full", "label_full",
            "code_family", "label_family",
            "code_group", "label_group",
            "code_subdivision", "label_subdivision",
            "code_division", "label_division",
            "nco_2004_code",
        ]
    ]


def build_dim_nic() -> pd.DataFrame:
    """
    Wide NIC 2008 hierarchy:
        code_subclass (5) → class (4) → group (3) → division (2)
    """
    subclass = pd.read_csv(CODEMAPS / "nic_subclass.csv", dtype=str).rename(
        columns={"code": "code_subclass", "description": "label_subclass"}
    )
    cls = pd.read_csv(CODEMAPS / "nic_class.csv", dtype=str).rename(
        columns={"code": "code_class", "description": "label_class"}
    )
    group = pd.read_csv(CODEMAPS / "nic_group.csv", dtype=str).rename(
        columns={"code": "code_group", "description": "label_group"}
    )
    division = pd.read_csv(CODEMAPS / "nic_division.csv", dtype=str).rename(
        columns={"code": "code_division", "description": "label_division"}
    )

    subclass["code_class"] = subclass["code_subclass"].str[:4]
    subclass["code_group"] = subclass["code_subclass"].str[:3]
    subclass["code_division"] = subclass["code_subclass"].str[:2]

    df = (
        subclass.merge(cls, on="code_class", how="left")
        .merge(group, on="code_group", how="left")
        .merge(division, on="code_division", how="left")
    )
    return df[
        [
            "code_subclass", "label_subclass",
            "code_class", "label_class",
            "code_group", "label_group",
            "code_division", "label_division",
        ]
    ]


def build_dim_geo() -> pd.DataFrame:
    """State + district in one table. district.csv already has state_code/name."""
    df = pd.read_csv(CODEMAPS / "district.csv", dtype=str)
    return df[["state_code", "state_name", "district_code", "district_name"]]


def build_releases_df() -> pd.DataFrame:
    """11-row registry derived directly from scripts/releases.py."""
    rows = []
    for rid, cfg in RELEASES.items():
        rows.append(
            {
                "release_id": rid,
                "label": cfg["label"],
                "format": cfg["format"],
                "year_label": cfg["year_label"],
                "period_start": cfg["period_start"],
                "period_end": cfg["period_end"],
                "catalog_id": cfg["catalog_id"],
                "catalog_url": cfg["catalog_url"],
                "weight_rule": cfg["weight_rule"],
                "n_files": len(cfg["files"]),
                "file_keys": "|".join(f["key"] for f in cfg["files"]),
            }
        )
    return pd.DataFrame(rows)


# ─── Fact builders ───────────────────────────────────────────────────────────

def _hh_id(row: pd.Series) -> str:
    """Stable 16-char household id derived from the survey design key.

    Includes release_id so ids are globally unique across releases (the natural
    key only identifies a household within one release).
    """
    parts = [str(row.get("release_id", ""))]
    parts.extend(str(row.get(c, "") or "") for c in HH_KEY_COLS)
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _add_hh_id(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized hh_id derivation — much faster than .apply on 1M+ rows."""
    keys = df["release_id"].astype(str)
    for c in HH_KEY_COLS:
        col = df[c].fillna("").astype(str) if c in df.columns else ""
        keys = keys + "|" + col
    df["hh_id"] = keys.map(lambda s: hashlib.sha1(s.encode("utf-8")).hexdigest()[:16])
    return df


def _safe_int(x) -> int:
    if pd.isna(x) or x == "":
        return 0
    try:
        return int(x)
    except (ValueError, TypeError):
        try:
            return int(float(x))
        except (ValueError, TypeError):
            return 0


def _compute_weight_annual(df: pd.DataFrame, release_id: str) -> pd.Series:
    """Apply the release's calibrated weight rule row-by-row."""
    if weight_rule_of(release_id) == "limited":
        # CY2021 has no usable weight column.  Persons still get loaded for
        # demographic queries; weight_annual is left NULL.
        return pd.Series([None] * len(df), dtype="float64")
    fn = get_weight_fn(release_id)
    return df.apply(lambda r: fn(r.to_dict()), axis=1).astype("float64")


def _read_release_csv(path: Path) -> pd.DataFrame:
    """Read a clean CSV with all-string dtypes (preserves zero-padded codes)."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def build_persons_for_release(release_id: str, labels: dict[str, dict[str, str]]) -> pd.DataFrame | None:
    """Build the persons rows for one release.  Returns None if data is missing."""
    cfg = RELEASES[release_id]
    out_dir = cfg["out_dir"]

    # Annual releases have perv1 + perrv; calendar releases have cperv1.
    candidates = [out_dir / "perv1.csv", out_dir / "perrv.csv", out_dir / "cperv1.csv"]
    paths = [p for p in candidates if p.exists()]
    if not paths:
        return None

    frames = []
    for p in paths:
        df = _read_release_csv(p)
        df["src_file"] = p.stem  # 'perv1' / 'perrv' / 'cperv1'
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    # ── Release-level metadata ──────────────────────────────────────────────
    df["release_id"] = release_id
    df["release_format"] = cfg["format"]
    df["release_year"] = cfg["year_label"]
    df["catalog_id"] = cfg["catalog_id"]

    # ── Derived join key ────────────────────────────────────────────────────
    df = _add_hh_id(df)

    # ── Derived industry division (2-digit prefix of NIC) ──────────────────
    if "ind_pas" in df.columns:
        df["ind_pas_div"] = df["ind_pas"].fillna("").astype(str).str[:2].replace("", None)

    # ── Inline labels for small enums ───────────────────────────────────────
    label_map = [
        ("sec", "sector", "sec_label"),
        ("sex", "sex", "sex_label"),
        ("marst", "marital_status", "marst_label"),
        ("rel", "relation_to_head", "rel_label"),
        ("gedu_lvl", "general_education", "gedu_label"),
        ("tedu_lvl", "technical_education", "tedu_label"),
        ("voc", "vocational_training_received", "voc_label"),
        ("pas", "activity_status", "pas_label"),
        ("etyp_pas", "enterprise_type", "etyp_pas_label"),
        ("ssec_pas", "social_security", "ssec_pas_label"),
        ("job_pas", "job_contract", "job_pas_label"),
        ("wrkr_pas", "no_of_workers", "wrkr_pas_label"),
    ]
    for src, mapname, dst in label_map:
        if src in df.columns:
            df[dst] = df[src].map(labels[mapname])

    # State name inline (joined from district codemap → state lookup)
    if "st" in df.columns:
        state_lookup = (
            pd.read_csv(CODEMAPS / "state.csv", dtype=str)
            .set_index("state_code")["state_name"]
            .to_dict()
        )
        df["state_name"] = df["st"].map(state_lookup)

    # ── Coerce numeric columns ──────────────────────────────────────────────
    for col in ("age", "ern_reg", "ern_self", "nss", "nsc", "mult", "no_qtr"):
        if col in df.columns:
            df[col] = df[col].map(_safe_int).astype("Int64")

    # ── Calibrated weight ───────────────────────────────────────────────────
    df["weight_annual"] = _compute_weight_annual(df, release_id)

    return df


def build_households_for_release(release_id: str, labels: dict[str, dict[str, str]]) -> pd.DataFrame | None:
    cfg = RELEASES[release_id]
    out_dir = cfg["out_dir"]

    candidates = [out_dir / "hhv1.csv", out_dir / "hhrv.csv", out_dir / "chhv1.csv"]
    paths = [p for p in candidates if p.exists()]
    if not paths:
        return None

    frames = []
    for p in paths:
        df = _read_release_csv(p)
        df["src_file"] = p.stem
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)

    df["release_id"] = release_id
    df["release_format"] = cfg["format"]
    df["release_year"] = cfg["year_label"]
    df["catalog_id"] = cfg["catalog_id"]

    df = _add_hh_id(df)

    # Labels
    inline = [
        ("sec", "sector", "sec_label"),
        ("religion", "religion", "religion_label"),
        ("social_grp", "social_group", "social_grp_label"),
    ]
    for src, mapname, dst in inline:
        if src in df.columns:
            df[dst] = df[src].map(labels[mapname])

    # hh_type label is rural OR urban depending on sec
    if "hh_type" in df.columns and "sec" in df.columns:
        rural = labels["household_type_rural"]
        urban = labels["household_type_urban"]
        df["hh_type_label"] = [
            (rural if sec == "1" else urban if sec == "2" else {}).get(code)
            for sec, code in zip(df["sec"], df["hh_type"])
        ]

    if "st" in df.columns:
        state_lookup = (
            pd.read_csv(CODEMAPS / "state.csv", dtype=str)
            .set_index("state_code")["state_name"]
            .to_dict()
        )
        df["state_name"] = df["st"].map(state_lookup)

    # Numerics
    for col in ("hh_size", "hce_tot", "hce1", "hce2", "hce3", "hce4", "hce5",
                "nss", "nsc", "mult", "no_qtr"):
        if col in df.columns:
            df[col] = df[col].map(_safe_int).astype("Int64")

    # MPCE — monthly per capita consumer expenditure (the income proxy).
    if "hce_tot" in df.columns and "hh_size" in df.columns:
        df["mpce"] = (
            df["hce_tot"].astype("Float64") / df["hh_size"].astype("Float64").replace(0, pd.NA)
        )

    df["weight_annual"] = _compute_weight_annual(df, release_id)
    return df


# ─── BQ upload ──────────────────────────────────────────────────────────────

def _upload(df: pd.DataFrame, table_id: str, *, append: bool, project: str | None,
            dry_run_dir: Path | None) -> None:
    """Load `df` into `table_id` (full id: project.dataset.table)."""
    if dry_run_dir is not None:
        out = dry_run_dir / f"{table_id.split('.')[-1]}.parquet"
        # In dry-run mode we accumulate per-release dataframes by appending.
        if append and out.exists():
            existing = pd.read_parquet(out)
            df = pd.concat([existing, df], ignore_index=True)
        df.to_parquet(out, index=False)
        print(f"  [dry-run] wrote {len(df):>10,} rows → {out}")
        return

    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    job_config = bigquery.LoadJobConfig(
        write_disposition=(
            bigquery.WriteDisposition.WRITE_APPEND
            if append
            else bigquery.WriteDisposition.WRITE_TRUNCATE
        ),
        autodetect=True,
    )
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()
    print(f"  uploaded {len(df):>10,} rows → {table_id}")


# ─── Main ───────────────────────────────────────────────────────────────────

def _iter_releases(only: str | None) -> Iterable[str]:
    if only:
        if only not in RELEASES:
            raise SystemExit(f"Unknown release {only!r}. Known: {sorted(RELEASES)}")
        return [only]
    return list(RELEASES)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=None, help="GCP project id (default: gcloud config)")
    ap.add_argument("--dataset", default=DEFAULT_DATASET, help=f"BQ dataset (default: {DEFAULT_DATASET})")
    ap.add_argument("--release", default=None, help="Load one release only (facts)")
    ap.add_argument("--dims-only", action="store_true", help="Skip facts; load dims + releases only")
    ap.add_argument("--facts-only", action="store_true", help="Skip dims; load facts only")
    ap.add_argument("--dry-run", action="store_true", help="Write parquet to /tmp/plfs_bq instead of uploading")
    args = ap.parse_args()

    ds = args.dataset
    dry_dir = None
    if args.dry_run:
        dry_dir = Path("/tmp/plfs_bq")
        dry_dir.mkdir(parents=True, exist_ok=True)
        print(f"DRY RUN — writing parquet to {dry_dir}")

    def tbl(name: str) -> str:
        return f"{ds}.{name}"

    labels = load_label_maps()

    # ── Dims + registry ─────────────────────────────────────────────────────
    if not args.facts_only:
        print("\n=== Dimension tables ===")
        for name, df in [
            ("releases", build_releases_df()),
            ("dim_nco", build_dim_nco()),
            ("dim_nic", build_dim_nic()),
            ("dim_geo", build_dim_geo()),
        ]:
            print(f"{name}:")
            _upload(df, tbl(name), append=False, project=args.project, dry_run_dir=dry_dir)

    if args.dims_only:
        return

    # ── Fact tables — release by release, streaming to BQ ───────────────────
    print("\n=== Fact tables ===")
    release_ids = list(_iter_releases(args.release))
    for i, release_id in enumerate(release_ids):
        print(f"\n[{i+1}/{len(release_ids)}] {release_id}")
        first = (i == 0) and not args.release  # don't truncate when loading a single release

        p = build_persons_for_release(release_id, labels)
        if p is None:
            print(f"  ⚠ no persons CSV found for {release_id}, skipping")
        else:
            print(f"  persons:")
            _upload(p, tbl("persons"), append=not first, project=args.project, dry_run_dir=dry_dir)

        h = build_households_for_release(release_id, labels)
        if h is None:
            print(f"  ⚠ no households CSV found for {release_id}, skipping")
        else:
            print(f"  households:")
            _upload(h, tbl("households"), append=not first, project=args.project, dry_run_dir=dry_dir)

    print("\n✓ done.")


if __name__ == "__main__":
    main()
