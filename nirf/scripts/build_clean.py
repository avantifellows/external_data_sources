"""
Build clean NIRF parquets from the raw parquets in nirf/raw/.

This is the auditable raw → clean recipe. The parquets it produces are the
exact files that upload_to_gcs.py stages and load_bq.py loads — nothing is
transformed downstream.

What it does, and why:

  1. Deduplicates `nirf_fact_master` and `nirf_fact_strength`.
     The upstream (Dataful) repeats rows 2-3× for some institutes. Verified
     against NIRF's own scorecards — e.g. Kalasalingam IR-E-U-0458 (2025) has
     ONE "1476 graduating / 1359 placed / Rs 6.10L" row in the official PDF and
     two byte-identical rows upstream. So the duplication is an ingestion
     artifact and collapsing it restores the filed values.

  2. Rebuilds `nirf_fact_aggregate` from the deduplicated master.
     The old build pivoted master with aggfunc='sum', so duplicated rows were
     ADDED — doubling counts and, nonsensically, median salary. This pivots the
     deduplicated master with 'max' and asserts the grain is unique first, so a
     future duplicate load fails loudly instead of silently inflating measures.

Duplicate policy, per table:

  * Byte-identical rows                → collapsed everywhere. Not in the source.
  * Same grain, same value, differing
    on a descriptive column (`city`)   → collapsed, first kept.
  * Same grain, CONFLICTING value:
      - nirf_fact_strength  → SUMMED, and every collapsed key is logged.
        NIRF's `programme` is a duration bucket, not a programme name, so an
        institute with two different 2-year PG programmes legitimately files two
        rows under "PG [2 Year Program(s)]". Punjabi University's 2020 scorecard
        does exactly that. Every strength category is an additive count
        (198,660/198,660 rows are "value in Absolute Number"), so summing gives
        the bucket total and loses nobody.
      - nirf_fact_master    → REFUSED (hard error). Master carries
        "value in Rupees" rows, and a summed median is meaningless. There are no
        such conflicts today; if one appears it needs a human decision.

Usage:
  python3 scripts/build_clean.py                             # build all four
  python3 scripts/build_clean.py --table nirf_fact_master    # one only
  python3 scripts/build_clean.py --dry-run                   # build in-mem, write nothing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import (AGGREGATE_JOIN_KEYS, AGGREGATE_PIVOT_INDEX, AGGREGATE_RENAMES,
                     CLEAN, FIRST_PARTY_CATEGORIES, RANKINGS_OFFICIAL_CSV, RAW,
                     TABLES, Table)

# Tables whose conflicting-value rows may be summed (pure-count measures only).
SUMMABLE = {"nirf_fact_strength"}

GRADUATING = "Number of students graduating in min stipulated time"
PLACED     = "Number of students placed"
ADMITTED   = "Number of first year students admitted"
INTAKE     = "Number of first year students intake"


# ─── Deduplication ───────────────────────────────────────────────────────────

def _dedupe(df: pd.DataFrame, table: Table) -> pd.DataFrame:
    """Collapse upstream duplicate rows down to the table's documented grain."""
    grain = list(table.grain)
    start = len(df)

    # 1. byte-identical rows — pure ingestion artifact
    df = df.drop_duplicates()
    exact = start - len(df)

    if "value" not in df.columns:
        # rankings: no measure column, so grain uniqueness is the whole story
        df = df.drop_duplicates(grain)
        print(f"    deduped {start - len(df):,} rows ({exact:,} byte-identical) → {len(df):,}")
        return df

    # 2. same grain AND same value, differing only on a descriptive column
    #    (upstream carries two spellings of `city` for some institutes)
    df = df.drop_duplicates(grain + ["value"])
    descriptive = start - exact - len(df)

    # 3. whatever still repeats on the grain has a genuinely conflicting value
    conflicts = df[df.duplicated(grain, keep=False)]
    if len(conflicts):
        if table.bq_name not in SUMMABLE:
            raise SystemExit(
                f"{table.bq_name}: {len(conflicts):,} rows share a grain key but disagree on "
                f"`value`, and this table is not summable (it mixes units — a summed median "
                f"is meaningless). Resolve by hand.\n\n{conflicts.sort_values(grain).to_string()}"
            )
        keys = conflicts[grain].drop_duplicates()
        print(f"    ⚠ {len(conflicts):,} rows across {len(keys):,} grain keys have CONFLICTING "
              f"values and were SUMMED (see module docstring):")
        for _, k in keys.iterrows():
            vals = conflicts.merge(k.to_frame().T, on=grain)["value"].tolist()
            loc = " / ".join(str(k[c]) for c in grain)
            print(f"        {loc}  ->  {' + '.join(f'{v:g}' for v in vals)} = {sum(vals):g}")

        others = [c for c in df.columns if c not in grain and c != "value"]
        df = (df.groupby(grain, as_index=False, dropna=False)
                .agg({"value": "sum", **{c: "first" for c in others}}))[list(conflicts.columns)]

    print(f"    deduped {start - len(df):,} rows "
          f"({exact:,} byte-identical, {descriptive:,} descriptive-only) → {len(df):,}")
    return df


