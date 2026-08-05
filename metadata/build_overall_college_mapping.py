"""
Build external_data_sources.bridge_college_mapping

AISHE is the spine (~72k institutions). Three source systems are cross-walked:

  NIRF — matched via three strategies in priority order:
    s1_id_extract        Modern NIRF id (IR-[cat]-[C/U]-[num]) embeds the AISHE
                         code in its last two segments; extract directly.
    s2_name_state_bridge Old-format NIRF id: find the same institute's modern id
                         via normalised name+state, then inherit its AISHE code.
    s3_name_state_direct Old-format NIRF id with no S2 bridge: match directly
                         against the AISHE union on normalised name+state.

  JoSAA — matched via four strategies in priority order:
    s1_name_exact        Normalised institute name matches exactly against AISHE.
    s2_name_location     Short-name + location hint in AISHE name.
    s3a_paren_free       Strip parenthetical abbreviations like (BHU), then exact.
    s3b_ratio            SequenceMatcher ratio ≥ 0.88 against AISHE universities.

  KCET — matched within Karnataka AISHE only, three strategies:
    s1_name_exact        Normalised full name matches exactly against AISHE.
    s2_name_short        Normalised short name (strip address suffix from KCET,
                         location suffix from AISHE) matches exactly.
    s3_ratio             SequenceMatcher ratio ≥ 0.85 on short names against
                         Karnataka AISHE — catches "B M S" vs "BMS" variants
                         (dot-expansion) and minor spelling differences.

  NMC — MBBS medical colleges, matched within same state, four strategies:
    s1_name_exact        Normalised full name + state matches exactly against AISHE.
    s2_name_short        Normalised short name + state matches exactly.
    s3_ratio             SequenceMatcher ratio ≥ 0.85 on short names within
                         the same state — catches spelling variants in medical
                         college names.
    s4_spaceless_exact   Split on first comma, remove ALL non-alphanumeric chars
                         (including spaces), then exact match within state —
                         catches dot/space variants like "S.N." vs "S N" vs "SN".

Output schema:
  aishe_code            STRING        -- spine, always populated
  aishe_name            STRING        -- institution name as stored in AISHE (for reference)
  nirf_institute_ids    ARRAY<STRING> -- all NIRF ids across all ranking categories;
                                         empty if never ranked.
                                         Join: ON r.institute_id IN UNNEST(b.nirf_institute_ids)
                                               AND r.ranking_category = 'Engineering'
  nirf_match_method     STRING        -- best NIRF match strategy; NULL if no match
  josaa_institute_name  STRING        -- matched JoSAA institute name (join key to
                                         josaa_fact_cutoffs.institute); NULL if not JoSAA
  josaa_match_method    STRING        -- JoSAA match strategy; NULL if no match
                                         s1_name_exact   exact normalised name
                                         s2_name_location short-name + location hint
                                         s3a_paren_free  strip abbreviations like (BHU)
                                         s3b_ratio       SequenceMatcher ratio ≥ 0.88
  kcet_college_codes    ARRAY<STRING> -- all KEA college codes for this institution;
                                         empty if not a KCET participant. The same
                                         physical college can have two codes — one for
                                         its Government-Aided quota seats and one for
                                         its Private Unaided quota seats.
                                         Join: ON k.college_code IN UNNEST(b.kcet_college_codes)
  kcet_match_method     STRING        -- best KCET match strategy; NULL if no match
                                         s1_name_exact   exact normalised full name
                                         s2_name_short   exact normalised short name
                                         s3_ratio        SequenceMatcher ratio ≥ 0.85
  nmc_college_name      STRING        -- original NMC college name (as printed in the NMC
                                         PDF); NULL if not an NMC MBBS college.
                                         Non-NULL = this AISHE institution is NMC-listed.
  nmc_match_method      STRING        -- best NMC match strategy; NULL if no match
                                         s1_name_exact       exact normalised full name + state
                                         s2_name_short       exact normalised short name + state
                                         s3_ratio            SequenceMatcher ratio ≥ 0.85 within state
                                         s4_spaceless_exact  spaceless (comma-split + strip all non-alnum) exact match

Usage:
  python3 build_bridge_college_mapping.py [--dry-run]
"""
from __future__ import annotations

import argparse
import difflib
import re

import pandas as pd

BQ_PROJECT  = "avantifellows"
BQ_DATASET  = "external_data_sources"
BQ_LOCATION = "asia-south1"
OUT_TABLE   = f"{BQ_PROJECT}.{BQ_DATASET}.overall_college_mapping"

AISHE_TABLES = [
    ("aishe_dim_colleges",                            "name",           "state"),
    ("aishe_dim_universities",                        "name",           "state"),
    ("aishe_dim_standalone_institutions",             "name",           "state"),
    ("aishe_dim_research_institutions",               "institute_name", "state_name"),
    ("aishe_dim_pm_vidyalaxmi_eligible_institutions", "institute_name", "state_name"),
]

NIRF_TABLES = [
    "nirf_fact_rankings",
    "nirf_fact_aggregate",
    "nirf_fact_master",
    "nirf_fact_strength",
]

KCET_TABLE = "kcet_fact_cutoffs"
NMC_TABLE  = "nmc_fact_mbbs_seats"

