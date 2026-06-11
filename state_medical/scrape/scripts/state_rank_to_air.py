"""
Convert state ranks to NEET AIR for cross-state comparison.

After deeper inspection of state source PDFs, the actual landscape is:

  AIR-NATIVE (publish NEET AIR directly — no conversion needed):
    AP, AS, BR, CG, MH, MP, PB, RJ, UK, WB     — `air`/`neet_air` cols
    KA, UP, HP, TG                              — header confirmed "All
                                                   India Rank" / "Neet
                                                   Rank" / NEET-UG-2025
                                                   rank (parser may have
                                                   labeled the column
                                                   `state_rank` or
                                                   `rank` but the values
                                                   are AIR)

  STATE-RANK ONLY (need conversion):
    TN  — has GRANK (TN state merit) + TMARK (NEET score). Convert via
          national score-to-AIR ladder.
    JH  — has CML rank (state) + NEET Score in source PDF. Re-parse for
          score, then convert via national ladder.
    KL  — Kerala state merit rank. Conversion built from CEE-Kerala
          merit list PDF (n=46,275 candidates with all 3: state_rank,
          AIR, score).
    JK  — UT rank. Conversion built from JKBOPEE provisional merit list
          (n=5,707 with state_rank + AIR + score).
    GJ  — Two rank scales:
          * General state merit rank (universal) — gen_merit_R5 PDF.
          * Category-specific merit ranks (SC/ST/SE/EW) — separate per-
            category PDFs. Each has cat_rank + AIR + score.

This script consolidates all (state_rank → AIR) and (cat_rank → AIR)
conversion curves and exposes a uniform `air_for(state, category, rank)`
function used by `normalize_round_depth.py`.

Inputs (sources)
----------------
  source/KL/KL_meritlist_2025.pdf
  source/JK/JK_meritlist_2025.pdf
  source/GJ/GJ_general_meritlist_R5.pdf
  source/GJ/GJ_{sc,st,se,ew}_merit_R5.pdf

Plus existing parsed allotment files for AS/UK/RJ/TN/CG/PB/AP/MP (used
to build the national score-to-AIR ladder).

Outputs
-------
  extracted_data/_neet_2025_score_to_air_ladder.csv
  extracted_data/_state_rank_to_air_<STATE>_curve.csv  (per-state lookup)
  extracted_data/_state_rank_to_air_GJ_<CAT>_curve.csv (per-category)
  extracted_data/_state_rank_to_air_summary.csv
  extracted_data/{KL,JK,GJ}_meritlist_state_rank_air.csv (raw parses)
  extracted_data/GJ_meritlist_category_rank_air.csv

See: extracted_data/METHODOLOGY_round_normalization.md § "State rank to
AIR conversion".
"""
from pathlib import Path
import pandas as pd
import numpy as np
import pdfplumber
import re

ROOT = Path(__file__).parent.parent
OUT = ROOT / "extracted_data"
SOURCE = ROOT / "source"


# ─── National score → AIR ladder ────────────────────────────────────────

SCORE_AIR_SOURCES = [
    ("AP", "AP_all_allotments_2025.csv", "score", "neet_rank"),
    ("AS", "AS_all_allotments_2025.csv", "neet_score", "neet_air"),
    ("CG", "CG_all_allotments_2025.csv", "score", "neet_rank"),
    ("MP", "MP_all_allotments_2025.csv", "closing_neet", "closing_air"),
    ("PB", "PB_all_allotments_2025.csv", "neet_marks", "neet_rank"),
]


def build_score_air_ladder() -> pd.DataFrame:
    parts = []
    for state, fname, sc, ar in SCORE_AIR_SOURCES:
        path = OUT / fname
        if not path.exists():
            continue
        df = pd.read_csv(path)
        sub = df[[sc, ar]].dropna().rename(columns={sc: "score", ar: "air"})
        parts.append(sub)
    allp = pd.concat(parts, ignore_index=True)
    allp["score"] = pd.to_numeric(allp["score"], errors="coerce")
    allp["air"] = pd.to_numeric(allp["air"], errors="coerce")
    allp = allp.dropna()
    allp = allp[(allp["score"] > 0) & (allp["score"] <= 720) & (allp["air"] > 0)]
    ladder = (
        allp.groupby("score")["air"]
        .agg(["min", "median", "max", "count"])
        .reset_index()
        .rename(columns={"min": "air_best", "median": "air_median",
                         "max": "air_worst", "count": "n_obs"})
        .sort_values("score", ascending=False)
    )
    ladder["air_at_score_or_above"] = ladder["air_worst"].cummax()
    ladder = ladder.sort_values("score").reset_index(drop=True)
    ladder.to_csv(OUT / "_neet_2025_score_to_air_ladder.csv", index=False)
    print(f"  Score ladder: {len(ladder)} score-points from {len(allp):,} pairs")
    return ladder