# ─── First-party rankings splice ─────────────────────────────────────────────

def _splice_official_rankings(dataful: pd.DataFrame) -> pd.DataFrame:
    """Replace the Dataful rows for FIRST_PARTY_CATEGORIES with rows parsed
    from nirfindia.org's own ranking pages (parse_dcs.py), and keep Dataful
    for every other category. Adds three columns to the table:

      rank_raw      — the rank as NIRF prints it. 2018 has '21A'/'26A'
                      (institutes inserted after data corrections); Dataful
                      silently renumbered everything below them.
      rank_band     — '101-150' etc. for rank-band institutes. NIRF publishes
                      NO id, score or rank for these, so institute_id and
                      overall_score are NULL on band rows — the grain there
                      is (year, category, institute_name, city).
      record_source — 'nirfindia.org' or 'dataful', per row.
    """
    if not RANKINGS_OFFICIAL_CSV.exists():
        raise SystemExit(
            f"missing {RANKINGS_OFFICIAL_CSV}\n"
            f"Build it first:  python3 scripts/fetch_dcs.py --pages-only && "
            f"python3 scripts/parse_dcs.py pages"
        )
    of = pd.read_csv(RANKINGS_OFFICIAL_CSV)
    official = pd.DataFrame({
        "ranking_year": of["ranking_year"],
        "ranking_category": of["discipline"],
        "institute_id": of["institute_id"],
        "institute_name": of["institute_name"],
        "state": of["state"],
        "city": of["city"],
        "overall_score": of["score"],
        "nirf_rank": of["rank"].astype(str).str.extract(r"(\d+)")[0].astype("Int64"),
        "rank_raw": of["rank"],
        "rank_band": of["rank_band"],
        "record_source": "nirfindia.org",
    })
    ranked = official[official.nirf_rank.notna()]
    assert not ranked.duplicated(
        ["ranking_year", "ranking_category", "institute_id"]).any(), \
        "official ranked rows repeat on (year, category, institute_id)"

    kept = dataful[~dataful.ranking_category.isin(FIRST_PARTY_CATEGORIES)].copy()
    kept["rank_raw"] = None
    kept["rank_band"] = None
    kept["record_source"] = "dataful"
    replaced = len(dataful) - len(kept)
    print(f"    spliced first-party rankings: {len(official):,} official rows "
          f"({official.rank_band.notna().sum():,} band) replace {replaced:,} "
          f"Dataful rows for {list(FIRST_PARTY_CATEGORIES)}")
    return pd.concat([official, kept[official.columns]], ignore_index=True)


# ─── First-party DCS tables ──────────────────────────────────────────────────

def _build_dcs(table: Table) -> pd.DataFrame:
    """extracted/ CSV → clean frame: byte-dedupe, enforce the grain, and mark
    superseded rows (every edition restates the 3 trailing academic years;
    the newest edition reporting a key wins, older restatements get
    superseded=True so a naive time-series query has one row per key)."""
    if not table.extracted_path.exists():
        raise SystemExit(
            f"missing {table.extracted_path}\n"
            f"Build it first:  python3 scripts/fetch_dcs.py && "
            f"python3 scripts/parse_dcs.py"
        )
    df = pd.read_csv(table.extracted_path)
    start = len(df)
    df = df.drop_duplicates()
    grain = list(table.grain)
    conflicts = df[df.duplicated(grain, keep=False)]
    if len(conflicts):
        raise SystemExit(
            f"{table.bq_name}: {len(conflicts):,} rows share a grain key with "
            f"different values — the PDF parse mis-assigned a table. Inspect:\n"
            f"{conflicts.sort_values(grain).head(20).to_string()}"
        )
    if table.supersede_on:
        key = list(table.supersede_on)
        latest = df.groupby(key, dropna=False)["edition_year"].transform("max")
        df["superseded"] = df["edition_year"] < latest
        print(f"    {len(df):,} rows ({int((~df.superseded).sum()):,} current, "
              f"{int(df.superseded.sum()):,} superseded restatements)")
    if start - len(df):
        print(f"    dropped {start - len(df):,} byte-identical rows")
    return df


