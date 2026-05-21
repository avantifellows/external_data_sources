#!/usr/bin/env python3
"""
wage_curves.py — LEGACY (superseded by avanti_estimate.py).

Retained only so the donor-report consumers (build_roi / build_projection /
build_deck_outcomes) keep importing the loader API until they are repointed at
avanti_estimate_deck.csv in the monorepo merge. Do NOT extend this — the frozen
wage-curve method is avanti_estimate.py. See README.

────────────────────────────────────────────────────────────────────────────
wage_curves.py — combine NIRF + PLFS + AISHE into the RoI wage-curve table.

This is the join step of the three-source RoI pipeline. It reads the three
clean per-source extracts and emits one row per destination tier with: fresh
pay, age→mid→senior progression, a formal-employment rate, annual graduate
counts, and the tier's share of all STEM / all UG graduates (the "1 in N"
selectivity that slide E3 quotes). Every number is traceable to one source —
no hand-compiled scorecards.

    NIRF  (nirf_tiers.csv)   ranked-college fresh-grad median pay + placement
                             → IIT / NIT-IIIT / Top State Eng early pay & rate
    PLFS  (plfs_baseline.csv) population employment + median wage + the age→wage
                             growth shape that lifts fresh pay to mid/senior;
                             also the "Other STEM" baseline outright
    AISHE (aishe_grads.csv)  annual UG graduate universe → tier shares + the
                             residual size of the "Other STEM" tier

Two inputs are NOT in the three tables and are set as documented constants:
    MBBS_BDS_FRESH_LAKH      govt junior-resident pay scale (7th CPC), ₹7.0 L/yr
    MBBS_BDS_GOVT_SEATS      govt MBBS+BDS annual seats (NMC/DCI), ~60,000
Both are flagged in the output `pay_source` / `notes`.

Output: roi/clean/wage_curves.csv — schema-compatible with the donor-brief
wage-curve loader (same bucket labels), so it is a drop-in replacement for the
old hand-compiled stem_pipeline_buckets CSV.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import plfs_baseline   # same dir; PLFS aggregates computed in-memory (no CSV)

HERE = Path(__file__).resolve()
CLEAN = HERE.parents[1] / "clean"
NIRF_CSV = CLEAN / "nirf_tiers.csv"
AISHE_CSV = CLEAN / "aishe_grads.csv"
OUT = CLEAN / "wage_curves.csv"

# ── documented constants (not derivable from the three source tables) ─────────
MBBS_BDS_FRESH_LAKH = 7.0        # govt junior-resident scale, 7th CPC (~₹56k/mo)
MBBS_BDS_GOVT_SEATS = 60_000     # govt MBBS + BDS annual seats (NMC/DCI, approx)
MBBS_BDS_EMP_RATE = 100.0        # govt service / compulsory internship → ~all

# bucket labels MUST match the donor-brief loader's BUCKET_TO_TIER keys
B_IIT = "1. IITs"
B_NIT = "2. NITs / IIITs"
B_MBBS = "3. Govt MBBS colleges"
B_TOPENG = "4. Top-200 NIRF Engineering (non-IIT/NIT/IIIT)"
B_OTHER = "5. All other STEM grads (non-elite engineering + IT/Computer + non-MBBS medical)"

FIELDS = ["bucket", "n_institutes", "annual_grads", "annual_placed",
          "employment_rate_pct", "rate_source",
          "avg_pay_25_29_lakh", "avg_pay_30_34_lakh", "avg_pay_35_40_lakh",
          "pay_metric", "pay_source", "pct_of_stem_ug", "pct_of_all_ug", "notes"]


# ── consumer API ──────────────────────────────────────────────────────────────
# Same surface the donor-brief deck/RoI/projection scripts import. They depend on
# this module (external_data_sources/roi owns the wage-curve data AND its loader),
# replacing the old hand-compiled India-Public-Education-Data table.
BUCKET_TO_TIER = {
    B_IIT: "IIT",
    B_NIT: "NIT/IIIT",
    B_MBBS: "MBBS/BDS",
    B_TOPENG: "Top State Eng",
    B_OTHER: "Other Sci",
}
TIER_ORDER = ["IIT", "NIT/IIIT", "MBBS/BDS", "Top State Eng", "Other Sci"]


def load_wage_curves() -> dict[str, dict]:
    """{tier → {early, mid, senior, employment_rate, expected_*}} in ₹ Lakhs.

    Reads the generated wage_curves.csv. `expected_*` = raw pay × employment
    rate (expected earnings for a randomly-drawn graduate of the tier).
    """
    if not OUT.exists():
        raise FileNotFoundError(
            f"{OUT} missing — generate it first: python3 "
            f"{Path(__file__).resolve().parent.name}/wage_curves.py")
    out: dict[str, dict] = {}
    with OUT.open() as f:
        for row in csv.DictReader(f):
            tier = BUCKET_TO_TIER.get(row["bucket"])
            if tier is None:
                continue
            early = float(row["avg_pay_25_29_lakh"])
            mid = float(row["avg_pay_30_34_lakh"])
            senior = float(row["avg_pay_35_40_lakh"])
            emp = float(row["employment_rate_pct"]) / 100.0
            out[tier] = {
                "early": early, "mid": mid, "senior": senior,
                "employment_rate": emp,
                "expected_early": early * emp,
                "expected_mid": mid * emp,
                "expected_senior": senior * emp,
            }
    missing = set(TIER_ORDER) - set(out)
    if missing:
        raise ValueError(f"wage_curves.csv is missing tiers: {missing}")
    return out


def expected_earnings_cr(tier: str, n_early: int = 5, n_mid: int = 5,
                         n_senior: int = 0, curves: dict | None = None,
                         employment_adjusted: bool = True) -> float:
    """₹ Crore earnings over an arbitrary horizon (year counts per life-stage).
    employment_adjusted multiplies by the tier's employment rate (expected
    earnings for a randomly-drawn graduate)."""
    curves = curves or load_wage_curves()
    c = curves[tier]
    if employment_adjusted:
        pay = (n_early * c["expected_early"] + n_mid * c["expected_mid"]
               + n_senior * c["expected_senior"])
    else:
        pay = (n_early * c["early"] + n_mid * c["mid"] + n_senior * c["senior"])
    return pay / 100  # ₹L → ₹Cr


def cumulative_10y_cr(tier: str, curves: dict | None = None,
                      employment_adjusted: bool = True) -> float:
    """10-yr horizon (5 yr early + 5 yr mid), backwards-compatible alias."""
    return expected_earnings_cr(tier, n_early=5, n_mid=5, curves=curves,
                                employment_adjusted=employment_adjusted)


def _load(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"Missing input: {path}. Run the per-source extractors first.")
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    nirf = {r["tier"]: r for r in _load(NIRF_CSV)}
    aishe = {r["discipline"]: r for r in _load(AISHE_CSV)}

    # PLFS field × credential aggregates, computed in-memory (no intermediate CSV)
    plfs = plfs_baseline.compute()

    def pm(field, cred, band):   # PLFS median annual ₹L
        return plfs[(field, cred, band)]["median_annual_lakh"]

    def pr(field, cred, band="25-29"):  # PLFS % in regular work
        return plfs[(field, cred, band)]["pct_regular_work"]

    # AISHE denominators
    stem_ug = int(aishe["__STEM_UG__"]["ug_outturn_2024_25"])
    all_ug = int(aishe["__ALL_UG__"]["ug_outturn_2024_25"])

    # ── PLFS growth multipliers (median ₹L, ×early=25-29) ─────────────────────
    # Ranked tiers are DEGREE holders → use the Degree progression shape.
    def growth(field):
        e = pm(field, "Degree", "25-29")
        return pm(field, "Degree", "30-34") / e, pm(field, "Degree", "35-40") / e
    eng_gmid, eng_gsen = growth("Engineering")
    med_gmid, med_gsen = growth("Medical")

    # ── "Other STEM" baseline = the modal "ordinary graduate" a non-elite Avanti
    # student becomes: PLFS Non-Technical DEGREE (B.Sc/B.A/B.Com graduate).
    # NOT blended with engineering — that would overstate the counterfactual.
    other_early = pm("Non-Technical", "Degree", "25-29")
    other_mid = pm("Non-Technical", "Degree", "30-34")
    other_sen = pm("Non-Technical", "Degree", "35-40")
    other_emp = pr("Non-Technical", "Degree")

    def pct(n, denom):
        return round(100 * n / denom, 2)

    rows = []

    # tiers 1,2,4 — NIRF pay + placement, PLFS-engineering progression
    for label, tier, note in [
        (B_IIT, "IIT", "All IITs reporting a median + grad count to NIRF 2025. "
                       "Progression assumes IIT grads track the PLFS Engineering "
                       "growth curve; the true top-quartile (FAANG/MBA) is steeper."),
        (B_NIT, "NIT/IIIT", "NITs + IIITs reporting to NIRF 2025."),
        (B_TOPENG, "Top State Eng", "Engineering institutes ranked <=200 in NIRF "
                                    "2025, excluding IIT/NIT/IIIT (BITS, VIT, COEP, "
                                    "Anna Univ campuses, etc.)."),
    ]:
        s = nirf[tier]
        grads, placed = int(float(s["annual_grads"])), int(float(s["annual_placed"]))
        early = float(s["grad_wtd_median_salary"]) / 1e5
        rows.append({
            "bucket": label,
            "n_institutes": int(float(s["n_institutes"])),
            "annual_grads": grads,
            "annual_placed": placed,
            "employment_rate_pct": float(s["placement_rate_pct"]),
            "rate_source": "NIRF 2025 placement rate (students_placed / graduating_on_time)",
            "avg_pay_25_29_lakh": round(early, 1),
            "avg_pay_30_34_lakh": round(early * eng_gmid, 1),
            "avg_pay_35_40_lakh": round(early * eng_gsen, 1),
            "pay_metric": f"NIRF grad-weighted median salary; progression via PLFS "
                          f"Engineering x{eng_gmid:.2f} / x{eng_gsen:.2f}",
            "pay_source": "NIRF 2025 (nirf_fact_aggregate, BQ) + PLFS CY2025 age-band growth",
            "pct_of_stem_ug": pct(grads, stem_ug),
            "pct_of_all_ug": pct(grads, all_ug),
            "notes": note + " Non-placed are largely higher-studies, not unemployed.",
        })

    # tier 3 — Govt MBBS/BDS: govt scale + PLFS-medical progression
    rows.append({
        "bucket": B_MBBS,
        "n_institutes": "",
        "annual_grads": MBBS_BDS_GOVT_SEATS,
        "annual_placed": MBBS_BDS_GOVT_SEATS,
        "employment_rate_pct": MBBS_BDS_EMP_RATE,
        "rate_source": "Compulsory internship + govt service — ~all govt-seat MBBS/BDS practise",
        "avg_pay_25_29_lakh": round(MBBS_BDS_FRESH_LAKH, 1),
        "avg_pay_30_34_lakh": round(MBBS_BDS_FRESH_LAKH * med_gmid, 1),
        "avg_pay_35_40_lakh": round(MBBS_BDS_FRESH_LAKH * med_gsen, 1),
        "pay_metric": f"Govt junior-resident scale at start; progression via PLFS "
                      f"Medical x{med_gmid:.2f} / x{med_gsen:.2f}",
        "pay_source": "7th CPC junior-resident scale (~₹56k/mo) + PLFS CY2025 Medical growth",
        "pct_of_stem_ug": pct(MBBS_BDS_GOVT_SEATS, stem_ug),
        "pct_of_all_ug": pct(MBBS_BDS_GOVT_SEATS, all_ug),
        "notes": f"~{MBBS_BDS_GOVT_SEATS:,} govt MBBS+BDS seats (NMC/DCI, approx). PLFS "
                 "Medical pools MBBS with nurses/AYUSH/pharma, so age progression "
                 "UNDER-counts true specialist trajectory (post-PG ₹15-25 L).",
    })

    # tier 5 — Other STEM: PLFS baseline outright; residual of STEM UG
    ranked = sum(r["annual_grads"] for r in rows)
    other_grads = stem_ug - ranked
    rows.append({
        "bucket": B_OTHER,
        "n_institutes": "",
        "annual_grads": other_grads,
        "annual_placed": "",
        "employment_rate_pct": round(other_emp, 1),
        "rate_source": "PLFS CY2025 % in regular work @25-29, non-technical graduate+PG",
        "avg_pay_25_29_lakh": round(other_early, 1),
        "avg_pay_30_34_lakh": round(other_mid, 1),
        "avg_pay_35_40_lakh": round(other_sen, 1),
        "pay_metric": "PLFS non-technical graduate+PG regular-salaried median (incl. B.Sc science)",
        "pay_source": "PLFS CY2025 directly (this bucket IS the PLFS cohort — no NIRF anchor)",
        "pct_of_stem_ug": pct(other_grads, stem_ug),
        "pct_of_all_ug": pct(other_grads, all_ug),
        "notes": "The modal 'ordinary graduate' counterfactual: a non-elite student "
                 "becomes a general/science graduate. Pay & % in regular work from the "
                 "PLFS non-technical graduate+PG group (the science/general-degree cohort). "
                 "grads = all STEM UG minus the four ranked/govt tiers. NOT blended with "
                 "engineering (that overstates the rest: STEM-weighted blend ≈ ₹3.1 L).",
    })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        wtr = csv.DictWriter(f, fieldnames=FIELDS)
        wtr.writeheader()
        wtr.writerows(rows)

    # ── console: the table + the working ──────────────────────────────────────
    print(f"RoI wage curves (NIRF + PLFS + AISHE) → {OUT.name}\n")
    print(f'{"Tier":<46} {"grads":>8} {"emp%":>6} '
          f'{"early":>7} {"mid":>7} {"senior":>7}  selectivity')
    print("-" * 104)
    short = {B_IIT: "IIT", B_NIT: "NIT/IIIT", B_MBBS: "Govt MBBS/BDS",
             B_TOPENG: "Top-200 NIRF Eng (non-IIT/NIT)", B_OTHER: "All other STEM grads"}
    for r in rows:
        g = r["annual_grads"]
        sel = (f'1 in {stem_ug / g:>5.0f} STEM grads'
               if r["bucket"] != B_OTHER else "baseline (the rest)")
        print(f'{short[r["bucket"]]:<46} {g:>8,} {r["employment_rate_pct"]:>5.1f}% '
              f'₹{r["avg_pay_25_29_lakh"]:>5.1f}L ₹{r["avg_pay_30_34_lakh"]:>4.1f}L '
              f'₹{r["avg_pay_35_40_lakh"]:>4.1f}L  {sel}')

    print("\nWorking:")
    print(f'  AISHE 2024-25 universe: STEM UG = {stem_ug:,} ; all UG = {all_ug:,} '
          f'({100*stem_ug/all_ug:.1f}% STEM)')
    print(f'  PLFS growth (×early):   Engineering x{eng_gmid:.2f}/x{eng_gsen:.2f} ; '
          f'Medical x{med_gmid:.2f}/x{med_gsen:.2f}')
    print(f'  "Other STEM" anchor:    PLFS non-technical grad+PG → '
          f'{other_emp:.1f}% in regular work, early ₹{other_early:.1f}L')
    print("\nSelectivity (1 in N), for slide E3:")
    elite = sum(r["annual_grads"] for r in rows if r["bucket"] in (B_IIT, B_NIT))
    print(f'  IIT only         : 1 in {stem_ug/rows[0]["annual_grads"]:.0f} STEM grads '
          f'(1 in {all_ug/rows[0]["annual_grads"]:.0f} of all UG grads)')
    print(f'  IIT + NIT/IIIT   : 1 in {stem_ug/elite:.0f} STEM grads '
          f'(1 in {all_ug/elite:.0f} of all UG grads)')


if __name__ == "__main__":
    main()
