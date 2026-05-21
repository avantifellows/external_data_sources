"""
PLFS wage + employment baseline by discipline — the population reference layer
for the cross-source wage-curve analysis.

PLFS is the only source that observes the *whole population* of degree holders
(not just those at ranked colleges). It is therefore the anchor: the
enrollment-weighted average wage across all college tiers (NIRF top tiers +
the long tail) should reconcile back to the PLFS discipline mean.

Discipline grouping comes from codemaps/discipline.csv (field of study, derived
from technical_education). PLFS can only separate the technical fields it codes
for — Engineering & Technology, Medicine & Health, Agriculture, Crafts, Other
technical. Everything else (Arts / Science / Commerce / Management / Law) is
undifferentiated and lands in "General graduate/PG (non-technical)".

  plfs_discipline buckets (graduate level only — UG degree or PG):
    Engineering & Technology      tedu 03 (degree) | 13 (grad+ diploma)
    Medicine & Health             tedu 04 | 14
    Agriculture                   tedu 02 | 12
    Crafts                        tedu 05 | 15
    Other technical/professional  tedu 06 | 16
    General graduate/PG           tedu 01 AND gedu in {12,13}

Per bucket it reports (regular-salaried, weighted):
    WPR (worker-pop ratio), regular-salaried share, and weighted
    mean / p25 / median / p75 monthly wage (ern_reg).

IMPORTANT — comparability with NIRF:
    NIRF median_salary is a *fresh-graduate placement* salary. PLFS median here
    is the *stock* of all degree holders in the workforce (all ages), which runs
    higher (experience premium). For a like-for-like anchor against NIRF, pass
    --age-min/--age-max to restrict to a young cohort (e.g. 22-28). Both views
    are useful: full-stock for the population picture, young-cohort for the
    fresh-grad reconciliation in the wage curve.

Run:
    python3 analyses/wage_by_discipline.py                       # default release
    python3 analyses/wage_by_discipline.py --release annual_2021_22
    python3 analyses/wage_by_discipline.py --age-min 22 --age-max 28

Requires the release's clean person CSV on disk
(clean/<release>/perv1.csv or cperv1.csv). PLFS is not in BigQuery; these
analyses read the parsed clean CSVs directly.
"""

import argparse
import csv
import collections
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from weights import get_weight_fn          # noqa: E402
from releases import RELEASES               # noqa: E402

CODEMAP = ROOT / "codemaps" / "discipline.csv"
DEFAULT_RELEASE = "annual_2023_24"

EMPLOYED_CODES = {"11", "12", "21", "31", "41", "42", "51"}
GRADUATE_LEVELS = {"Degree", "Diploma (graduate+)"}   # exclude below-graduate diplomas
GENERAL_GRAD = "General graduate/PG"

# Order disciplines for the printout (Engineering first — it's the focus).
DISCIPLINE_ORDER = [
    "Engineering & Technology",
    "Medicine & Health",
    "Agriculture",
    "Other technical/professional",
    "Crafts",
    GENERAL_GRAD,
]


def load_discipline_map():
    """tedu_lvl -> (plfs_discipline, degree_level) for the technical codes."""
    out = {}
    with CODEMAP.open() as f:
        for r in csv.DictReader(f):
            out[r["tedu_lvl"]] = (r["plfs_discipline"], r["degree_level"])
    return out


def bucket_of(gedu, tedu, dmap):
    """Return (plfs_discipline, degree_level) restricted to graduate level, or None.

    Technical fields are read from the codemap. The non-technical general
    graduate/PG bucket needs gedu (tedu=01 carries no field), so it is derived
    here rather than in the flat codemap.
    """
    disc, lvl = dmap.get(tedu, ("General / non-technical", "n/a"))
    if tedu and tedu != "01":
        return (disc, lvl) if lvl in GRADUATE_LEVELS else None
    # tedu missing or "01" -> no technical education; use general education level
    if gedu == "13":
        return (GENERAL_GRAD, "Postgraduate (general)")
    if gedu == "12":
        return (GENERAL_GRAD, "Graduate (general)")
    return None   # not a graduate -> excluded from the discipline baseline


