"""
wage_curves data access — ONE place, decoupled from the sibling source repos.

This module is the single seam between the analysis and the data. NIRF is already
in BigQuery; PLFS / AISHE / NMC are not yet loaded, so today they're read from the
sibling repos' local parquets/CSVs (gitignored). The TARGET is to read everything
from the canonical BQ tables — each function documents its BQ target, and switching
is a localised change here (the analysis scripts never touch source internals).

  Source | today (local)                       | BQ target (when loaded)
  -------|-------------------------------------|------------------------------------------------
  NIRF   | BigQuery (live)                     | external_data_sources.nirf_fact_aggregate ✓
  AISHE  | ../aishe/clean/outturn.parquet      | external_data_sources.aishe_fact_outturn
  NMC    | ../nmc/clean/mbbs_seats.parquet     | external_data_sources.nmc_fact_mbbs_seats
  PLFS   | ../plfs/clean/<release>/perv1.csv   | external_data_sources.plfs_persons (weight_annual precomputed)

When PLFS lands in BQ, `plfs_persons()` becomes a query selecting weight_annual and
the inline `plfs_weight()` is dropped (BQ already calibrates the weight at load).
"""

import csv
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
PLFS_RELEASE = "annual_2022_23"


# ── BigQuery ─────────────────────────────────────────────────────────────────
def bq(sql: str) -> list[dict]:
    """Run a standard-SQL query via the bq CLI, return rows as dicts."""
    r = subprocess.run(["bq", "query", "--use_legacy_sql=false", "--format=csv"],
                       input=sql, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"bq failed:\n{r.stderr}")
    return list(csv.DictReader(io.StringIO(r.stdout)))


# ── AISHE (parquet today → aishe_fact_outturn) ───────────────────────────────
def _aishe_df():
    import pandas as pd
    return pd.read_parquet(REPO / "aishe" / "clean" / "outturn.parquet")


def aishe_ug(disciplines, year="2021-22") -> float:
    """All-India UG graduating class summed over the given AISHE disciplines."""
    df = _aishe_df()
    sl = df[(df.aishe_year == year) & (df.state == "All") & (df.social_category == "All")
            & (df.programme == "All") & (df.gender == "Total") & (df.level == "Under Graduate")
            & (df.discipline.isin(disciplines))]
    return float(sl.out_turn.sum())


def aishe_grand_ug(year="2021-22") -> float:
    """All-India UG graduating class, all real disciplines (excludes aggregate labels)."""
    df = _aishe_df()
    sl = df[(df.aishe_year == year) & (df.state == "All") & (df.social_category == "All")
            & (df.programme == "All") & (df.gender == "Total") & (df.level == "Under Graduate")
            & (~df.discipline.isin(["All", "All India", "Grand"]))]
    return float(sl.out_turn.sum())


# ── PLFS (clean CSV + inline weight today → plfs_persons w/ weight_annual) ────
def _safe_int(x, d=0):
    try:
        return int(x)
    except (TypeError, ValueError):
        try:
            return int(float(x))
        except (TypeError, ValueError):
            return d


def plfs_weight(row) -> float:
    """Calibrated annual weight, 'combined' rule (annual + CY2022/CY2024 releases):
    mult / no_qtr / (100 if nss==nsc else 200). Mirrors plfs/scripts/weights.py.
    NOTE: the BQ `plfs_persons` table carries `weight_annual` precomputed — when
    reading from BQ, use that column directly and ignore this function."""
    mult = _safe_int(row.get("mult"))
    nss, nsc = _safe_int(row.get("nss")), _safe_int(row.get("nsc"))
    no_qtr = _safe_int(row.get("no_qtr"), 1) or 1
    return mult / no_qtr / (100 if nss == nsc else 200)


def plfs_persons(release=PLFS_RELEASE):
    """Yield (row_dict, weight) for each PLFS person record.
    BQ target: SELECT … , weight_annual FROM plfs_persons WHERE release_id=@release.
    plfs_weight() implements the 'combined' rule (annual + CY2022/CY2024); CY2023
    (half_yearly) and CY2025 (simple) would need their own rule if used."""
    base = REPO / "plfs" / "clean" / release
    path = next((base / f for f in ("perv1.csv", "cperv1.csv") if (base / f).exists()), None)
    if path is None:
        sys.exit(f"PLFS clean CSV not found under {base} (parse the release or load to BQ).")
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield row, plfs_weight(row)


def nco_labels():
    """NCO 3-digit group code → description (PLFS codemap)."""
    p = REPO / "plfs" / "codemaps" / "nco_group.csv"
    return {r["code"]: r["description"] for r in csv.DictReader(p.open())}


# ── shared small utils ───────────────────────────────────────────────────────
def num(x):
    return float(x) if x not in (None, "", "NULL") else None


def wmedian(value_weights, p=50):
    """Weighted p-th percentile of [(value, weight), …]."""
    if not value_weights:
        return None
    s = sorted(value_weights)
    target = sum(w for _, w in s) * p / 100
    c = 0.0
    for v, w in s:
        c += w
        if c >= target:
            return v
    return s[-1][0]