NIRF_METHOD_PRIORITY = {"s1_id_extract": 0, "s2_name_state_bridge": 1, "s3_name_state_direct": 2}
KCET_METHOD_PRIORITY = {"s1_name_exact": 0, "s2_name_short": 1, "s3_ratio": 2}
NMC_METHOD_PRIORITY  = {"s1_name_exact": 0, "s2_name_short": 1, "s3_ratio": 2, "s4_spaceless_exact": 3}

# NMC source is PDF-parsed and has two state-name corruption patterns:
# 1. Truncated/split by the PDF extractor (e.g. "Maharasht ra", "Uttarakhan d")
# 2. Old official names now changed (Orissa → Odisha, Pondicherry → Puducherry)
# Apply after _norm so keys are already uppercased and stripped.
# State-name matching. The NMC PDF prints states in several forms, and _norm strips
# "&" to a space — so "JAMMU  KASHMIR" never equalled AISHE's "JAMMU AND KASHMIR"
# and all 12 J&K colleges were state-scoped out of every match. _norm_state also
# drops the connector word so all three spellings collapse to one key.
#
# The truncation entries below ("MAHARASHT RA", "UTTAR PRADE" ...) are a PDF
# column-bleed artefact, now repaired at the parse step in nmc/scripts/clean_nmc.py.
# Kept as a one-release safety net for tables loaded before that fix; safe to delete
# once nmc_fact_mbbs_seats has been reloaded.
_NMC_STATE_FIXUP: dict[str, str] = {
    "MAHARASHT RA":     "MAHARASHTRA",
    "MAHARASHTR":       "MAHARASHTRA",
    "MADHYA PRA DESH":  "MADHYA PRADESH",
    "MADHYA PRA":       "MADHYA PRADESH",
    "UTTAR PRADE SH":   "UTTAR PRADESH",
    "UTTAR PRADE":      "UTTAR PRADESH",
    "UTTARAKHAN D":     "UTTARAKHAND",
    "UTTARAKHAN":       "UTTARAKHAND",
    "WEST BENGA L":     "WEST BENGAL",
    "WEST BENGA":       "WEST BENGAL",
    "PONDICHERR Y":     "PUDUCHERRY",
    "PONDICHERRY":      "PUDUCHERRY",
    "ORISSA":           "ODISHA",
    "CHATTISGARH":      "CHHATTISGARH",
}


def _norm(s: pd.Series) -> pd.Series:
    return (
        s.fillna("").str.upper().str.strip()
        .str.replace(r"[^A-Z0-9 ]", "", regex=True)
        .str.replace(r" {2,}", " ", regex=True)
    )


def _norm_state(s: pd.Series) -> pd.Series:
    """Normalise a state name for comparison: drop the AND/& connector so
    "Jammu & Kashmir", "Jammu and Kashmir" and "JAMMU KASHMIR" all match."""
    return (
        _norm(s)
        .str.replace(r"\bAND\b", " ", regex=True)
        .str.replace(r" {2,}", " ", regex=True)
        .str.strip()
        .replace(_NMC_STATE_FIXUP)
    )


def _short_norm(s: pd.Series) -> pd.Series:
    """Strip location suffix (after first comma or open-paren) then normalise."""
    return _norm(s.str.replace(r"[,(].*", "", regex=True))


def _spaceless(s: pd.Series) -> pd.Series:
    """Split on first comma, then remove ALL non-alphanumeric chars (including spaces), uppercase.
    Handles dot/space abbreviation variants: 'S.N.' = 'S N' = 'SN'."""
    return s.str.split(",").str[0].str.upper().str.replace(r"[^A-Z0-9]", "", regex=True)


# ── AISHE ─────────────────────────────────────────────────────────────────────

def _read_aishe(client) -> pd.DataFrame:
    parts = []
    for table, name_col, state_col in AISHE_TABLES:
        sql = f"""
            SELECT aishe_code, {name_col} AS college_name, {state_col} AS college_state
            FROM `{BQ_PROJECT}.{BQ_DATASET}.{table}`
            WHERE aishe_code IS NOT NULL
        """
        parts.append(client.query(sql).to_dataframe())
    df = pd.concat(parts, ignore_index=True).drop_duplicates(subset="aishe_code", keep="first")
    df["norm_name"]       = _norm(df["college_name"])
    df["norm_state"]      = _norm_state(df["college_state"])
    df["short_norm_name"] = _short_norm(df["college_name"])
    df["spaceless_name"]  = _spaceless(df["college_name"])
    return df


# ── NIRF ──────────────────────────────────────────────────────────────────────

def _read_nirf(client) -> pd.DataFrame:
    union = "\n    UNION ALL\n    ".join(
        f"SELECT institute_id, institute_name, state FROM `{BQ_PROJECT}.{BQ_DATASET}.{t}`"
        for t in NIRF_TABLES
    )
    sql = f"""
        SELECT institute_id,
               ANY_VALUE(institute_name) AS institute_name,
               ANY_VALUE(state)          AS state
        FROM ({union})
        WHERE institute_id IS NOT NULL
        GROUP BY institute_id
    """
    df = client.query(sql).to_dataframe()
    df["norm_name"]  = _norm(df["institute_name"])
    df["norm_state"] = _norm_state(df["state"])
    df["is_modern"]  = df["institute_id"].str.match(r"^IR-[A-Z]+-[CU]-\d+$", na=False)

    def _extract(iid: str) -> str | None:
        m = re.search(r"-([CU]-\d+)$", iid)
        return m.group(1) if m else None

    df["s1_code"] = df["institute_id"].apply(_extract)
    return df


