"""
Normalize closing-rank round-depth across all states for cross-state comparison.

Problem
-------
Different states publish closing ranks at different round depths:

  - Most official states publish R3 / Final / Last-round cumulative — these
    are the "true" closing ranks (max rank that has gotten any allotment).
  - Some states only have R1 (Assam) or R1+R2 (Chandigarh AIQ).
  - Third-party sources sometimes carry only one round.

Comparing an R1-only closing rank against an R3 cumulative closing rank
is unfair: R1 can be 25-30%+ harder than R3 (for UR mid-tier colleges)
because upgrades and new candidates haven't yet shaken out.

Approach
--------
For each (state, college, category), pick the BEST round we have, then
estimate the equivalent R3 cumulative closing using **tier-stratified
multipliers** derived empirically from the 6 states (MH, TN, TG, UP, AP,
WB) where R1+R2+R3 cumulative is available.

Multipliers persisted to `extracted_data/_round_multipliers_2025.csv`.
Tier boundaries in `extracted_data/_round_tier_bounds_2025.csv`.

Why tier-stratified
-------------------
The biggest empirical finding: TOP-tier seats lock in by R1, so multiplier
≈ 1.00. Mid/lower-tier seats see most movement (1.20-1.30 for UR, 1.05-
1.10 for reserved). Applying a single per-category multiplier would
over-correct top colleges by 25%+ — clearly wrong because AIIMS-tier
seats don't move R1→R3.

Why NOT marks-normalize
-----------------------
NEET paper difficulty varies year to year. A "590-marks closing" in 2024
isn't the same difficulty as a "590-marks closing" in 2025. Rank-based
normalization is anchored to the candidate pool of that year and stays
internally consistent.

Output
------
`extracted_data/national_closing_ranks_normalized_2025.csv` — one row per
(state, college, program, category) with:
  - actual_round, actual_closing_rank
  - estimated_R3_closing_rank (= actual × multiplier; equals actual when
    actual is already R3 / Final / Last cumulative)
  - tier (Top / Mid / Lower / All)
  - multiplier_applied
  - confidence (High / Medium / Low / N/A)
  - is_estimated (True iff multiplier > 1.0)
  - source_quality (official / third-party)

See `extracted_data/METHODOLOGY_round_normalization.md` for the full
methodology write-up.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).parent.parent
OUT = ROOT / "extracted_data"

# ─── Round-depth labels we treat as "already R3-equivalent" ─────────────
R3_EQUIVALENT_LABELS = {
    # cumulative-final markers
    "R3", "R3 Revised", "R3 Final", "R3 broadsheet",
    "Final", "Last", "MopUp", "Mop-Up", "MopUp Round",
    "Stray", "Stray Vacancy", "Special Stray",
    "Phase-II", "Phase-2", "P2", "P3", "Phase 3", "Phase-3",
    "Round3", "Round 3",
    # state-specific cumulative tags
    "R1+R2", "R1+R2+R3", "R1+R3",  # cumulative tags
    "R4",  # Gujarat last main round
    # When `round` is missing on official-state pivots, the underlying
    # state script already aggregated cumulative — treat as R3-equivalent.
    "n/a", "nan", "",
}
R2_LABELS = {"R2", "Round2", "Round 2", "Phase-1", "Phase-I", "P1", "Phase 1"}
R1_LABELS = {"R1", "Round1", "Round 1"}

# ─── Multipliers + tier bounds (loaded from CSV at runtime) ─────────────


def load_multipliers():
    mult = pd.read_csv(OUT / "_round_multipliers_2025.csv")
    bounds = pd.read_csv(OUT / "_round_tier_bounds_2025.csv")
    # Build a {(category, tier): multiplier_row} dict
    by_key = {(r.category, r.tier): r for r in mult.itertuples()}
    bound_rules = {}
    for r in bounds.itertuples():
        bound_rules.setdefault(r.category, []).append((r.tier, r.r1_min, r.r1_max))
    return by_key, bound_rules


def tier_for(category: str, r1_rank: float, bound_rules: dict) -> str | None:
    if category not in bound_rules:
        return None
    for tier, lo, hi in bound_rules[category]:
        if r1_rank >= lo and (pd.isna(hi) or r1_rank <= hi):
            return tier
    return None


def classify_round(round_label) -> str:
    """Return one of: R3_EQUIV / R2 / R1 / UNKNOWN."""
    if round_label is None or pd.isna(round_label):
        return "R3_EQUIV"  # missing round on official pivot = cumulative
    s = str(round_label).strip()
    if s in R3_EQUIVALENT_LABELS:
        return "R3_EQUIV"
    if s in R2_LABELS:
        return "R2"
    if s in R1_LABELS:
        return "R1"
    return "UNKNOWN"


# ─── Per-state pivot readers (col-name normalization) ───────────────────

# Official state pivots use varied column names; map each state's category
# columns to canonical UR / OBC / EWS / SC / ST so we can compute tiers
# and apply multipliers uniformly. Only the canonical 5 are normalized;
# state-specific subcategories (Karnataka 2A/3B, Tamil Nadu BC/MBC, etc.)
# pass through unchanged.

OFFICIAL_CAT_MAP = {
    # canonical → list of column-name aliases observed across pivots
    "UR":  ["UR", "OPEN", "Open", "GM", "GEN", "OC", "General", "OM", "SM"],
    "OBC": ["OBC", "BC", "OBC-NCL", "BCA", "BC-I", "BC-II"],
    "EWS": ["EWS", "EW", "SE"],
    # SC: include Karnataka 'SCG' (SC-General-urban, the headline SC bucket)
    # and Telangana 'SC1' (largest of the 3 regional SC sub-pools — SC2/SC3
    # remain as separate raw rows for inspection but only SC1 maps to
    # canonical for tier-multiplier purposes).
    "SC":  ["SC", "SCG", "SC1"],
    "ST":  ["ST", "ST(P)", "ST(H)", "STG"],
}

# State-pivot configs: (state_code, file_glob, college_col, program_col_or_None,
#                       round_col_or_None, source_quality, default_round_label)
PIVOT_CONFIGS = [
    # OFFICIAL
    ("AP", "AP_closing_ranks_state_govt_2025_pivot.csv", "college", "course", None, "official", "Phase-II"),
    ("AS", "AS_closing_ranks_state_govt_2025_pivot.csv", "college_canon", "program", None, "official", "R1"),
    ("BR", "BR_closing_ranks_state_govt_2025_pivot.csv", "institute", "program", None, "official", "R3 Revised"),
    ("CG", "CG_closing_ranks_state_govt_2025_pivot.csv", "college", "program", None, "official", "R1+R2"),
    ("GJ", "GJ_closing_ranks_state_govt_2025_pivot.csv", "base", "program", None, "official", "R4"),
    ("HP", "HP_closing_ranks_state_govt_2025_pivot.csv", "college", None, None, "official", "R1+R3"),
    ("JH", "JH_closing_ranks_state_govt_2025_pivot.csv", "college_canon", "program", None, "official", "R1+R3"),
    ("JK", "JK_closing_ranks_state_govt_2025_pivot.csv", "institution", "discipline", None, "official", "R3"),
    ("KA", "KA_closing_ranks_state_govt_2025_pivot.csv", "college_clean", "program", None, "official", "R3"),
    ("KL", "KL_closing_ranks_state_govt_2025_pivot.csv", "college", "program", None, "official", "Phase-3"),
    ("MH", "MH_closing_ranks_state_govt_2025_pivot.csv", "college", "program", None, "official", "R1+R2+R3"),
    ("MP", "MP_closing_ranks_state_govt_2025_pivot.csv", "inst_name", "course", None, "official", "R2"),
    ("PB", "PB_closing_ranks_state_govt_2025_pivot.csv", "allotted_college", "allotted_course", None, "official", "R3 Final"),
    ("TG", "TG_closing_ranks_state_govt_2025_pivot.csv", "college", "program", None, "official", "MopUp"),
    ("TN", "TN_closing_ranks_state_govt_2025_pivot_grank.csv", "college", "program", None, "official", "R1+R2+R3+Stray"),
    # UK and UP publish separate M/F pivots — we read the M file as the
    # gender-blind headline (M is the strictly larger pool; closing AIRs
    # are nearly identical across genders since reservation is vertical).
    ("UK", "UK_closing_ranks_state_govt_2025_pivot_M.csv", "allotted_college", "program", None, "official", "R3 broadsheet"),
    ("UP", "UP_closing_ranks_state_govt_2025_pivot_M.csv", "institute", "branch", None, "official", "R1+R2+R3"),
    ("RJ", "RJ_closing_ranks_state_govt_2024_pivot_M.csv", "college", "course", None, "official", "R1+R2 (2024 data)"),
    ("WB", "WB_closing_ranks_state_govt_2025_pivot.csv", "institute", "course", None, "official", "R1+R2"),
    # THIRD-PARTY
    ("AN", "AN_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("AR", "AR_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("CH", "CH_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("DD", "DD_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("DL", "DL_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("GA", "GA_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("HR", "HR_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("ML", "ML_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("MN", "MN_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("MZ", "MZ_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("NL", "NL_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("OD", "OD_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", None, "third-party", "Final"),
    ("PD", "PD_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
    ("TR", "TR_closing_ranks_state_govt_2025_pivot_THIRDPARTY.csv", "college", "program", "round", "third-party", None),
]


def normalize_pivot_to_long(state, fname, college_col, program_col, round_col,
                            source_quality, default_round) -> pd.DataFrame:
    """Read a state pivot, melt to long, return one row per (college, category)
    with closing_rank + round_label. Pick the BEST round if multiple available."""
    path = OUT / fname
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if college_col not in df.columns:
        # try fallbacks
        for alt in ["college_canon", "college_clean", "institute", "inst_name"]:
            if alt in df.columns:
                college_col = alt; break
        else:
            return pd.DataFrame()
    if program_col is None or program_col not in df.columns:
        df["program"] = "MBBS"
        program_col = "program"
    rows = []
    for _, r in df.iterrows():
        college = str(r.get(college_col, "")).strip()
        if not college or college.lower() == "nan":
            continue
        program = str(r.get(program_col, "MBBS")).strip()
        round_label = (str(r.get(round_col, default_round)).strip()
                       if round_col else default_round)
        # find category columns: any column not in the structural set
        struct = {college_col, program_col, "year", "round", "rank_type", "quota",
                  "NOT_OFFICIAL", "course", "type", "code", "mgmt", "discipline",
                  "base", "inst_code", "college_code", "allotted_course"}
        for col in df.columns:
            if col in struct:
                continue
            val = r.get(col)
            if pd.isna(val):
                continue
            try:
                rank = float(val)
            except (ValueError, TypeError):
                continue
            if rank <= 0:
                continue
            # Map to canonical category if possible
            cat_canon = None
            for canon, aliases in OFFICIAL_CAT_MAP.items():
                if col in aliases:
                    cat_canon = canon; break
            rows.append({
                "state": state,
                "college": college,
                "program": program,
                "category_raw": col,
                "category_canonical": cat_canon,
                "actual_round": round_label,
                "actual_closing_rank": rank,
                "source_quality": source_quality,
            })
    return pd.DataFrame(rows)


def main():
    print("Stage 1 — load multipliers + tier bounds...")
    mult_by_key, bound_rules = load_multipliers()
    print(f"  {len(mult_by_key)} (category, tier) cells loaded")

    print("\nStage 2 — read all state pivots and normalize to long...")
    parts = []
    for cfg in PIVOT_CONFIGS:
        long = normalize_pivot_to_long(*cfg)
        if not long.empty:
            print(f"  {cfg[0]:5s}  {len(long):4d} (college, category) rows")
            parts.append(long)
    nat = pd.concat(parts, ignore_index=True)
    print(f"  Total rows: {len(nat)}")

    print("\nStage 3 — pick BEST round per (state, college, category_raw)...")

    def round_priority(r):
        c = classify_round(r)
        return {"R3_EQUIV": 0, "R2": 1, "R1": 2, "UNKNOWN": 3}[c]

    nat["_priority"] = nat["actual_round"].apply(round_priority)
    nat = nat.sort_values(["state", "college", "category_raw", "_priority"])
    nat = nat.drop_duplicates(subset=["state", "college", "category_raw"], keep="first")
    nat = nat.drop(columns=["_priority"])
    print(f"  After dedup to best-round-per-cell: {len(nat)} rows")

    print("\nStage 4 — apply tier-stratified multipliers...")

    def apply_multiplier(row):
        round_class = classify_round(row.actual_round)
        cat = row.category_canonical
        rank = row.actual_closing_rank

        # If already R3-equivalent — no estimation
        if round_class in ("R3_EQUIV", "UNKNOWN"):
            return pd.Series({
                "estimated_R3_closing_rank": rank,
                "tier": None,
                "multiplier_applied": 1.0,
                "confidence": "N/A (already R3 cumulative)" if round_class == "R3_EQUIV"
                              else "Unknown (round label not recognized)",
                "is_estimated": False,
            })

        # If category isn't canonical (e.g. KA "2AG") — can't apply multiplier
        if cat is None:
            return pd.Series({
                "estimated_R3_closing_rank": rank,
                "tier": None,
                "multiplier_applied": 1.0,
                "confidence": "N/A (state-specific category, no multiplier)",
                "is_estimated": False,
            })

        # Determine tier from R1 closing
        tier = tier_for(cat, rank, bound_rules)
        if tier is None or (cat, tier) not in mult_by_key:
            return pd.Series({
                "estimated_R3_closing_rank": rank,
                "tier": tier,
                "multiplier_applied": 1.0,
                "confidence": "N/A (no multiplier match)",
                "is_estimated": False,
            })

        m = mult_by_key[(cat, tier)]
        multiplier = m.multiplier
        # If R2 → apply only the residual R3/R2 component (~1.00 for most)
        if round_class == "R2":
            multiplier = 1.00 if cat != "UR" or tier == "Top" else 1.04
        return pd.Series({
            "estimated_R3_closing_rank": round(rank * multiplier),
            "tier": tier,
            "multiplier_applied": multiplier,
            "confidence": m.confidence,
            "is_estimated": multiplier > 1.0,
        })

    extra = nat.apply(apply_multiplier, axis=1)
    nat = pd.concat([nat.reset_index(drop=True), extra.reset_index(drop=True)], axis=1)

    # Reorder columns
    nat = nat[[
        "state", "college", "program", "category_raw", "category_canonical",
        "actual_round", "actual_closing_rank",
        "tier", "multiplier_applied", "estimated_R3_closing_rank",
        "is_estimated", "confidence", "source_quality",
    ]]
    nat = nat.sort_values(["state", "college", "category_canonical"], na_position="last")
    out_path = OUT / "national_closing_ranks_normalized_2025.csv"
    nat.to_csv(out_path, index=False)

    print(f"\nStage 5 — wrote {len(nat)} normalized rows to {out_path.name}")

    # Summary stats
    print("\n=== Estimation summary ===")
    print(f"  Rows total:      {len(nat)}")
    print(f"  Already R3:      {(~nat.is_estimated).sum()}")
    print(f"  R3 estimated:    {nat.is_estimated.sum()}")
    print(f"  Estimated states: {sorted(nat[nat.is_estimated]['state'].unique())}")
    print("\n  Estimation by category:")
    print(nat[nat.is_estimated].groupby("category_canonical").size().to_string())


if __name__ == "__main__":
    main()