def weighted_percentiles(values_weights, percentiles=(25, 50, 75)):
    if not values_weights:
        return {p: None for p in percentiles}
    s = sorted(values_weights)
    total_w = sum(w for _, w in s)
    out, cum = {}, 0.0
    remaining = {p: total_w * p / 100 for p in percentiles}
    for v, w in s:
        cum += w
        for p in list(remaining):
            if cum >= remaining[p]:
                out[p] = v
                del remaining[p]
        if not remaining:
            break
    for p in remaining:
        out[p] = s[-1][0]
    return out


def per_csv_path(release_id):
    out_dir = RELEASES[release_id]["out_dir"]
    for name in ("perv1.csv", "cperv1.csv"):
        p = out_dir / name
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=DEFAULT_RELEASE,
                    help=f"PLFS release_id (default {DEFAULT_RELEASE})")
    ap.add_argument("--age-min", type=int, default=None)
    ap.add_argument("--age-max", type=int, default=None)
    args = ap.parse_args()

    dmap = load_discipline_map()
    weight_fn = get_weight_fn(args.release)
    src = per_csv_path(args.release)
    if src is None:
        sys.exit(
            f"No clean person CSV for {args.release}. Expected "
            f"clean/{args.release}/perv1.csv (or cperv1.csv). "
            f"Parse the release first: python3 scripts/parse_data.py {args.release}"
        )

    agg = collections.defaultdict(lambda: {
        "pop": 0.0, "employed": 0.0, "regular": 0.0,
        "n": 0, "n_reg": 0, "wages": [],
    })

    with src.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tedu = (row.get("tedu_lvl") or "").strip()
            gedu = (row.get("gedu_lvl") or "").strip()
            b = bucket_of(gedu, tedu, dmap)
            if b is None:
                continue
            if args.age_min is not None or args.age_max is not None:
                try:
                    age = int(row["age"])
                except (ValueError, KeyError):
                    continue
                if args.age_min is not None and age < args.age_min:
                    continue
                if args.age_max is not None and age > args.age_max:
                    continue
            disc, _lvl = b
            try:
                w = weight_fn(row)
            except Exception:
                continue
            d = agg[disc]
            d["pop"] += w
            d["n"] += 1
            pas = row.get("pas")
            if pas in EMPLOYED_CODES:
                d["employed"] += w
                if pas == "31":
                    d["regular"] += w
                    try:
                        wage = int(row.get("ern_reg", "0") or "0")
                    except ValueError:
                        wage = 0
                    if wage > 0:
                        d["n_reg"] += 1
                        d["wages"].append((wage, w))

    age_note = ""
    if args.age_min is not None or args.age_max is not None:
        age_note = f"  (age {args.age_min or ''}-{args.age_max or ''})"

    print("=" * 104)
    print(f"PLFS {args.release} — wage + employment by discipline (graduate level){age_note}")
    print("=" * 104)
    hdr = (f'{"Discipline":<30} {"N":>7} {"Pop(M)":>8} {"WPR":>6} {"%Reg":>6}'
           f'   {"Mean":>9} {"P25":>9} {"Median":>9} {"P75":>9}   {"n(reg)":>7}')
    print(hdr)
    print("-" * 104)

    def fmt(v):
        if v is None:
            return "    —    "
        return f"₹{v:>7,.0f}"

    for disc in DISCIPLINE_ORDER:
        d = agg.get(disc)
        if not d or d["n"] == 0:
            continue
        wpr = d["employed"] / d["pop"] * 100 if d["pop"] else 0
        regshare = d["regular"] / d["pop"] * 100 if d["pop"] else 0
        pcts = weighted_percentiles(d["wages"])
        mean = (sum(v * w for v, w in d["wages"]) / sum(w for _, w in d["wages"])
                if d["wages"] else None)
        print(f'{disc:<30} {d["n"]:>7,} {d["pop"]/1e6:>8,.2f} '
              f'{wpr:>5.1f}% {regshare:>5.1f}%   '
              f'{fmt(mean)} {fmt(pcts[25])} {fmt(pcts[50])} {fmt(pcts[75])}'
              f'   {d["n_reg"]:>7,}')
    print("-" * 104)
    print("Wages are monthly regular-salaried earnings (ern_reg), weighted. "
          "Annualise ×12 to compare with NIRF median_salary.")


if __name__ == "__main__":
    main()