def _match_nirf(aishe: pd.DataFrame, nirf: pd.DataFrame) -> pd.DataFrame:
    """Returns per-AISHE-code nirf_institute_ids list + best match method."""
    # S1: modern ids with extractable AISHE code
    s1 = (
        nirf[nirf["is_modern"] & nirf["s1_code"].notna()]
        [["institute_id", "s1_code"]]
        .rename(columns={"s1_code": "aishe_code"})
        .assign(nirf_match_method="s1_id_extract")
    )

    # S2: old ids → bridge via modern id sharing same norm_name+norm_state
    modern = nirf[nirf["is_modern"] & nirf["s1_code"].notna()][
        ["norm_name", "norm_state", "s1_code"]
    ].rename(columns={"s1_code": "bridged_code"})
    old = nirf[~nirf["is_modern"]][["institute_id", "norm_name", "norm_state"]]
    s2_raw = old.merge(modern, on=["norm_name", "norm_state"], how="inner").sort_values("bridged_code")
    s2 = (
        s2_raw.drop_duplicates(subset="institute_id", keep="first")
        [["institute_id", "bridged_code"]]
        .rename(columns={"bridged_code": "aishe_code"})
        .assign(nirf_match_method="s2_name_state_bridge")
    )

    # S3: remaining old ids → direct name+state match against AISHE
    s2_ids = set(s2["institute_id"])
    old_unmatched = old[~old["institute_id"].isin(s2_ids)]
    aishe_norm = aishe[["aishe_code", "norm_name", "norm_state"]]
    s3_raw = old_unmatched.merge(aishe_norm, on=["norm_name", "norm_state"], how="inner").sort_values("aishe_code")
    s3 = (
        s3_raw.drop_duplicates(subset="institute_id", keep="first")
        [["institute_id", "aishe_code"]]
        .assign(nirf_match_method="s3_name_state_direct")
    )

    matched = pd.concat([s1, s2, s3], ignore_index=True)
    print(
        f"  NIRF S1={len(s1):,}  S2={len(s2):,}  S3={len(s3):,}  "
        f"unmatched={len(nirf) - len(matched):,}  total={len(nirf):,}"
    )

    def _agg(grp: pd.DataFrame) -> pd.Series:
        ids  = sorted(grp["institute_id"].tolist())
        best = grp["nirf_match_method"].map(NIRF_METHOD_PRIORITY).idxmin()
        return pd.Series({"nirf_institute_ids": ids,
                          "nirf_match_method":  grp.loc[best, "nirf_match_method"]})

    nirf_per_aishe = matched.groupby("aishe_code", sort=False).apply(_agg).reset_index()
    return nirf_per_aishe


# ── JoSAA ─────────────────────────────────────────────────────────────────────

def _read_josaa(client) -> pd.DataFrame:
    sql = f"""
        SELECT DISTINCT institute
        FROM `{BQ_PROJECT}.{BQ_DATASET}.josaa_fact_cutoffs`
        WHERE institute IS NOT NULL
    """
    df = client.query(sql).to_dataframe()
    df["norm_name"]       = _norm(df["institute"])
    df["short_norm_name"] = _short_norm(df["institute"])
    return df


def _paren_free_norm(s: pd.Series) -> pd.Series:
    """Strip parenthetical content then normalise."""
    return _norm(s.str.replace(r"\([^)]*\)", "", regex=True))