def score_to_air(score, ladder):
    if pd.isna(score) or ladder.empty:
        return np.nan
    eligible = ladder[ladder["score"] <= score]
    if not len(eligible):
        return np.nan
    return float(eligible.iloc[-1]["air_at_score_or_above"])


# ─── Merit-list parsers (KL, JK, GJ) ────────────────────────────────────

def parse_KL_meritlist():
    rows = []
    pdf_path = SOURCE / "KL" / "KL_meritlist_2025.pdf"
    if not pdf_path.exists():
        print(f"  KL merit list missing — skipping"); return pd.DataFrame()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) < 5: continue
                    sl = (r[0] or "").strip().rstrip(".")
                    if not sl.isdigit(): continue
                    appl = (r[1] or "").strip()
                    score = (r[2] or "").strip()
                    air = (r[3] or "").strip().replace(",", "")
                    sr = (r[4] or "").strip()
                    if not (score.isdigit() and air.isdigit() and sr.isdigit()): continue
                    rows.append({"state": "KL", "appl_no": appl,
                                 "score": int(score), "air": int(air),
                                 "state_rank": int(sr)})
    return pd.DataFrame(rows)


def parse_JK_meritlist():
    rows = []
    pdf_path = SOURCE / "JK" / "JK_meritlist_2025.pdf"
    if not pdf_path.exists():
        print(f"  JK merit list missing — skipping"); return pd.DataFrame()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) < 11: continue
                    roll = (r[0] or "").strip()
                    if not (roll.isdigit() and len(roll) >= 8): continue
                    air = (r[8] or "").strip().replace(",", "")
                    score = (r[9] or "").strip()
                    ut_rank = (r[10] or "").strip()
                    if not (air.isdigit() and score.isdigit() and ut_rank.isdigit()): continue
                    rows.append({"state": "JK", "roll": roll,
                                 "score": int(score), "air": int(air),
                                 "state_rank": int(ut_rank)})
    return pd.DataFrame(rows)


def parse_GJ_meritlist_general():
    """GJ general merit list — line regex (text-based parse)."""
    rows = []
    pat_no_cat = re.compile(r"^(\d{5})\s+(\d{10})\s+(\d{5})\s+(\d{1,7})\s+(\d{1,3})\s+(\d{1,3}\.\d{1,3})\s")
    pat_with_cat = re.compile(r"^(\d{5})\s+(\d{10})\s+(\d{5})\s+([A-Z]{2,4}-\d{1,5})\s+(\d{1,7})\s+(\d{1,3})\s+(\d{1,3}\.\d{1,3})\s")
    pdf_path = SOURCE / "GJ" / "GJ_general_meritlist_R5.pdf"
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").split("\n"):
                m = pat_with_cat.match(line)
                if m:
                    rows.append({"state": "GJ", "user_id": m.group(1),
                                 "roll": m.group(2), "state_rank": int(m.group(3)),
                                 "cat_rank_str": m.group(4), "air": int(m.group(5)),
                                 "score": int(m.group(6))})
                    continue
                m = pat_no_cat.match(line)
                if m:
                    rows.append({"state": "GJ", "user_id": m.group(1),
                                 "roll": m.group(2), "state_rank": int(m.group(3)),
                                 "cat_rank_str": None, "air": int(m.group(4)),
                                 "score": int(m.group(5))})
    return pd.DataFrame(rows)


