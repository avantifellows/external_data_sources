#!/usr/bin/env python3
"""
avanti_estimate.py — the "Avanti Estimate": one wage/employment table per field,
decomposed into NIRF top tiers + a PLFS-anchored residual.

STATUS: this is the FROZEN wage-curve method (replaces the old 5-tier blend in
wage_curves.py). Remaining implementation (not method) steps, see README:
mid/senior age bands · wire into deck/RoI consumers · MBBS-count + 2022→2025 recency.

Method (decomposition that reconciles to PLFS):
  • AISHE graduates = the universe (master count per common field).
  • Carve the NIRF top slices off the front at NIRF wages + placement.
  • PLFS is the field's population average (25-29, "if-working" median). The
    leftover ("Other …") wage is BACKED OUT so the graduate-weighted average of
    (NIRF tops + residual) equals the PLFS field average:
        rest_wage = (PLFS_avg·AISHE_total − Σ NIRF_wageᵢ·gradsᵢ) / (AISHE_total − Σ gradsᵢ)

Engineering is split IIT / NIT / IIIT / Top Engineering / Other, with IIT, NIT,
IIIT scaled to NATIONAL graduate counts (NIRF only covers reporting institutes)
and IIT+NIT+IIIT+Top Engineering pinned to 250,000 graduates. Other ranked
fields (Medical, Law, Other-Technical via Pharmacy) carve their NIRF top at the
NIRF-reported count; the rest of each field is the PLFS residual. Fields with no
NIRF salary (IT & Computer, Science, Commerce, Management, Other) sit wholly on
the PLFS general-degree wage.

Flags (accepted simplifications):
  • NIRF salary = placement *package* of placed students; PLFS = realized median
    of those in regular work. We treat them as comparable — NIRF runs higher, so
    residuals are, if anything, conservative (depressed).
  • PLFS gives a MEDIAN; the back-out is a MEAN identity. Median-as-mean.
  • "If-working" wages throughout; employment/placement shown separately.

Inputs: clean/nirf_tiers.csv, clean/aishe_grads.csv, plfs_baseline.compute().
Output: clean/avanti_estimate.csv
"""
from __future__ import annotations

import csv
from pathlib import Path

import plfs_baseline
import taxonomy

HERE = Path(__file__).resolve()
CLEAN = HERE.parents[1] / "clean"
NIRF_CSV = CLEAN / "nirf_tiers.csv"
AISHE_CSV = CLEAN / "aishe_grads.csv"
OUT = CLEAN / "avanti_estimate.csv"
OUT_DECK = CLEAN / "avanti_estimate_deck.csv"

# ── deck rollup: (field, tier) → the 5 Avanti-deck buckets; rest → "Others" ───
DECK_ORDER = ["IIT", "NIT / IIIT", "Top Engg Colleges",
              "MBBS / BDS — Govt", "MBBS / BDS — Private", "Others"]
DECK_OF = {
    ("Engineering", "IIT"): "IIT",
    ("Engineering", "NIT"): "NIT / IIIT",
    ("Engineering", "IIIT"): "NIT / IIIT",
    ("Engineering", "Top Engineering Colleges"): "Top Engg Colleges",
    ("Medical", "Govt MBBS/BDS"): "MBBS / BDS — Govt",
    ("Medical", "Private MBBS/BDS"): "MBBS / BDS — Private",
}

# ── assumptions not derivable from the three sources (flagged) ────────────────
IIT_NATIONAL_GRADS = 16_000     # ~17.7k B.Tech intake (23 IITs) × ~0.9 completion
NIT_NATIONAL_GRADS = 22_000     # ~24k intake (31 NITs) × ~0.9
IIIT_NATIONAL_GRADS = 8_000     # ~25 IIITs
ENG_TOP_CAP = 250_000           # IIT + NIT + IIIT + Top Engineering = 2.5 lakh

# MBBS/BDS by ownership (NMC/DCI seat matrix, approx graduates/yr). NIRF does not
# tag govt vs private, so these are documented assumptions; doctor early wage =
# govt junior-resident scale (7th CPC ~₹56k/mo ≈ ₹7L), applied to both.
GOVT_MBBS_BDS_GRADS = 60_000    # govt MBBS ~56k + govt BDS ~3.5k
PRIVATE_MBBS_BDS_GRADS = 78_000  # private MBBS ~58k + private BDS ~20k
MBBS_BDS_WAGE = 7.0
GOVT_MED_EMP = 100.0            # compulsory internship + govt service
PRIVATE_MED_EMP = 95.0          # near-universal (professional degree)
AGE_BAND = "25-29"