def _match_josaa(aishe: pd.DataFrame, josaa: pd.DataFrame) -> pd.DataFrame:
    """
    Returns DataFrame: aishe_code → josaa_institute_name + josaa_match_method.

    S1:  Exact normalised name match.
    S2:  Short-name + location-hint: strip location suffix (after first comma/paren),
         require AISHE norm_name to contain the extracted location hint — prevents
         multiple NITs/IITs collapsing to the same AISHE code.
    S3a: Paren-free exact: strip parenthetical abbreviations like "(BHU)", "(ISM)"
         from both sides, then re-apply exact match.
    S3b: SequenceMatcher ratio ≥ 0.88 against AISHE universities only (U-* codes) —
         catches spelling variants (Tiruchirappalli/Tiruchirapalli, Malaviya/Malviya).
         Restricted to universities because all JoSAA participants are
         centrally-funded institutions, and the small candidate pool (~1k rows)
         keeps comparisons fast and false-positive risk low.
    """
    aishe_norm_dedup  = aishe.drop_duplicates(subset="norm_name", keep="first")
    aishe_short_dedup = aishe.drop_duplicates(subset="short_norm_name", keep="first")
    aishe_short_dedup = aishe_short_dedup[aishe_short_dedup["short_norm_name"].str.len() > 5]

    # S1: exact normalised name
    s1 = (
        josaa.merge(aishe_norm_dedup[["aishe_code", "norm_name"]], on="norm_name", how="inner")
        .drop_duplicates(subset="institute", keep="first")
        [["institute", "aishe_code"]]
        .assign(josaa_match_method="s1_name_exact")
    )

    # S2: short-name + location-hint
    s1_matched = set(s1["institute"])
    josaa_unmatched = josaa[~josaa["institute"].isin(s1_matched)].copy()
    josaa_unmatched["location_hint"] = _norm(
        josaa_unmatched["institute"].str.replace(r"^[^,(]+[,(]\s*", "", regex=True)
    )
    josaa_s2_candidates = josaa_unmatched[josaa_unmatched["location_hint"].str.len() > 0]
    aishe_s2 = aishe_short_dedup[["aishe_code", "short_norm_name", "norm_name"]].rename(
        columns={"norm_name": "aishe_norm_name"}
    )
    s2_raw = josaa_s2_candidates.merge(aishe_s2, on="short_norm_name", how="inner")
    s2_raw = s2_raw[s2_raw.apply(lambda r: r["location_hint"] in r["aishe_norm_name"], axis=1)]
    s2 = (
        s2_raw.drop_duplicates(subset="institute", keep="first")
        [["institute", "aishe_code"]]
        .assign(josaa_match_method="s2_name_location")
    )

    # S3a: paren-free exact — handles "(BHU)", "(ISM)" abbreviation expansions
    s2_matched = s1_matched | set(s2["institute"])
    josaa_unmatched2 = josaa[~josaa["institute"].isin(s2_matched)].copy()
    josaa_unmatched2["pf_norm"] = _paren_free_norm(josaa_unmatched2["institute"])

    aishe_pf = aishe.copy()
    aishe_pf["pf_norm"] = _paren_free_norm(aishe["college_name"])
    aishe_pf_dedup = (
        aishe_pf[aishe_pf["pf_norm"].str.len() > 3]
        .drop_duplicates(subset="pf_norm", keep="first")
    )
    s3a = (
        josaa_unmatched2.merge(
            aishe_pf_dedup[["aishe_code", "pf_norm"]], on="pf_norm", how="inner"
        )
        .drop_duplicates(subset="institute", keep="first")
        [["institute", "aishe_code"]]
        .assign(josaa_match_method="s3a_paren_free")
    )

    # S3b: ratio match against AISHE universities only (U-* codes, ~1k rows)
    s3a_matched = s2_matched | set(s3a["institute"])
    josaa_unmatched3 = josaa[~josaa["institute"].isin(s3a_matched)]
    aishe_unis = aishe[aishe["aishe_code"].str.startswith("U-")].reset_index(drop=True)

    s3b_rows = []
    for _, row in josaa_unmatched3.iterrows():
        full = row["norm_name"]
        ratios = [
            difflib.SequenceMatcher(None, full, an).ratio()
            for an in aishe_unis["norm_name"]
        ]
        best_idx   = max(range(len(ratios)), key=lambda i: ratios[i])
        best_ratio = ratios[best_idx]
        if best_ratio < 0.88:
            continue
        other_max = max((r for i, r in enumerate(ratios) if i != best_idx), default=0)
        if other_max >= best_ratio - 0.05:
            continue  # ambiguous
        s3b_rows.append({
            "institute":          row["institute"],
            "aishe_code":         aishe_unis.loc[best_idx, "aishe_code"],
            "josaa_match_method": "s3b_ratio",
            "_ratio":             round(best_ratio, 3),
        })

    s3b = pd.DataFrame(s3b_rows) if s3b_rows else pd.DataFrame(
        columns=["institute", "aishe_code", "josaa_match_method", "_ratio"]
    )

    matched = pd.concat([s1, s2, s3a, s3b[["institute", "aishe_code", "josaa_match_method"]]], ignore_index=True)
    dupes = matched[matched.duplicated(subset="aishe_code", keep=False)]
    if not dupes.empty:
        print(f"  ⚠ {dupes['aishe_code'].nunique()} aishe_code(s) claimed by multiple JoSAA institutes — keeping first:")
        for code, grp in dupes.groupby("aishe_code"):
            print(f"    {code}: {list(grp['institute'])}")
        matched = matched.drop_duplicates(subset="aishe_code", keep="first")
    n_unmatched = len(josaa) - len(matched)
    print(
        f"  JoSAA S1={len(s1):,}  S2={len(s2):,}  S3a={len(s3a):,}  S3b={len(s3b):,}  "
        f"unmatched={n_unmatched:,}  total={len(josaa):,}"
    )
    if len(s3a) > 0:
        print("  S3a (paren-free) matches:")
        for _, r in s3a.iterrows():
            print(f"    {r['institute']}")
    if not s3b.empty:
        print("  S3b (ratio) matches:")
        for _, r in s3b.iterrows():
            print(f"    {r['institute']}  (ratio={r['_ratio']})")
    if n_unmatched > 0:
        unmatched_names = set(josaa["institute"]) - set(matched["institute"])
        print("  Still unmatched:")
        for name in sorted(unmatched_names):
            print(f"    {name}")

    return matched.rename(columns={"institute": "josaa_institute_name"})


# ── KCET ──────────────────────────────────────────────────────────────────────