# ─── Derived table: nirf_fact_aggregate ──────────────────────────────────────

def _build_aggregate(master: pd.DataFrame, rankings: pd.DataFrame) -> pd.DataFrame:
    """Pivot the deduplicated master long→wide and attach it to rankings.

    Guarded by an assertion: if the master grain is not unique, pivoting would
    silently aggregate several rows into one measure. That is exactly how the
    doubled counts and doubled median salary happened, so it must fail rather
    than produce a number.
    """
    dupes = master.duplicated(AGGREGATE_PIVOT_INDEX + ["category"]).sum()
    if dupes:
        raise SystemExit(
            f"nirf_fact_aggregate: master still has {dupes:,} duplicate grain rows after "
            f"deduplication — refusing to pivot. Aggregating here is what doubled every "
            f"measure, median salary included."
        )

    pivot = master.pivot_table(
        index=AGGREGATE_PIVOT_INDEX, columns="category", values="value", aggfunc="max"
    ).reset_index()
    pivot.columns.name = None

    if PLACED in pivot.columns and GRADUATING in pivot.columns:
        pivot["Percentage Placed (%)"] = (pivot[PLACED] / pivot[GRADUATING] * 100).round(2)
    if ADMITTED in pivot.columns and INTAKE in pivot.columns:
        pivot["Admission Rate (%)"] = (pivot[ADMITTED] / pivot[INTAKE] * 100).round(2)

    ranked = rankings[rankings["nirf_rank"].notna()]
    agg = ranked.merge(pivot, on=AGGREGATE_JOIN_KEYS, how="left")
    return agg.rename(columns=AGGREGATE_RENAMES)


# ─── Build ───────────────────────────────────────────────────────────────────

def build(table: Table, cache: dict[str, pd.DataFrame]) -> pd.DataFrame:
    if table.extracted_csv:
        return _build_dcs(table)
    if table.derived:
        # aggregate needs the CLEAN master + rankings, so build those first
        for dep in ("nirf_fact_master", "nirf_fact_rankings"):
            if dep not in cache:
                dt = next(t for t in TABLES if t.bq_name == dep)
                print(f"  {dep} (dependency of {table.bq_name})")
                cache[dep] = build(dt, cache)
        return _build_aggregate(cache["nirf_fact_master"], cache["nirf_fact_rankings"])

    if not table.raw_path.exists():
        raise SystemExit(
            f"missing raw parquet: {table.raw_path}\n"
            f"Fetch it with:  gcloud storage cp {table.raw_gcs_uri} {RAW}/"
        )
    df = pd.read_parquet(table.raw_path)
    print(f"    read {len(df):,} rows from {table.raw_path.name}")
    df = _dedupe(df, table)
    if table.column_renames:
        df = df.rename(columns=table.column_renames)
    if table.bq_name == "nirf_fact_rankings":
        df = _splice_official_rankings(df)
    return df


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--table", default=None,
                    help="Build only this BQ table name (e.g. nirf_fact_master)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build in-mem and print summary; write nothing to disk")
    args = ap.parse_args()

    chosen = TABLES
    if args.table:
        chosen = [t for t in TABLES if t.bq_name == args.table]
        if not chosen:
            raise SystemExit(f"unknown table {args.table!r}; known: {[t.bq_name for t in TABLES]}")

    if not args.dry_run:
        CLEAN.mkdir(parents=True, exist_ok=True)

    print(f"NIRF build_clean   ({'dry-run' if args.dry_run else f'writing to {CLEAN}'})")
    cache: dict[str, pd.DataFrame] = {}
    for t in chosen:
        print(f"  {t.bq_name}")
        df = cache.get(t.bq_name)
        if df is None:
            df = build(t, cache)
            cache[t.bq_name] = df
        print(f"    → {len(df):,} rows × {len(df.columns)} cols")
        if args.dry_run:
            continue
        df.to_parquet(t.local_path, index=False)
        print(f"    wrote {t.local_path}")

    print("✓ done.")


if __name__ == "__main__":
    main()