def parse_GJ_meritlist_categories():
    """GJ category-specific merit lists — one (cat_rank, AIR) per row per category."""
    pat = re.compile(r"^(\d{5})\s+(\d{10})\s+(\d{5})\s+([A-Z]{2,4}-\d{1,5})\s+(\d{1,7})\s+(\d{1,3})\s+(\d{1,3}\.\d{1,3})\s")
    all_rows = []
    for cat, fname in [("SC", "GJ_sc_merit_R5.pdf"), ("ST", "GJ_st_merit_R5.pdf"),
                        ("SE", "GJ_se_merit_R5.pdf"), ("EW", "GJ_ew_merit_R5.pdf")]:
        pdf_path = SOURCE / "GJ" / fname
        if not pdf_path.exists(): continue
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for line in (page.extract_text() or "").split("\n"):
                    m = pat.match(line)
                    if not m: continue
                    cat_token = m.group(4)
                    if not cat_token.startswith(cat): continue
                    all_rows.append({
                        "state": "GJ", "category": cat,
                        "gen_state_rank": int(m.group(3)),
                        "cat_state_rank": int(cat_token.split("-")[1]),
                        "air": int(m.group(5)), "score": int(m.group(6)),
                    })
    return pd.DataFrame(all_rows)


# ─── Curve builders ────────────────────────────────────────────────────

def collapse_to_curve(df: pd.DataFrame, rank_col: str = "rank",
                      air_col: str = "air", n_buckets: int = 200) -> pd.DataFrame:
    df = df[[rank_col, air_col]].dropna().copy()
    df[rank_col] = df[rank_col].astype(int)
    df[air_col] = df[air_col].astype(int)
    df = df.sort_values(rank_col)
    n_unique = df[rank_col].nunique()
    if n_unique < 5:
        return df.rename(columns={rank_col: "rank", air_col: "air"})
    df["bucket"] = pd.qcut(df[rank_col], q=min(n_buckets, n_unique), duplicates="drop")
    curve = (
        df.groupby("bucket", observed=True)
        .agg(rank=(rank_col, "median"), air=(air_col, "median"), n=(rank_col, "size"))
        .reset_index(drop=True)
    )
    curve["air"] = curve["air"].cummax()
    return curve


def build_curve_AS():
    df = pd.read_csv(OUT / "AS_all_allotments_2025.csv")
    df = df[["state_rank", "neet_air"]].apply(pd.to_numeric, errors="coerce").dropna()
    return df.rename(columns={"state_rank": "rank", "neet_air": "air"})


def build_curve_UK():
    df = pd.read_csv(OUT / "UK_all_allotments_2025.csv")
    df = df[["uk_rank", "neet_air"]].apply(pd.to_numeric, errors="coerce").dropna()
    return df.rename(columns={"uk_rank": "rank", "neet_air": "air"})


def build_curve_RJ():
    df = pd.read_csv(OUT / "RJ_all_allotments_2024.csv")
    df = df[["state_merit", "ai_rank"]].apply(pd.to_numeric, errors="coerce").dropna()
    return df.rename(columns={"state_merit": "rank", "ai_rank": "air"})


def build_curve_TN(ladder):
    df = pd.read_csv(OUT / "TN_all_allotments_2025.csv")
    df = df[["grank", "tmark"]].apply(pd.to_numeric, errors="coerce").dropna()
    df["air"] = df["tmark"].apply(lambda s: score_to_air(s, ladder))
    return df[["grank", "air"]].dropna().rename(columns={"grank": "rank"})


def build_curve_JH(ladder):
    """JH allotment file has cml_rank + neet_score. Convert score → AIR via
    national ladder, then build (cml_rank → AIR) curve."""
    df = pd.read_csv(OUT / "JH_all_allotments_2025.csv")
    df = df[["cml_rank", "neet_score"]].apply(pd.to_numeric, errors="coerce").dropna()
    df["air"] = df["neet_score"].apply(lambda s: score_to_air(s, ladder))
    return df[["cml_rank", "air"]].dropna().rename(columns={"cml_rank": "rank"})


# ─── Main orchestrator ────────────────────────────────────────────────