def _read_kcet(client) -> pd.DataFrame:
    sql = f"""
        SELECT DISTINCT college_code, college_name
        FROM `{BQ_PROJECT}.{BQ_DATASET}.{KCET_TABLE}`
        WHERE college_code IS NOT NULL
    """
    df = client.query(sql).to_dataframe()
    df["norm_name"]       = _norm(df["college_name"])
    # KCET names embed full addresses after the college name (e.g.
    # "BMS College of Engineering, Basavanagudi, Bangalore POST BOX...").
    # short_norm_name strips everything after the first comma or paren.
    df["short_norm_name"] = _short_norm(df["college_name"])
    return df


def _match_kcet(aishe: pd.DataFrame, kcet: pd.DataFrame) -> pd.DataFrame:
    """
    Returns DataFrame: aishe_code → kcet_college_code + kcet_match_method.

    Restricted to Karnataka AISHE institutions only — KCET is a state exam.

    S1: Exact normalised full name match (covers edge cases with no address suffix).
    S2: Exact normalised short name match — strips address suffix from KCET
        and location suffix from AISHE, so "BMS College of Engineering,
        Basavanagudi..." vs "BMS College of Engineering, Bangalore" both
        reduce to "BMS COLLEGE OF ENGINEERING".
    S3: SequenceMatcher ratio ≥ 0.85 on short names within Karnataka AISHE —
        catches dot-expansion variants ("B M S" vs "BMS" from "B.M.S.") and
        minor spelling differences common in state-level naming.
        Ambiguity guard: second-best must be > 0.06 below best.
    """
    aishe_ka = aishe[aishe["norm_state"] == "KARNATAKA"].reset_index(drop=True)

    # S1: exact full normalised name
    aishe_ka_norm_dedup = aishe_ka.drop_duplicates(subset="norm_name", keep="first")
    s1 = (
        kcet.merge(aishe_ka_norm_dedup[["aishe_code", "norm_name"]], on="norm_name", how="inner")
        .drop_duplicates(subset="college_code", keep="first")
        [["college_code", "aishe_code"]]
        .assign(kcet_match_method="s1_name_exact")
    )

    # S2: exact short name (address-stripped KCET vs location-stripped AISHE)
    s1_matched = set(s1["college_code"])
    kcet_unmatched = kcet[~kcet["college_code"].isin(s1_matched)]
    aishe_ka_short_dedup = (
        aishe_ka[aishe_ka["short_norm_name"].str.len() > 5]
        .drop_duplicates(subset="short_norm_name", keep="first")
    )
    s2 = (
        kcet_unmatched.merge(
            aishe_ka_short_dedup[["aishe_code", "short_norm_name"]], on="short_norm_name", how="inner"
        )
        .drop_duplicates(subset="college_code", keep="first")
        [["college_code", "aishe_code"]]
        .assign(kcet_match_method="s2_name_short")
    )

    # S3: ratio on short names within Karnataka AISHE
    s2_matched = s1_matched | set(s2["college_code"])
    kcet_unmatched2 = kcet[~kcet["college_code"].isin(s2_matched)].reset_index(drop=True)

    s3_rows = []
    for _, row in kcet_unmatched2.iterrows():
        short = row["short_norm_name"]
        if not short:
            continue
        ratios = [
            difflib.SequenceMatcher(None, short, sn).ratio()
            for sn in aishe_ka["short_norm_name"]
        ]
        best_idx   = max(range(len(ratios)), key=lambda i: ratios[i])
        best_ratio = ratios[best_idx]
        if best_ratio < 0.85:
            continue
        # Guard: don't match if AISHE short name is a strict subset of KCET name
        # (length ratio > 1.25 means one name has 25%+ more tokens — likely a
        # prefix/suffix difference, not a spelling variant).
        aishe_short = aishe_ka.loc[best_idx, "short_norm_name"]
        len_ratio = max(len(short), len(aishe_short)) / max(min(len(short), len(aishe_short)), 1)
        if len_ratio > 1.25:
            continue
        other_max = max((r for i, r in enumerate(ratios) if i != best_idx), default=0)
        if other_max >= best_ratio - 0.06:
            continue  # ambiguous
        s3_rows.append({
            "college_code":      row["college_code"],
            "college_name":      row["college_name"],
            "aishe_code":        aishe_ka.loc[best_idx, "aishe_code"],
            "aishe_name_match":  aishe_ka.loc[best_idx, "college_name"],
            "kcet_match_method": "s3_ratio",
            "_ratio":            round(best_ratio, 3),
        })

    s3 = pd.DataFrame(s3_rows) if s3_rows else pd.DataFrame(
        columns=["college_code", "college_name", "aishe_code", "aishe_name_match",
                 "kcet_match_method", "_ratio"]
    )

    matched = pd.concat(
        [s1, s2, s3[["college_code", "aishe_code", "kcet_match_method"]]], ignore_index=True
    )

    # Aggregate: one row per aishe_code, all KCET codes as a sorted list.
    # The same physical college can appear under two codes (Govt-Aided quota + Private
    # Unaided quota), so we keep all codes — same pattern as nirf_institute_ids.
    def _agg(grp: pd.DataFrame) -> pd.Series:
        codes = sorted(grp["college_code"].tolist())
        best  = grp["kcet_match_method"].map(KCET_METHOD_PRIORITY).idxmin()
        return pd.Series({
            "kcet_college_codes": codes,
            "kcet_match_method":  grp.loc[best, "kcet_match_method"],
        })

    kcet_per_aishe = matched.groupby("aishe_code", sort=False).apply(_agg).reset_index()

    n_unmatched = len(kcet) - len(matched)
    n_multi = (kcet_per_aishe["kcet_college_codes"].apply(len) > 1).sum()
    print(
        f"  KCET Karnataka AISHE pool={len(aishe_ka):,}  "
        f"S1={len(s1):,}  S2={len(s2):,}  S3={len(s3):,}  "
        f"unmatched={n_unmatched:,}  total={len(kcet):,}  "
        f"multi-code={n_multi}"
    )
    if not s3.empty:
        print("  S3 (ratio) matches:")
        for _, r in s3.iterrows():
            print(f"    {r['college_code']}  {r['college_name'][:50]}  →  {r['aishe_name_match'][:50]}  (ratio={r['_ratio']})")
    if n_unmatched > 0:
        unmatched_codes = set(kcet["college_code"]) - set(matched["college_code"])
        unmatched = kcet[kcet["college_code"].isin(unmatched_codes)].sort_values("college_code")
        print(f"  Still unmatched ({n_unmatched}):")
        for _, r in unmatched.iterrows():
            print(f"    {r['college_code']}  {r['college_name']}")

    return kcet_per_aishe


