"""
FULL wage curve — every tier of every discipline, top to tail, in one long table.

Each discipline is decomposed into its NIRF-ranked elite tiers (where NIRF
exists) plus the non-NIRF residual ("Others"), sized as AISHE total − ranked
and priced off the PLFS population anchor (back-solved so the grad-weighted
average reconciles to PLFS). Medical is special: its tiers are govt vs private
MBBS+BDS (from NMC/College DB seats), priced by PLFS occupation wages (doctor /
dentist / nurse), since doctor pay doesn't follow a campus-placement model.

Layout (top to tail):
  Engineering : IIT · IIIT · NIT · Top Colleges (rest of top-200 NIRF) · Others (non-NIRF)
  Medical     : Govt Medical (MBBS+BDS) · Pvt Medical (MBBS+BDS) · Others (AYUSH/Nursing/allied)
  Agriculture : NIRF ranked · Others (non-NIRF)
  Law         : NIRF ranked · Others (non-NIRF)
  Others      : all non-NIRF general disciplines (Arts/Commerce/Science/IT/Mgmt/…)

Inputs: NIRF (BQ), AISHE outturn (parquet), JoSAA seats + govt medical seats
(CSVs here), PLFS young-cohort anchors (constants below, from
../plfs/analyses/wage_by_discipline.py and PLFS NCO-occupation cuts).

Output: wage_curves/wage_curve_full.csv      Run: python3 wage_curves/build_full_curve.py
"""

import csv as csvmod
import io
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
AISHE = ROOT.parent / "aishe" / "clean" / "outturn.parquet"
ENG_SQL = ROOT / "nirf_engineering_tiers.sql"
SEATS_CSV = ROOT / "josaa_2022_seats.csv"
MED_CSV = ROOT / "govt_medical_seats.csv"
OUT = ROOT / "wage_curve_full.csv"

COMPLETION = 0.93                  # UG seats → graduates
# PLFS ANNUAL wage anchors, ₹/yr
A_ENG, A_GEN = 360_000, 180_000                # degree bucket (Eng 22-28; general catch-all)
A_LAW, A_AGRI = 300_000, 300_000               # occupation blended salaried+self (NCO 261; NCO 131+213)
W_MBBS, W_BDS, W_NURS = 540_000, 240_000, 192_000   # occupation (NCO 221 doctor / 226 dentist / 222 nurse)
# PLFS young-cohort employment rate (WPR), % — the placement-rate anchor per discipline
# (plfs/analyses/wage_by_discipline.py --age-min 22 --age-max 28). NIRF "placement" is a
# campus-offer %, PLFS is observed employment %; mixed first-order, like the wages.
# Law has no PLFS degree bucket → uses the general-graduate WPR (P_GEN).
P_ENG, P_MED, P_AGRI, P_GEN = 55.9, 50.6, 34.3, 38.5


def bq(sql):
    r = subprocess.run(["bq", "query", "--use_legacy_sql=false", "--format=csv"],
                       input=sql, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"bq failed:\n{r.stderr}")
    return list(csvmod.DictReader(io.StringIO(r.stdout)))


def n(x):
    return float(x) if x not in (None, "", "NULL") else None


def nirf_rollup(categories, year):
    cl = ",".join(f'"{c}"' for c in categories)
    rows = bq(f"""
      WITH agg AS (SELECT * FROM `avantifellows.external_data_sources.nirf_fact_aggregate`
                   WHERE ranking_category IN ({cl}) AND ranking_year = {year}),
      grad AS (SELECT *, ROW_NUMBER() OVER (
                 PARTITION BY institute_id, ranking_category, type ORDER BY academic_year DESC) rn
               FROM agg WHERE students_placed IS NOT NULL)
      SELECT COUNT(DISTINCT institute_id) n_inst, ROUND(SUM(graduating_on_time)) grads,
             ROUND(100*SUM(students_placed)/NULLIF(SUM(graduating_on_time),0),1) placement,
             ROUND(SUM(median_salary*students_placed)/NULLIF(SUM(students_placed),0)) wage
      FROM grad WHERE rn = 1""")
    return rows[0]


def eng_tiers():
    rows = bq(ENG_SQL.read_text().replace("@yr", "2022"))
    return {r["tier"]: r for r in rows}


