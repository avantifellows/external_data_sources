"""
Engineering wage curve — cross-source synthesis (NIRF + AISHE + PLFS).

The story this builds:
  * NIRF ranks the top ~200 engineering institutes and reports their placement
    rate + median fresh-graduate salary. We split them into IIT / NIT / IIIT /
    Other-NIRF tiers (by institute_name).
  * AISHE is the canonical count of ALL engineering graduates nationally. The
    NIRF-ranked tiers are only ~20% of them; the other ~80% graduate from
    non-ranked "Other Engg Colleges" with no published wage data.
  * PLFS observes the whole population's wages. It is the anchor: the
    graduate-weighted average wage across all tiers must reconcile to the PLFS
    engineering-graduate wage. We back-solve the unknown "Other Engg Colleges"
    wage from that constraint.

Output is a descending wage curve:
    IIT/IIIT  >  NIT  >  Other NIRF  >  Other Engg Colleges      (PLFS = weighted mean)

Data sources at runtime:
  NIRF  -> BigQuery (avantifellows.external_data_sources.nirf_fact_aggregate)
           via the `bq` CLI and nirf_engineering_tiers.sql
  AISHE -> ../aishe/clean/outturn.parquet (local)
  PLFS  -> the engineering-graduate ANNUAL wage anchor. Until PLFS is loaded,
           pass it with --plfs-annual-wage (see ../plfs/analyses/wage_by_discipline.py,
           which produces a monthly figure; annualise ×12). For a like-for-like
           fresh-graduate anchor, restrict that script to a young cohort
           (--age-min 22 --age-max 28).

Run:
    python3 build_wage_curve.py --plfs-annual-wage 300000
    python3 build_wage_curve.py --nirf-year 2022 --aishe-year 2021-22 --plfs-annual-wage 300000

Public-tier graduate counts:
  NIRF's graduating_on_time is unreliable for IITs/NITs/IIITs — they run split
  4-yr + 5-yr programs and report them inconsistently (e.g. IIT Madras shows
  only its 5-yr dual-degree; some IITs show 0), so it captures only a partial
  placement-pool count (~6k for 19 IITs vs ~16k reality). Private "Other NIRF"
  colleges run a single B.Tech and report completely, so they keep their NIRF
  count. The three public tiers are therefore sized from actual UG intake
  (josaa_2022_seats.csv) × a completion rate, holding placement rate + median
  wage at the NIRF tier average. This also subsumes the un-ranked institutes:
  the seat totals already cover all 23/31/26 of them. Disable with
  --no-public-from-seats to fall back to raw NIRF counts.

Caveat: JoSAA-2022 seats describe the cohort admitted in 2022 (graduating ~2026),
  while the AISHE 2021-22 graduating class was admitted ~2018 when IIT/NIT seats
  were smaller — so 2022 seats modestly overstate the 2021-22 public graduating
  cohort. Used as instructed; the completion rate (--completion-rate) absorbs
  some of this.
"""

import argparse
import csv
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
AISHE_PARQUET = ROOT.parent / "aishe" / "clean" / "outturn.parquet"
NIRF_SQL = ROOT / "nirf_engineering_tiers.sql"
JOSAA_SEATS_CSV = ROOT / "josaa_2022_seats.csv"

# Display order: top of the curve to the tail.
TIER_ORDER = ["IIT", "IIIT", "NIT", "Other NIRF", "Other Engg Colleges"]
PUBLIC_TIERS = ["IIT", "NIT", "IIIT"]


def josaa_seats() -> dict:
    """{tier: {"institutes": int, "ug_seats": int}} from josaa_2022_seats.csv."""
    out = {}
    if not JOSAA_SEATS_CSV.exists():
        return out
    df = pd.read_csv(JOSAA_SEATS_CSV)
    for _, r in df.iterrows():
        out[r["tier"]] = {"institutes": int(r["institutes"]),
                          "ug_seats": int(r["ug_seats_2022"])}
    return out


def nirf_tiers(year: int) -> dict:
    """Run nirf_engineering_tiers.sql via bq, return {tier: {grads, placed, ...}}."""
    sql = NIRF_SQL.read_text()
    # Pass the query via stdin: bq parses a leading "--" SQL comment as a flag.
    cmd = [
        "bq", "query", "--use_legacy_sql=false", "--format=csv",
        f"--parameter=yr:INT64:{year}",
    ]
    out = subprocess.run(cmd, input=sql, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"bq query failed:\n{out.stderr}")
    rows = list(csv.DictReader(io.StringIO(out.stdout)))
    tiers = {}
    for r in rows:
        tiers[r["tier"]] = {
            "n_inst": int(r["n_inst"]),
            "graduates": float(r["graduates"]),
            "placed": float(r["placed"]),
            "higher_studies": float(r["higher_studies"]),
            "placement_rate": float(r["placement_rate"]),
            "wtd_median_salary": float(r["wtd_median_salary"]),
        }
    return tiers