# ── NMC ───────────────────────────────────────────────────────────────────────

def _read_nmc(client) -> pd.DataFrame:
    sql = f"""
        SELECT sl_no, college, state
        FROM `{BQ_PROJECT}.{BQ_DATASET}.{NMC_TABLE}`
        WHERE sl_no IS NOT NULL
    """
    df = client.query(sql).to_dataframe()
    df["norm_name"]       = _norm(df["college"])
    # NMC college field often includes full postal address after the college name
    # (e.g. "ARMED FORCES MEDICAL COLLEGE, PUNE 411040").
    # short_norm_name strips everything after the first comma or paren.
    df["short_norm_name"] = _short_norm(df["college"])
    df["spaceless_name"]  = _spaceless(df["college"])
    df["norm_state"]      = _norm_state(df["state"])
    return df


def _match_nmc(aishe: pd.DataFrame, nmc: pd.DataFrame) -> pd.DataFrame:
    """
    Returns DataFrame: aishe_code → nmc_sl_no + nmc_match_method.

    Matching is restricted to AISHE institutions in the same state as the NMC
    college (state name normalised via _norm — strips & and special chars).

    S1: Exact normalised full name + state match.
    S2: Exact short name (strip address suffix) + state match.
    S3: SequenceMatcher ratio ≥ 0.88 on short names within same state.
        Ambiguity guard: second-best must be > 0.06 below best.
        Length-ratio guard: short names must be within 25% length of each other.
        Collision guard: if multiple NMC colleges produce a ratio match to the
        same AISHE code (e.g. many "Government Medical College" variants), all
        are dropped — these are false positives, not dual-code like KCET.
    S4: Exact spaceless name + state match — split on first comma, remove ALL
        non-alphanumeric chars (including spaces), uppercase, then exact compare.
        Catches dot/space abbreviation variants: "S.N." = "S N" = "SN",
        "J.J.M." = "J J M" = "JJM", "R.V.M." = "R V M" = "RVM".
    """
    # S1: exact full name + state
    aishe_ns_dedup = aishe.drop_duplicates(subset=["norm_name", "norm_state"], keep="first")
    s1 = (
        nmc.merge(aishe_ns_dedup[["aishe_code", "norm_name", "norm_state"]],
                  on=["norm_name", "norm_state"], how="inner")
        .drop_duplicates(subset="sl_no", keep="first")
        [["sl_no", "aishe_code"]]
        .assign(nmc_match_method="s1_name_exact")
    )

    # S2: exact short name + state
    s1_matched = set(s1["sl_no"])
    nmc_unmatched = nmc[~nmc["sl_no"].isin(s1_matched)]
    aishe_short_st_dedup = (
        aishe[aishe["short_norm_name"].str.len() > 5]
        .drop_duplicates(subset=["short_norm_name", "norm_state"], keep="first")
    )
    s2 = (
        nmc_unmatched.merge(
            aishe_short_st_dedup[["aishe_code", "short_norm_name", "norm_state"]],
            on=["short_norm_name", "norm_state"], how="inner",
        )
        .drop_duplicates(subset="sl_no", keep="first")
        [["sl_no", "aishe_code"]]
        .assign(nmc_match_method="s2_name_short")
    )

    # S3: ratio on short names within same state
    s2_matched = s1_matched | set(s2["sl_no"])
    nmc_unmatched2 = nmc[~nmc["sl_no"].isin(s2_matched)].reset_index(drop=True)

    s3_rows = []
    for _, row in nmc_unmatched2.iterrows():
        short = row["short_norm_name"]
        state = row["norm_state"]
        if not short or not state:
            continue
        aishe_st = aishe[aishe["norm_state"] == state].reset_index(drop=True)
        if aishe_st.empty:
            continue
        ratios = [
            difflib.SequenceMatcher(None, short, sn).ratio()
            for sn in aishe_st["short_norm_name"]
        ]
        best_idx   = max(range(len(ratios)), key=lambda i: ratios[i])
        best_ratio = ratios[best_idx]
        if best_ratio < 0.88:
            continue
        aishe_short = aishe_st.loc[best_idx, "short_norm_name"]
        len_ratio = max(len(short), len(aishe_short)) / max(min(len(short), len(aishe_short)), 1)
        if len_ratio > 1.25:
            continue
        other_max = max((r for i, r in enumerate(ratios) if i != best_idx), default=0)
        if other_max >= best_ratio - 0.06:
            continue  # ambiguous
        s3_rows.append({
            "sl_no":            row["sl_no"],
            "college_name":     row["college"],
            "aishe_code":       aishe_st.loc[best_idx, "aishe_code"],
            "aishe_name_match": aishe_st.loc[best_idx, "college_name"],
            "nmc_match_method": "s3_ratio",
            "_ratio":           round(best_ratio, 3),
        })

    s3 = pd.DataFrame(s3_rows) if s3_rows else pd.DataFrame(
        columns=["sl_no", "college_name", "aishe_code", "aishe_name_match",
                 "nmc_match_method", "_ratio"]
    )

    # S3 collision guard: if multiple NMC colleges ratio-match the same AISHE code
    # (e.g. all "Government Medical College, [city]" short-normalize the same way),
    # drop all of them — these are false positives, not legitimate dual entries.
    if not s3.empty:
        s3_dup_codes = set(s3[s3.duplicated(subset="aishe_code", keep=False)]["aishe_code"])
        if s3_dup_codes:
            print(f"  NMC S3 collision guard: removing {len(s3_dup_codes)} ambiguous AISHE code(s)")
            s3 = s3[~s3["aishe_code"].isin(s3_dup_codes)]

    # S4: exact spaceless match within state — catches "S.N." = "S N" = "SN" variants
    s3_matched = s2_matched | set(s3["sl_no"])
    nmc_unmatched3 = nmc[~nmc["sl_no"].isin(s3_matched)]
    aishe_sp_st_dedup = (
        aishe[aishe["spaceless_name"].str.len() > 5]
        .drop_duplicates(subset=["spaceless_name", "norm_state"], keep="first")
    )
    s4 = (
        nmc_unmatched3.merge(
            aishe_sp_st_dedup[["aishe_code", "spaceless_name", "norm_state"]],
            on=["spaceless_name", "norm_state"], how="inner",
        )
        .drop_duplicates(subset="sl_no", keep="first")
        [["sl_no", "aishe_code"]]
        .assign(nmc_match_method="s4_spaceless_exact")
    )

    matched = pd.concat(
        [s1, s2, s3[["sl_no", "aishe_code", "nmc_match_method"]],
         s4], ignore_index=True
    )

    # Final collision check across all strategies: if multiple NMC sl_nos mapped
    # to the same AISHE code (e.g. all "Government Medical College" in one state),
    # DROP ALL — unlike KCET's dual-code, two distinct NMC sl_nos can't be the
    # same physical college, so keeping one would be a false positive.
    dupes = matched[matched.duplicated(subset="aishe_code", keep=False)]
    if not dupes.empty:
        dup_codes = dupes["aishe_code"].nunique()
        print(f"  ⚠ Dropping {dup_codes} AISHE code(s) claimed by multiple NMC sl_nos (ambiguous, not dual-code):")
        for code, grp in dupes.groupby("aishe_code"):
            print(f"    {code}: sl_no={list(grp['sl_no'])}")
        matched = matched[~matched["aishe_code"].isin(dupes["aishe_code"])]

    # Carry original NMC college name (from the PDF) so the bridge is human-readable
    # even if sl_nos are ever renumbered in a future PDF release.
    matched["nmc_college_name"] = matched["sl_no"].map(nmc.set_index("sl_no")["college"])

    n_unmatched = len(nmc) - len(matched)
    print(
        f"  NMC S1={len(s1):,}  S2={len(s2):,}  S3={len(s3):,}  S4={len(s4):,}  "
        f"unmatched={n_unmatched:,}  total={len(nmc):,}"
    )
    if not s3.empty:
        print("  S3 (ratio) matches:")
        for _, r in s3.iterrows():
            print(f"    {r['sl_no']:>3}  {r['college_name'][:55]}  →  {r['aishe_name_match'][:45]}  ({r['_ratio']})")
    if not s4.empty:
        print("  S4 (spaceless exact) matches:")
        sl_to_college = nmc.set_index("sl_no")["college"]
        for _, r in s4.iterrows():
            print(f"    {r['sl_no']:>3}  {sl_to_college[r['sl_no']][:55]}")
    if n_unmatched > 0:
        unmatched_nos = set(nmc["sl_no"]) - set(matched["sl_no"])
        unmatched = nmc[nmc["sl_no"].isin(unmatched_nos)].sort_values("sl_no")
        print(f"  Still unmatched ({n_unmatched}):")
        for _, r in unmatched.iterrows():
            print(f"    {r['sl_no']:>3}  {r['state']:<25}  {r['college'][:65]}")

    return matched[["aishe_code", "nmc_college_name", "nmc_match_method"]]


