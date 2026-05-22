"""
Occupation profile of NON-TECHNICAL (general) graduates — what jobs they end up
in, and at what wage. Decomposes the flat "Others (general)" row of the curve.

PLFS lumps Arts/Commerce/Science/Law/Mgmt/… into one "general graduate" bucket
(tedu = none, gedu = graduate/PG). That bucket is NOT uniform: a slice become
lawyers / accountants / officers (well paid), most become teachers / clerks /
salespeople (modest), many aren't employed. This table splits it by NCO group,
and lets us size field-specific supply from the general pool (occupation share ×
general-grad population − NIRF-college output = non-ranked contribution; ratios,
not levels — PLFS stock vs AISHE/NIRF flow).

Population: general grads (tedu in {'', '01'} & gedu in {'12','13'}), age 22-30.
Wage: combined regular-salaried (ern_reg) OR self-employed (ern_self) monthly.

Data via datasource.py (PLFS clean CSV today → plfs_persons BQ table later).
Output: wage_curves/general_grad_occupations.csv
"""

import collections
import csv
from pathlib import Path

from datasource import plfs_persons, nco_labels, wmedian

OUT = Path(__file__).resolve().parent / "general_grad_occupations.csv"
AGE_LO, AGE_HI = 22, 30
EMPLOYED = {"11", "12", "21", "31", "41", "42", "51"}
MIN_SHARE = 0.5   # % — occupations below this are lumped into "Other occupations"


def main():
    labels = nco_labels()
    total_pop = employed_pop = 0.0
    occ_w = collections.defaultdict(float)
    occ_wage = collections.defaultdict(list)
    occ_n = collections.defaultdict(int)

    for r, w in plfs_persons():
        tedu = (r.get("tedu_lvl") or "").strip()
        gedu = (r.get("gedu_lvl") or "").strip()
        if not (tedu in ("", "01") and gedu in ("12", "13")):
            continue
        try:
            age = int(r["age"])
        except (ValueError, KeyError):
            continue
        if not (AGE_LO <= age <= AGE_HI):
            continue
        total_pop += w
        pas = r.get("pas")
        if pas not in EMPLOYED:
            continue
        employed_pop += w
        occ = (r.get("ocu_pas") or "").strip() or "(unspecified)"
        occ_w[occ] += w
        occ_n[occ] += 1
        wage = 0
        if pas == "31":
            wage = int(r.get("ern_reg", "0") or "0")
        elif pas in ("11", "12"):
            wage = int(r.get("ern_self", "0") or "0")
        if wage > 0:
            occ_wage[occ].append((wage, w))

    rows, other_w, other_wage = [], 0.0, []
    for occ, w in sorted(occ_w.items(), key=lambda kv: -kv[1]):
        share = w / total_pop * 100
        if share < MIN_SHARE:
            other_w += w; other_wage += occ_wage[occ]; continue
        med = wmedian(occ_wage[occ])
        rows.append(dict(nco_code=occ, occupation=labels.get(occ, occ),
                         share_of_genpop_pct=round(share, 1),
                         median_wage_inr_mo=med, median_wage_inr_yr=med * 12 if med else None,
                         n=occ_n[occ]))
    if other_w:
        med = wmedian(other_wage)
        rows.append(dict(nco_code="(other)", occupation="Other occupations (each <0.5%)",
                         share_of_genpop_pct=round(other_w / total_pop * 100, 1),
                         median_wage_inr_mo=med, median_wage_inr_yr=med * 12 if med else None, n=0))
    rows.append(dict(nco_code="(none)", occupation="Not employed / out of labour force",
                     share_of_genpop_pct=round((total_pop - employed_pop) / total_pop * 100, 1),
                     median_wage_inr_mo=None, median_wage_inr_yr=None, n=0))

    cols = ["nco_code", "occupation", "share_of_genpop_pct",
            "median_wage_inr_mo", "median_wage_inr_yr", "n"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

    print(f"General (non-technical) graduates, age {AGE_LO}-{AGE_HI}")
    print(f"Employment rate (WPR): {employed_pop/total_pop*100:.1f}%   (pop {total_pop/1e6:.1f}M)\n")
    print(f'{"NCO":>5}  {"Occupation":<46}{"%pop":>6}{"₹/mo":>9}{"n":>6}')
    print("-" * 76)
    for r in rows:
        print(f'{r["nco_code"]:>5}  {r["occupation"][:46]:<46}{r["share_of_genpop_pct"]:>6}'
              f'{(("₹"+format(r["median_wage_inr_mo"],",")) if r["median_wage_inr_mo"] else "—"):>9}'
              f'{r["n"]:>6}')
    print(f"\nWrote {OUT.parent.name}/{OUT.name}")


if __name__ == "__main__":
    main()