def main():
    print("Stage 1 — build NEET 2025 score → AIR national ladder...")
    ladder = build_score_air_ladder()

    print("\nStage 2 — parse the 3 state merit lists (KL, JK, GJ)...")
    print("  Parsing KL merit list (~520 pages, ~60s)...")
    kl = parse_KL_meritlist()
    if not kl.empty:
        kl.to_csv(OUT / "KL_meritlist_state_rank_air.csv", index=False)
        print(f"    KL: {len(kl):,} (state_rank, AIR) pairs")
    print("  Parsing JK merit list (~290 pages, ~17s)...")
    jk = parse_JK_meritlist()
    if not jk.empty:
        jk.to_csv(OUT / "JK_meritlist_state_rank_air.csv", index=False)
        print(f"    JK: {len(jk):,} pairs")
    print("  Parsing GJ general merit list...")
    gj_gen = parse_GJ_meritlist_general()
    if not gj_gen.empty:
        gj_gen.to_csv(OUT / "GJ_meritlist_state_rank_air.csv", index=False)
        print(f"    GJ general: {len(gj_gen):,} pairs")
    print("  Parsing GJ category merit lists (SC/ST/SE/EW)...")
    gj_cat = parse_GJ_meritlist_categories()
    if not gj_cat.empty:
        gj_cat.to_csv(OUT / "GJ_meritlist_category_rank_air.csv", index=False)
        print(f"    GJ category: {len(gj_cat):,} pairs")

    print("\nStage 3 — build per-state conversion curves...")
    summary = []
    for state, builder, method, n_label in [
        ("AS", build_curve_AS, "direct (allotments)", "AS_all_allotments"),
        ("UK", build_curve_UK, "direct (allotments)", "UK_all_allotments"),
        ("RJ", build_curve_RJ, "direct (allotments)", "RJ_all_allotments_2024"),
        ("TN", lambda: build_curve_TN(ladder), "score-bridge", "TN_all_allotments via score ladder"),
        ("JH", lambda: build_curve_JH(ladder), "score-bridge", "JH_all_allotments via score ladder"),
        ("KL", lambda: kl[["state_rank", "air"]].rename(columns={"state_rank": "rank"}),
         "direct (merit list)", "KL_meritlist_2025"),
        ("JK", lambda: jk[["state_rank", "air"]].rename(columns={"state_rank": "rank"}),
         "direct (merit list)", "JK_meritlist_2025"),
        ("GJ_general", lambda: gj_gen[["state_rank", "air"]].rename(columns={"state_rank": "rank"}),
         "direct (merit list)", "GJ_general_meritlist_R5"),
    ]:
        raw = builder()
        if raw.empty: continue
        curve = collapse_to_curve(raw)
        curve.to_csv(OUT / f"_state_rank_to_air_{state}_curve.csv", index=False)
        summary.append({
            "state": state, "method": method, "n_pairs": len(raw),
            "rank_min": int(raw["rank"].min()), "rank_max": int(raw["rank"].max()),
            "air_min": int(raw["air"].min()), "air_max": int(raw["air"].max()),
            "n_curve_points": len(curve), "source": n_label,
        })
        print(f"  {state:12s} {len(raw):>6,} pairs → {len(curve)} curve pts  ({method})")

    # GJ per-category curves (SC/ST/SE/EW)
    if not gj_cat.empty:
        for cat, sub in gj_cat.groupby("category"):
            raw = sub[["cat_state_rank", "air"]].rename(columns={"cat_state_rank": "rank"})
            curve = collapse_to_curve(raw)
            label = f"GJ_{cat}"
            curve.to_csv(OUT / f"_state_rank_to_air_{label}_curve.csv", index=False)
            summary.append({
                "state": label, "method": "direct (per-category merit)", "n_pairs": len(raw),
                "rank_min": int(raw["rank"].min()), "rank_max": int(raw["rank"].max()),
                "air_min": int(raw["air"].min()), "air_max": int(raw["air"].max()),
                "n_curve_points": len(curve),
                "source": f"GJ_{cat.lower()}_merit_R5",
            })
            print(f"  {label:12s} {len(raw):>6,} pairs → {len(curve)} curve pts (GJ {cat} category-merit)")

    summ = pd.DataFrame(summary)
    summ.to_csv(OUT / "_state_rank_to_air_summary.csv", index=False)
    print(f"\nSaved summary: {len(summ)} curves total")
    print(summ.to_string(index=False))


if __name__ == "__main__":
    main()
