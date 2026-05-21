#!/usr/bin/env python3
"""
plfs_baseline.py — population wage trajectory + % in regular work, from PLFS.

Source: PLFS Periodic Labour Force Survey, latest calendar round (CY2025),
person-level file `clean/calendar_2025/cperv1.csv` in the sibling `PLFS` repo
(~/Avanti Fellows Dropbox/.../Claude/PLFS). The *baseline* leg of the RoI
pipeline (NIRF = ranked-college pay/placement, AISHE = graduate universe).

Two-level classification — FIELD × CREDENTIAL — keyed on the technical-education
code (tedu_lvl) when present, else the general-education code (gedu_lvl):

  FIELD        CREDENTIAL  PLFS codes
  Engineering  Degree      tedu 03
               Diploma     tedu 08 (below-grad), 13 (grad+)
  Medical      Degree      tedu 04
               Diploma     tedu 09, 14
  OtherTech    Degree      tedu 02 (agri), 05 (crafts), 06 (other)
               Diploma     tedu 07, 10, 11, 12, 15, 16
  NonTechnical Degree      no technical edu (tedu 01) AND gedu 12/13 (grad/PG)
               Diploma     no technical edu (tedu 01) AND gedu 11 (diploma course)

Field = Degree + Diploma rolled up. Everyone below this level (general schooling
≤ higher secondary with no technical/diploma qualification) is excluded.

Per leaf group × age band (25-29, 30-34, 35-40):
    % in regular work  = wt(regular salaried, pas=31) / wt(group population)
    WPR (any work)     = wt(employed) / wt(group population)
    Median wage        = weighted median of ern_reg among regular salaried (₹/mo)
Weight rule for CY2025: weight = mult / 100.

No intermediate CSV: `compute()` returns the aggregates in memory and the RoI
combiner (wage_curves.py) imports it directly. Run this file standalone to print
the 8-group table for inspection.
"""
from __future__ import annotations

import collections
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
CLAUDE_ROOT = HERE.parents[3]

_PLFS_CANDIDATES = [
    CLAUDE_ROOT / "PLFS" / "clean" / "calendar_2025" / "cperv1.csv",
    HERE.parents[2] / "plfs" / "clean" / "calendar_2025" / "cperv1.csv",
]


def _find_src() -> Path:
    for p in _PLFS_CANDIDATES:
        if p.exists():
            return p
    sys.exit("PLFS microdata not found. Looked in:\n  "
             + "\n  ".join(str(p) for p in _PLFS_CANDIDATES))


# ── field × credential classification ─────────────────────────────────────────
# tedu_lvl code → (field, credential)
TEDU_MAP = {
    "03": ("Engineering", "Degree"),
    "08": ("Engineering", "Diploma"), "13": ("Engineering", "Diploma"),
    "04": ("Medical", "Degree"),
    "09": ("Medical", "Diploma"), "14": ("Medical", "Diploma"),
    "02": ("Other Technical", "Degree"), "05": ("Other Technical", "Degree"),
    "06": ("Other Technical", "Degree"),
    "07": ("Other Technical", "Diploma"), "10": ("Other Technical", "Diploma"),
    "11": ("Other Technical", "Diploma"), "12": ("Other Technical", "Diploma"),
    "15": ("Other Technical", "Diploma"), "16": ("Other Technical", "Diploma"),
}
NO_TECH = {"01", "", "00"}

FIELD_ORDER = ["Engineering", "Medical", "Other Technical", "Non-Technical"]
CRED_ORDER = ["Degree", "Diploma"]

EMPLOYED_CODES = {"11", "12", "21", "31", "41", "42", "51"}
REGULAR_CODE = "31"
AGE_BANDS = ["25-29", "30-34", "35-40"]


def classify(gedu: str, tedu: str):
    """Return (field, credential) or None if below degree/diploma level."""
    if tedu in TEDU_MAP:
        return TEDU_MAP[tedu]
    if tedu in NO_TECH:                       # no technical qualification → use general
        if gedu in {"12", "13"}:
            return ("Non-Technical", "Degree")
        if gedu == "11":
            return ("Non-Technical", "Diploma")
    return None


def age_band(a: int) -> str:
    if 25 <= a <= 29:
        return "25-29"
    if 30 <= a <= 34:
        return "30-34"
    if 35 <= a <= 40:
        return "35-40"
    return ""


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