def aishe_ug(disciplines):
    df = pd.read_parquet(AISHE)
    sl = df[(df.aishe_year == "2021-22") & (df.state == "All") & (df.social_category == "All")
            & (df.programme == "All") & (df.gender == "Total") & (df.level == "Under Graduate")
            & (df.discipline.isin(disciplines))]
    return float(sl.out_turn.sum())


def aishe_grand():
    df = pd.read_parquet(AISHE)
    sl = df[(df.aishe_year == "2021-22") & (df.state == "All") & (df.social_category == "All")
            & (df.programme == "All") & (df.gender == "Total") & (df.level == "Under Graduate")
            & (~df.discipline.isin(["All", "All India", "Grand"]))]
    return float(sl.out_turn.sum())


def seats():
    d = {r["tier"]: int(r["ug_seats_2022"]) for r in csvmod.DictReader(SEATS_CSV.open())}
    return d


def med_seats():
    out = {}
    for r in csvmod.DictReader(MED_CSV.open()):
        out[(r["program"], r["segment"])] = int(r["ug_seats"])
    return out


def main():
    rows = []
    grand = aishe_grand()   # all-India UG graduating class, all disciplines

    def add(disc, tier, inst, grads, total, place, wage, src):
        rows.append(dict(discipline=disc, tier=tier, institutes=inst,
                         graduates=round(grads),
                         share_in_disc_pct=round(grads / total * 100, 1),
                         share_all_pct=round(grads / grand * 100, 2),
                         placement_pct=place, median_wage_inr=round(wage) if wage else None,
                         source=src))

    # ---------------- ENGINEERING ----------------
    et, se = eng_tiers(), seats()
    eng_total = aishe_ug(["Engineering & Technology"])
    pubs = {"IIT": "IIT", "IIIT": "IIIT", "NIT": "NIT"}
    ranked_grads, wage_mass, place_mass = 0.0, 0.0, 0.0
    eng_rows = []
    for tier in ["IIT", "IIIT", "NIT"]:
        g = se[tier] * COMPLETION
        w, pl = n(et[tier]["wtd_median_salary"]), n(et[tier]["placement_rate"])
        eng_rows.append((tier, se_count(tier), g, pl, w,
                         f"NIRF 2022 median; grads = JoSAA {se[tier]:,} seats × {COMPLETION:.0%}"))
        ranked_grads += g; wage_mass += g * w; place_mass += g * pl
    # Top Colleges = rest of top-200 NIRF (the Other-NIRF tier, NIRF counts kept)
    tc = et["Other NIRF"]
    g_tc, w_tc, pl_tc = n(tc["graduates"]), n(tc["wtd_median_salary"]), n(tc["placement_rate"])
    eng_rows.append(("Top Colleges (rest of top-200 NIRF)", int(float(tc["n_inst"])), g_tc,
                     pl_tc, w_tc, "NIRF 2022 median + graduating_on_time"))
    ranked_grads += g_tc; wage_mass += g_tc * w_tc; place_mass += g_tc * pl_tc
    # Others (non-NIRF) — back-solve wage AND placement from the PLFS engineering anchors
    g_oth = eng_total - ranked_grads
    w_oth = (A_ENG * eng_total - wage_mass) / g_oth
    p_oth = (P_ENG * eng_total - place_mass) / g_oth
    for tier, inst, g, pl, w, src in eng_rows:
        add("Engineering", tier, inst, g, eng_total, pl, w, src)
    add("Engineering", "Others (non-NIRF)", None, g_oth, eng_total, round(p_oth, 1), w_oth,
        f"PLFS back-solve (Eng degree ₹{A_ENG:,}, WPR {P_ENG}%)")

    # ---------------- MEDICAL ----------------
    ms = med_seats()
    med_total = aishe_ug(["Medical Science", "Paramedical Science"])
    for seg in ["Government", "Private"]:
        mbbs, bds = ms[("MBBS", seg)], ms[("BDS", seg)]
        g = (mbbs + bds) * COMPLETION
        w = (mbbs * W_MBBS + bds * W_BDS) / (mbbs + bds)   # seat-weighted MBBS/BDS blend
        add("Medical", f"{'Govt' if seg=='Government' else 'Pvt'} Medical (MBBS+BDS)",
            None, g, med_total, P_MED, w,
            f"PLFS doctor ₹{W_MBBS:,}/dentist ₹{W_BDS:,}; WPR {P_MED}% (Medicine&Health; doctor occ. higher); "
            f"seats MBBS {mbbs:,}+BDS {bds:,}×{COMPLETION:.0%}")
    g_used = sum((ms[(p, s)] for p in ("MBBS", "BDS") for s in ("Government", "Private"))) * COMPLETION
    add("Medical", "Others (AYUSH/Nursing/allied)", None, med_total - g_used, med_total, P_MED, W_NURS,
        f"PLFS NCO-222 nursing/allied; WPR {P_MED}%; residual of AISHE Medical Science")

    # ---------------- AGRICULTURE ----------------
    ag = nirf_rollup(["Agriculture and Allied Sectors"], 2023)
    ag_total = aishe_ug(["Agriculture", "Veterinary & Animal Sciences", "Fisheries Science"])
    g_ag, w_ag, pl_ag = n(ag["grads"]), n(ag["wage"]), n(ag["placement"])
    add("Agriculture", "NIRF ranked", int(float(ag["n_inst"])), g_ag, ag_total, pl_ag,
        w_ag, "NIRF 2023 median")
    g_ago = ag_total - g_ag
    w_ago = (A_AGRI * ag_total - g_ag * w_ag) / g_ago
    p_ago = (P_AGRI * ag_total - g_ag * pl_ag) / g_ago
    add("Agriculture", "Others (non-NIRF)", None, g_ago, ag_total, round(p_ago, 1), w_ago,
        f"PLFS back-solve (occupation NCO 131+213 ₹{A_AGRI:,}, WPR {P_AGRI}%)")

    # ---------------- LAW ----------------
    la = nirf_rollup(["Law"], 2022)
    la_total = aishe_ug(["Law"])
    g_la, w_la, pl_la = n(la["grads"]), n(la["wage"]), n(la["placement"])
    add("Law", "NIRF ranked", int(float(la["n_inst"])), g_la, la_total, pl_la,
        w_la, "NIRF 2022 median")
    g_lao = la_total - g_la
    w_lao = (A_LAW * la_total - g_la * w_la) / g_lao
    p_lao = (P_GEN * la_total - g_la * pl_la) / g_lao
    add("Law", "Others (non-NIRF)", None, g_lao, la_total, round(p_lao, 1), w_lao,
        f"PLFS back-solve (occupation NCO 261 legal ₹{A_LAW:,}, WPR {P_GEN}%)")

    # ---------------- OTHERS (general non-NIRF) ----------------
    covered = eng_total + med_total + ag_total + la_total
    g_gen = grand - covered
    add("Others (general)", "All non-NIRF disciplines", None, g_gen, g_gen, P_GEN, A_GEN,
        f"PLFS General graduate/PG (wage ₹{A_GEN:,}, WPR {P_GEN}%); Arts/Commerce/Science/IT/Mgmt/…")

    # ---- write + print ----
    cols = ["discipline", "tier", "institutes", "graduates", "share_in_disc_pct",
            "share_all_pct", "placement_pct", "median_wage_inr", "source"]
    with OUT.open("w", newline="") as f:
        w = csvmod.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

    print(f"Wrote {ROOT.name}/{OUT.name}  ({len(rows)} rows)\n")
    print(f'{"Discipline":<16}{"Tier":<35}{"Inst":>5}{"Grads":>10}{"%disc":>6}{"%all":>6}{"Place%":>7}{"₹/yr":>11}')
    print("-" * 102)
    for r in rows:
        print(f'{r["discipline"]:<16}{r["tier"]:<35}'
              f'{(str(r["institutes"]) if r["institutes"] else "—"):>5}'
              f'{r["graduates"]:>10,}{r["share_in_disc_pct"]:>6}{r["share_all_pct"]:>6}'
              f'{(str(r["placement_pct"]) if r["placement_pct"] else "—"):>7}'
              f'{r["median_wage_inr"]:>11,}')


def se_count(tier):
    return {"IIT": 23, "IIIT": 26, "NIT": 31}[tier]


if __name__ == "__main__":
    main()