def aishe_eng_grads(aishe_year: str) -> float:
    """All-India UG Engineering & Technology graduating class from AISHE."""
    df = pd.read_parquet(AISHE_PARQUET)
    sl = df[(df.aishe_year == aishe_year) & (df.state == "All")
            & (df.social_category == "All") & (df.programme == "All")
            & (df.gender == "Total") & (df.level == "Under Graduate")
            & (df.discipline == "Engineering & Technology")]
    if sl.empty:
        sys.exit(f"No AISHE engineering UG total for {aishe_year}.")
    return float(sl.out_turn.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nirf-year", type=int, default=2022)
    ap.add_argument("--aishe-year", default="2021-22")
    ap.add_argument("--plfs-annual-wage", type=float, required=True,
                    help="PLFS engineering-graduate ANNUAL wage (₹). Anchors the curve.")
    ap.add_argument("--plfs-placement-rate", type=float, default=None,
                    help="Optional: PLFS engineering employment/regular-salaried rate (%%).")
    ap.add_argument("--public-from-seats", action=argparse.BooleanOptionalAction, default=True,
                    help="Size IIT/NIT/IIIT graduate volume from josaa_2022_seats.csv "
                         "instead of NIRF graduating_on_time (default on; NIRF undercounts them).")
    ap.add_argument("--completion-rate", type=float, default=0.93,
                    help="Share of UG seats that graduate (default 0.93). Applied to JoSAA seats.")
    args = ap.parse_args()

    tiers = nirf_tiers(args.nirf_year)
    total_grads = aishe_eng_grads(args.aishe_year)

    # Size the public tiers (IIT/NIT/IIIT) from actual UG intake, since NIRF's
    # graduating_on_time undercounts them (incomplete 4-yr/5-yr program reporting).
    # Keep their NIRF placement rate + median wage (robust ratios/medians); only the
    # graduate VOLUME is replaced. Seat totals already cover all institutes incl.
    # those NIRF didn't rank, so no separate un-ranked step is needed.
    adj_notes = []
    if args.public_from_seats:
        seats = josaa_seats()
        for tier in PUBLIC_TIERS:
            t, s = tiers.get(tier), seats.get(tier)
            if not t or not s:
                continue
            grads = s["ug_seats"] * args.completion_rate
            t["nirf_grads"] = t["graduates"]
            t["graduates"] = grads
            t["placed"] = (grads * t["placement_rate"] / 100
                           if t["placement_rate"] is not None else None)
            t["higher_studies"] = None
            t["n_inst"] = s["institutes"]
            adj_notes.append(
                f"{tier}: {s['institutes']} institutes, {s['ug_seats']:,} JoSAA-2022 seats "
                f"× {args.completion_rate:.0%} = {grads:,.0f} grads "
                f"(NIRF reported {t['nirf_grads']:,.0f})")

    ranked_grads = sum(t["graduates"] for t in tiers.values())
    resid_grads = total_grads - ranked_grads
    if resid_grads <= 0:
        sys.exit(f"Residual non-positive ({resid_grads:,.0f}): AISHE total "
                 f"({total_grads:,.0f}) <= NIRF ranked ({ranked_grads:,.0f}). "
                 f"Check year alignment.")

    # Back-solve the Other-Engg-Colleges wage from the PLFS reconciliation:
    #   Σ(grads_tier * wage_tier) / total_grads = plfs_annual_wage
    known_wage_mass = sum(t["graduates"] * t["wtd_median_salary"] for t in tiers.values())
    resid_wage = (args.plfs_annual_wage * total_grads - known_wage_mass) / resid_grads

    # Back-solve residual placement rate if a PLFS rate is supplied (same logic).
    resid_rate = None
    if args.plfs_placement_rate is not None:
        known_placed_mass = sum(t["graduates"] * t["placement_rate"] for t in tiers.values())
        resid_rate = (args.plfs_placement_rate * total_grads - known_placed_mass) / resid_grads

    tiers["Other Engg Colleges"] = {
        "n_inst": None,
        "graduates": resid_grads,
        "placed": resid_grads * (resid_rate or float("nan")) / 100 if resid_rate else None,
        "higher_studies": None,
        "placement_rate": resid_rate,
        "wtd_median_salary": resid_wage,
    }

    print("=" * 96)
    print(f"ENGINEERING WAGE CURVE  —  NIRF {args.nirf_year} | AISHE {args.aishe_year} | "
          f"PLFS anchor ₹{args.plfs_annual_wage:,.0f}/yr")
    print("=" * 96)
    print(f'{"Tier":<22} {"Colleges":>9} {"Graduates":>11} {"Share":>7} '
          f'{"Placement%":>11} {"Median ₹/yr":>13}')
    print("-" * 96)
    for tier in TIER_ORDER:
        t = tiers.get(tier)
        if not t:
            continue
        share = t["graduates"] / total_grads * 100
        ninst = f'{t["n_inst"]:>9,}' if t["n_inst"] is not None else f'{"~tail":>9}'
        rate = f'{t["placement_rate"]:>10.1f}%' if t["placement_rate"] is not None else f'{"—":>11}'
        print(f'{tier:<22} {ninst} {t["graduates"]:>11,.0f} {share:>6.1f}% '
              f'{rate} {t["wtd_median_salary"]:>12,.0f}')
    print("-" * 96)
    print(f'{"TOTAL / weighted":<22} {"":>9} {total_grads:>11,.0f} {"100.0%":>7} '
          f'{"":>11} {args.plfs_annual_wage:>12,.0f}')
    print()
    print(f"Other Engg Colleges = {resid_grads:,.0f} grads "
          f"({resid_grads/total_grads*100:.0f}% of all UG engineering graduates), "
          f"implied median ₹{resid_wage:,.0f}/yr.")
    if adj_notes:
        print("Public tiers sized from UG intake (JoSAA 2022 seats; "
              "placement & wage held at NIRF tier average):")
        for n in adj_notes:
            print(f"  · {n}")
    if resid_wage < 0:
        print("  WARNING: implied residual wage is negative — the PLFS anchor is too low "
              "to be consistent with the NIRF tier wages at these grad weights.")


if __name__ == "__main__":
    main()