def collect() -> dict:
    src = _find_src()
    agg = collections.defaultdict(lambda: {
        "pop": 0.0, "employed": 0.0, "regular": 0.0,
        "n": 0, "n_reg": 0, "wages_reg": [],
    })
    with src.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                age = int(row["age"])
                w = int(row["mult"]) / 100
            except (ValueError, KeyError):
                continue
            band = age_band(age)
            if not band:
                continue
            fc = classify(row.get("gedu_lvl") or "", row.get("tedu_lvl") or "")
            if fc is None:
                continue
            field, cred = fc
            d = agg[(field, cred, band)]
            d["pop"] += w
            d["n"] += 1
            if row.get("pas") in EMPLOYED_CODES:
                d["employed"] += w
                if row.get("pas") == REGULAR_CODE:
                    d["regular"] += w
                    d["n_reg"] += 1
                    try:
                        wage = int(row.get("ern_reg") or "0")
                    except ValueError:
                        wage = 0
                    if wage > 0:
                        d["wages_reg"].append((wage, w))
    return agg


def compute() -> dict[tuple, dict]:
    """Return {(field, credential, age_band): metrics}. Scans the microdata once.

    metrics = pct_regular_work, wpr_any_work_pct, median_monthly_wage,
              median_annual_lakh, p25_monthly, p75_monthly, pop_millions,
              n_unweighted, n_regular.
    Imported by the RoI combiner — no intermediate CSV.
    """
    agg = collect()
    out: dict[tuple, dict] = {}
    for field in FIELD_ORDER:
        for cred in CRED_ORDER:
            for band in AGE_BANDS:
                d = agg.get((field, cred, band))
                if not d or d["n"] == 0:
                    continue
                pcts = weighted_percentiles(d["wages_reg"])
                median = pcts[50]
                out[(field, cred, band)] = {
                    "field": field,
                    "credential": cred,
                    "group_label": f"{field} {cred}",
                    "age_band": band,
                    "n_unweighted": d["n"],
                    "pop_millions": round(d["pop"] / 1e6, 3),
                    "pct_regular_work": round(100 * d["regular"] / d["pop"], 1),
                    "wpr_any_work_pct": round(100 * d["employed"] / d["pop"], 1),
                    "median_monthly_wage": int(median) if median else None,
                    "median_annual_lakh": round(median * 12 / 1e5, 2) if median else None,
                    "p25_monthly": int(pcts[25]) if pcts[25] else None,
                    "p75_monthly": int(pcts[75]) if pcts[75] else None,
                    "n_regular": d["n_reg"],
                }
    return out


def main() -> None:
    cells = compute()
    rows = list(cells.values())

    # ── console: 8 leaf groups × 3 bands ─────────────────────────────────────
    print("PLFS CY2025 — field × credential, wage + % in regular work\n")
    pop = {(field, cred): sum(r["pop_millions"] for r in rows
                              if r["field"] == field and r["credential"] == cred) / 3
           for field in FIELD_ORDER for cred in CRED_ORDER}
    hdr = (f'{"Group":<26} {"25-29":>16} {"30-34":>16} {"35-40":>16} {"pop(M)":>8}')
    print(hdr)
    print(f'{"":<26} {"%reg / ₹L":>16} {"%reg / ₹L":>16} {"%reg / ₹L":>16}')
    print("-" * len(hdr))

    def cell(field, cred, band):
        for r in rows:
            if r["field"] == field and r["credential"] == cred and r["age_band"] == band:
                ml = r["median_annual_lakh"]
                return (f'{r["pct_regular_work"]:.0f}% / ₹{ml:.1f}L' if ml is not None
                        else f'{r["pct_regular_work"]:.0f}% / —')
        return "—"

    for field in FIELD_ORDER:
        for cred in CRED_ORDER:
            if not any(r["field"] == field and r["credential"] == cred for r in rows):
                continue
            print(f'{field+" "+cred:<26} '
                  f'{cell(field, cred, "25-29"):>16} {cell(field, cred, "30-34"):>16} '
                  f'{cell(field, cred, "35-40"):>16} {pop[(field, cred)]:>8.2f}')
        print()


if __name__ == "__main__":
    main()