def _load_csv(p: Path) -> list[dict]:
    with p.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    nirf = {r["tier"]: r for r in _load_csv(NIRF_CSV)}
    nirf_wage = lambda t: float(nirf[t]["grad_wtd_median_salary"]) / 1e5
    nirf_plac = lambda t: float(nirf[t]["placement_rate_pct"]) if nirf[t]["placement_rate_pct"] else None

    # AISHE graduate total per common field (sum discipline rows, skip rollups)
    aishe_field: dict[str, int] = {}
    for r in _load_csv(AISHE_CSV):
        if r["discipline"].startswith("__"):
            continue
        aishe_field[r["field"]] = aishe_field.get(r["field"], 0) + int(r["ug_outturn_2024_25"])

    # PLFS: field-average wage + % in regular work (25-29, Degree)
    plfs = plfs_baseline.compute()

    def plfs_avg(common_field: str) -> float:
        return plfs[(taxonomy.plfs_field(common_field), "Degree", AGE_BAND)]["median_annual_lakh"]

    def plfs_emp(common_field: str) -> float:
        return plfs[(taxonomy.plfs_field(common_field), "Degree", AGE_BAND)]["pct_regular_work"]

    rows: list[dict] = []

    def add(field, tier, grads, wage, emp, wage_basis):
        rows.append({"field": field, "tier": tier, "annual_grads": int(round(grads)),
                     "wage_25_29_lakh": round(wage, 2),
                     "employment_pct": (round(emp, 1) if emp is not None else ""),
                     "wage_basis": wage_basis})

    def residual_wage(field_avg, total, tops):
        """tops = [(grads, wage), …]. Back out the leftover wage."""
        used = sum(g for g, _ in tops)
        spent = sum(g * w for g, w in tops)
        rest_n = total - used
        return (field_avg * total - spent) / rest_n, rest_n

    # ── ENGINEERING (national IIT/NIT/IIIT, 250k cap, residual) ───────────────
    eng_total = aishe_field["Engineering"]
    eng_avg = plfs_avg("Engineering")
    iit_w, nit_w, iiit_w = nirf_wage("IIT"), nirf_wage("NIT"), nirf_wage("IIIT")
    top_eng_n = ENG_TOP_CAP - (IIT_NATIONAL_GRADS + NIT_NATIONAL_GRADS + IIIT_NATIONAL_GRADS)
    top_eng_w = nirf_wage("Other NIRF Top-200 Eng")
    eng_tops = [(IIT_NATIONAL_GRADS, iit_w), (NIT_NATIONAL_GRADS, nit_w),
                (IIIT_NATIONAL_GRADS, iiit_w), (top_eng_n, top_eng_w)]
    eng_rest_w, eng_rest_n = residual_wage(eng_avg, eng_total, eng_tops)

    add("Engineering", "IIT", IIT_NATIONAL_GRADS, iit_w, nirf_plac("IIT"), "NIRF (national count)")
    add("Engineering", "NIT", NIT_NATIONAL_GRADS, nit_w, nirf_plac("NIT"), "NIRF (national count)")
    add("Engineering", "IIIT", IIIT_NATIONAL_GRADS, iiit_w, nirf_plac("IIIT"), "NIRF (national count)")
    add("Engineering", "Top Engineering Colleges", top_eng_n, top_eng_w,
        nirf_plac("Other NIRF Top-200 Eng"), "NIRF Other-Top-200 (to 2.5 lakh)")
    add("Engineering", "Other Engineering Colleges", eng_rest_n, eng_rest_w,
        plfs_emp("Engineering"), "PLFS residual (back-out)")

    # ── MEDICAL — Govt + Private MBBS/BDS at the doctor wage; residual = rest ──
    med_total = aishe_field["Medical"]
    med_avg = plfs_avg("Medical")
    med_tops = [(GOVT_MBBS_BDS_GRADS, MBBS_BDS_WAGE), (PRIVATE_MBBS_BDS_GRADS, MBBS_BDS_WAGE)]
    med_rest_w, med_rest_n = residual_wage(med_avg, med_total, med_tops)
    add("Medical", "Govt MBBS/BDS", GOVT_MBBS_BDS_GRADS, MBBS_BDS_WAGE, GOVT_MED_EMP,
        "Govt JR scale · NMC count (assumed)")
    add("Medical", "Private MBBS/BDS", PRIVATE_MBBS_BDS_GRADS, MBBS_BDS_WAGE, PRIVATE_MED_EMP,
        "Doctor wage · DCI/NMC count (assumed)")
    add("Medical", "Other Medical", med_rest_n, med_rest_w, plfs_emp("Medical"),
        "PLFS residual (back-out)")

    # ── fields with a single NIRF top tier ────────────────────────────────────
    SINGLE_TOP = [
        ("Law", "Top NIRF Law", "Other Law"),
        ("Other Technical", "Top NIRF Pharmacy", "Other (Other Technical)"),
    ]
    for field, top_tier, rest_label in SINGLE_TOP:
        total = aishe_field[field]
        favg = plfs_avg(field)
        top_n = int(float(nirf[top_tier]["annual_grads"]))
        top_w = nirf_wage(top_tier)
        rest_w, rest_n = residual_wage(favg, total, [(top_n, top_w)])
        add(field, top_tier, top_n, top_w, nirf_plac(top_tier), "NIRF (reported count)")
        add(field, rest_label, rest_n, rest_w, plfs_emp(field), "PLFS residual (back-out)")

    # ── fields with no NIRF salary → whole field at PLFS general-degree wage ───
    for field in ["IT & Computer", "Science", "Commerce", "Management", "Other"]:
        total = aishe_field[field]
        add(field, f"All {field}", total, plfs_avg(field), plfs_emp(field),
            "PLFS general-degree (no NIRF)")

    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["field", "tier", "annual_grads",
                                          "wage_25_29_lakh", "employment_pct", "wage_basis"])
        w.writeheader()
        w.writerows(rows)

    # ── console ───────────────────────────────────────────────────────────────
    print("AVANTI ESTIMATE — graduates × wage (25-29, if-working) × employment\n")
    print(f'{"Field":<16} {"Tier":<28} {"grads":>9} {"wage":>7} {"emp%":>6}  basis')
    print("-" * 92)
    cur = None
    for r in rows:
        if cur and cur != r["field"]:
            print()
        emp = f'{r["employment_pct"]}%' if r["employment_pct"] != "" else "—"
        print(f'{(r["field"] if cur != r["field"] else ""):<16} {r["tier"]:<28} '
              f'{r["annual_grads"]:>9,} ₹{r["wage_25_29_lakh"]:>4.1f}L {emp:>6}  {r["wage_basis"]}')
        cur = r["field"]

    # reconciliation: engineering weighted avg should equal PLFS
    eng_rows = [r for r in rows if r["field"] == "Engineering"]
    wavg = sum(r["annual_grads"] * r["wage_25_29_lakh"] for r in eng_rows) / sum(r["annual_grads"] for r in eng_rows)
    print(f'\nReconciliation — Engineering grad-weighted avg = ₹{wavg:.2f}L '
          f'(PLFS engineering = ₹{eng_avg:.2f}L) ✓')
    print(f"Assumptions: IIT {IIT_NATIONAL_GRADS:,} / NIT {NIT_NATIONAL_GRADS:,} / "
          f"IIIT {IIIT_NATIONAL_GRADS:,} national grads; top-eng cap {ENG_TOP_CAP:,}.")
    print(f"→ {OUT.name}")

    # ── deck rollup: club into the 5 Avanti-deck buckets ──────────────────────
    club: dict[str, dict] = {d: {"grads": 0, "wsum": 0.0, "esum": 0.0} for d in DECK_ORDER}
    for r in rows:
        d = DECK_OF.get((r["field"], r["tier"]), "Others")
        g = r["annual_grads"]
        club[d]["grads"] += g
        club[d]["wsum"] += g * r["wage_25_29_lakh"]
        club[d]["esum"] += g * (r["employment_pct"] or 0)

    deck_rows = []
    for d in DECK_ORDER:
        c = club[d]
        if not c["grads"]:
            continue
        deck_rows.append({"deck_tier": d, "annual_grads": c["grads"],
                          "wage_25_29_lakh": round(c["wsum"] / c["grads"], 2),
                          "employment_pct": round(c["esum"] / c["grads"], 1)})

    with OUT_DECK.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["deck_tier", "annual_grads",
                                          "wage_25_29_lakh", "employment_pct"])
        w.writeheader()
        w.writerows(deck_rows)

    print("\nAVANTI DECK ROLLUP — 5 buckets (grad-weighted)\n")
    print(f'{"Deck tier":<20} {"grads":>10} {"wage":>8} {"emp%":>6}')
    print("-" * 48)
    for r in deck_rows:
        print(f'{r["deck_tier"]:<20} {r["annual_grads"]:>10,} '
              f'₹{r["wage_25_29_lakh"]:>5.1f}L {r["employment_pct"]:>5.1f}%')
    print(f"→ {OUT_DECK.name}")


if __name__ == "__main__":
    main()