# ── Assemble ──────────────────────────────────────────────────────────────────

def _build(
    aishe: pd.DataFrame,
    nirf_per_aishe: pd.DataFrame,
    josaa_per_aishe: pd.DataFrame,
    kcet_per_aishe: pd.DataFrame,
    nmc_per_aishe: pd.DataFrame,
) -> pd.DataFrame:
    result = (
        aishe[["aishe_code", "college_name"]]
        .rename(columns={"college_name": "aishe_name"})
        .merge(nirf_per_aishe, on="aishe_code", how="left")
        .merge(josaa_per_aishe, on="aishe_code", how="left")
        .merge(kcet_per_aishe, on="aishe_code", how="left")
        .merge(nmc_per_aishe, on="aishe_code", how="left")
        .sort_values("aishe_code")
        .reset_index(drop=True)
    )
    result["nirf_institute_ids"] = result["nirf_institute_ids"].apply(
        lambda x: x if isinstance(x, list) else []
    )
    result["kcet_college_codes"] = result["kcet_college_codes"].apply(
        lambda x: x if isinstance(x, list) else []
    )
    return result


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dry-run", action="store_true", help="Read + compute; don't write to BQ")
    args = ap.parse_args()

    from google.cloud import bigquery
    from google.cloud.bigquery import LoadJobConfig, SchemaField, WriteDisposition

    client = bigquery.Client(project=BQ_PROJECT, location=BQ_LOCATION)

    print("Reading AISHE…")
    aishe = _read_aishe(client)
    print(f"  {len(aishe):,} institutions across {len(AISHE_TABLES)} tables")

    print("Reading NIRF…")
    nirf = _read_nirf(client)
    print(f"  {len(nirf):,} unique ids  ({nirf['is_modern'].sum():,} modern format)")

    print("Matching NIRF → AISHE…")
    nirf_per_aishe = _match_nirf(aishe, nirf)
    print(f"  {len(nirf_per_aishe):,} AISHE codes with ≥1 NIRF id")

    print("Reading JoSAA…")
    josaa = _read_josaa(client)
    print(f"  {len(josaa):,} unique JoSAA institute names")

    print("Matching JoSAA → AISHE…")
    josaa_per_aishe = _match_josaa(aishe, josaa)
    print(f"  {len(josaa_per_aishe):,} AISHE codes matched to a JoSAA institute")

    print("Reading KCET…")
    kcet = _read_kcet(client)
    print(f"  {len(kcet):,} unique KCET college codes")

    print("Matching KCET → AISHE (Karnataka only)…")
    kcet_per_aishe = _match_kcet(aishe, kcet)
    print(f"  {len(kcet_per_aishe):,} AISHE codes matched to a KCET college")

    print("Reading NMC…")
    nmc = _read_nmc(client)
    print(f"  {len(nmc):,} NMC MBBS colleges")

    print("Matching NMC → AISHE (state-filtered)…")
    nmc_per_aishe = _match_nmc(aishe, nmc)
    print(f"  {len(nmc_per_aishe):,} AISHE codes matched to an NMC college")

    print("Assembling bridge_college_mapping…")
    result = _build(aishe, nirf_per_aishe, josaa_per_aishe, kcet_per_aishe, nmc_per_aishe)

    n_nirf  = result["nirf_institute_ids"].apply(len).gt(0).sum()
    n_josaa = result["josaa_institute_name"].notna().sum()
    n_kcet  = result["kcet_college_codes"].apply(len).gt(0).sum()
    n_nmc   = result["nmc_college_name"].notna().sum()
    print(
        f"  {len(result):,} rows  |  "
        f"NIRF: {n_nirf:,}  |  JoSAA: {n_josaa:,}  |  KCET: {n_kcet:,}  |  NMC: {n_nmc:,}"
    )

    if args.dry_run:
        print("\n[dry-run] Not writing to BQ. Sample rows with NMC match:")
        sample = result[result["nmc_sl_no"].notna()].head(15)
        for _, r in sample.iterrows():
            print(
                f"  {r['aishe_code']:<10}  ({r['nmc_match_method']})  "
                f"nmc_name={str(r['nmc_college_name'])[:50]}  "
                f"aishe_name={r['aishe_name'][:45]}"
            )
        return

    schema = [
        SchemaField("aishe_code",           "STRING",  mode="NULLABLE"),
        SchemaField("aishe_name",            "STRING",  mode="NULLABLE"),
        SchemaField("nirf_institute_ids",    "STRING",  mode="REPEATED"),
        SchemaField("nirf_match_method",     "STRING",  mode="NULLABLE"),
        SchemaField("josaa_institute_name",  "STRING",  mode="NULLABLE"),
        SchemaField("josaa_match_method",    "STRING",  mode="NULLABLE"),
        SchemaField("kcet_college_codes",    "STRING",  mode="REPEATED"),
        SchemaField("kcet_match_method",     "STRING",  mode="NULLABLE"),
        SchemaField("nmc_college_name",      "STRING",  mode="NULLABLE"),
        SchemaField("nmc_match_method",      "STRING",  mode="NULLABLE"),
    ]

    print(f"\nWriting → {OUT_TABLE}…")
    client.load_table_from_dataframe(
        result, OUT_TABLE,
        job_config=LoadJobConfig(
            write_disposition=WriteDisposition.WRITE_TRUNCATE,
            schema=schema,
        ),
    ).result()
    print(f"Done. {len(result):,} rows written.")


if __name__ == "__main__":
    main()
