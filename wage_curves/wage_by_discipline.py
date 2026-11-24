"""
PLFS wage + employment baseline by discipline — the population reference layer
for the wage curve. PLFS is the only source that observes the *whole population*
of degree holders (not just ranked colleges), so it anchors each discipline's
graduate-weighted average wage and employment rate.

Discipline grouping comes from ../plfs/codemaps/discipline.csv (field of study,
from technical_education). PLFS only separates the technical fields it codes for —
Engineering & Technology, Medicine & Health, Agriculture, Crafts, Other technical;
everything else (Arts/Science/Commerce/Management/Law) lands in "General graduate/PG".

  plfs_discipline buckets (graduate level only — UG degree or grad+ diploma):
    Engineering & Technology  tedu 03|13 · Medicine & Health 04|14 · Agriculture 02|12
    Crafts 05|15 · Other technical/professional 06|16 · General graduate/PG (tedu 01 & gedu 12|13)

Per bucket: WPR, regular-salaried share, weighted mean/p25/median/p75 monthly
wage (ern_reg). NIRF median_salary is a fresh-grad placement salary, so for a
like-for-like anchor restrict to a young cohort (--age-min 22 --age-max 28).

Data via datasource.py (PLFS clean CSV today → plfs_persons BQ table later).
Run: python3 wage_curves/wage_by_discipline.py [--release annual_2022_23] [--age-min 22 --age-max 28]
"""

import argparse
import collections
from pathlib import Path

from datasource import plfs_persons, wmedian, PLFS_RELEASE

CODEMAP = Path(__file__).resolve().parent.parent / "plfs" / "codemaps" / "discipline.csv"
EMPLOYED_CODES = {"11", "12", "21", "31", "41", "42", "51"}
GRADUATE_LEVELS = {"Degree", "Diploma (graduate+)"}
GENERAL_GRAD = "General graduate/PG"
DISCIPLINE_ORDER = ["Engineering & Technology", "Medicine & Health", "Agriculture",
                    "Other technical/professional", "Crafts", GENERAL_GRAD]


def load_discipline_map():
    import csv
    with CODEMAP.open() as f:
        return {r["tedu_lvl"]: (r["plfs_discipline"], r["degree_level"]) for r in csv.DictReader(f)}


def bucket_of(gedu, tedu, dmap):
    """(plfs_discipline, degree_level) restricted to graduate level, or None."""
    disc, lvl = dmap.get(tedu, ("General / non-technical", "n/a"))
    if tedu and tedu != "01":
        return (disc, lvl) if lvl in GRADUATE_LEVELS else None
    if gedu == "13":
        return (GENERAL_GRAD, "Postgraduate (general)")
    if gedu == "12":
        return (GENERAL_GRAD, "Graduate (general)")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=PLFS_RELEASE)
    ap.add_argument("--age-min", type=int, default=None)
    ap.add_argument("--age-max", type=int, default=None)
    args = ap.parse_args()

    dmap = load_discipline_map()
    agg = collections.defaultdict(lambda: {"pop": 0.0, "employed": 0.0, "regular": 0.0,
                                           "n": 0, "n_reg": 0, "wages": []})

    for row, w in plfs_persons(args.release):
        b = bucket_of((row.get("gedu_lvl") or "").strip(), (row.get("tedu_lvl") or "").strip(), dmap)
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
        d = agg[b[0]]
        d["pop"] += w; d["n"] += 1
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

    age_note = (f"  (age {args.age_min or ''}-{args.age_max or ''})"
                if (args.age_min is not None or args.age_max is not None) else "")
    print("=" * 104)
    print(f"PLFS {args.release} — wage + employment by discipline (graduate level){age_note}")
    print("=" * 104)
    print(f'{"Discipline":<30} {"N":>7} {"Pop(M)":>8} {"WPR":>6} {"%Reg":>6}'
          f'   {"Mean":>9} {"P25":>9} {"Median":>9} {"P75":>9}   {"n(reg)":>7}')
    print("-" * 104)

    def fmt(v):
        return "    —    " if v is None else f"₹{v:>7,.0f}"

    for disc in DISCIPLINE_ORDER:
        d = agg.get(disc)
        if not d or d["n"] == 0:
            continue
        wpr = d["employed"] / d["pop"] * 100 if d["pop"] else 0
        regshare = d["regular"] / d["pop"] * 100 if d["pop"] else 0
        mean = (sum(v * w for v, w in d["wages"]) / sum(w for _, w in d["wages"])
                if d["wages"] else None)
        print(f'{disc:<30} {d["n"]:>7,} {d["pop"]/1e6:>8,.2f} '
              f'{wpr:>5.1f}% {regshare:>5.1f}%   '
              f'{fmt(mean)} {fmt(wmedian(d["wages"], 25))} {fmt(wmedian(d["wages"], 50))} '
              f'{fmt(wmedian(d["wages"], 75))}   {d["n_reg"]:>7,}')
    print("-" * 104)
    print("Monthly regular-salaried earnings (ern_reg), weighted. Annualise ×12 vs NIRF median_salary.")


if __name__ == "__main__":
    main()
