#!/usr/bin/env python3
"""
Build the CUET merit-rule tables:

  cuet_dim_merit_rules    one row per rule: the papers it counts (as text and
                          as JSON combinations), max score, proration, the
                          bulletin page it is printed on
  cuet_dim_program_rules  every course string in the DU and BHU cutoff facts
                          -> its rule (NULL with a reason for courses CUET
                          alone can't decide: practical / performance tests)

Checks (the build fails on any):
  - every course string gets a rule or an exclusion reason
  - every rule is used, every slot names known papers
  - no cutoff above its rule's maximum (a wrong rule shows up as a cutoff
    the scale can't hold)

Course strings come from the cutoff sources' clean parquet on GCS (see
sources.CUTOFF_SOURCES), so a new course in a cutoff refresh fails here
until it is given a rule.

Usage:
  python3 scripts/build_clean.py            # build + write parquet
  python3 scripts/build_clean.py --dry-run  # build + report only
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import (LANGUAGES, PAPER_LABEL, PAPER_SCORE_MAX, RULE_OF, RULES,
                   SCALE_TO, SUBJECTS, ZERO_IF_MISSING)
from sources import (BULLETIN, CLEAN, CUTOFF_SOURCES, GCS_BUCKET, RAW,
                     RAW_FILES, TABLES, YEAR)

# courses CUET alone can't place a student in
EXCLUDED = [(r"Fine Arts|Performing Arts",
             "admission also needs BHU's practical test")]


def fetch_raw() -> None:
    """GCS is canonical; download any raw file missing locally."""
    missing = [rf for rf in RAW_FILES if not rf.local_path.exists()]
    if not missing:
        return
    from google.cloud import storage
    RAW.mkdir(parents=True, exist_ok=True)
    bucket = storage.Client().bucket(GCS_BUCKET)
    for rf in missing:
        bucket.blob(rf.gcs_path).download_to_filename(str(rf.local_path))
        print(f"  fetched {rf.local_path.name} from {rf.gcs_uri}")


def cutoff_programs() -> pd.DataFrame:
    """(university, program, max_cutoff) from each cutoff source on GCS."""
    from google.cloud import storage
    bucket = storage.Client().bucket(GCS_BUCKET)
    frames = []
    for src in CUTOFF_SOURCES:
        df = pd.read_parquet(io.BytesIO(bucket.blob(src.gcs_path).download_as_bytes()))
        g = df.groupby(src.program_col)[src.score_col].max().reset_index()
        g.columns = ["program", "max_cutoff"]
        g.insert(0, "university", src.university)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def slot_json(slot):
    return slot if isinstance(slot, str) else list(slot)


def slot_text(slot) -> str:
    return {"L": "language", "B": "subject", "G": "GAT"}.get(slot) if isinstance(slot, str) \
        else " or ".join(PAPER_LABEL[p] for p in slot)


def combo_text(combo) -> str:
    """[L, B, B, B] -> 'language + 3 subjects'."""
    parts = []
    for name in map(slot_text, combo):
        if parts and parts[-1][0] == name:
            parts[-1][1] += 1
        else:
            parts.append([name, 1])
    return " + ".join(name if n == 1 else f"{n} {name}s" for name, n in parts)


def build_rules() -> pd.DataFrame:
    known = set(LANGUAGES) | set(SUBJECTS) | {"gat"}
    rows = []
    for rid, (uni, combos, needs_lang, ref) in RULES.items():
        for combo in combos:
            for slot in combo:
                if not isinstance(slot, str):
                    unknown = set(slot) - known
                    assert not unknown, f"{rid}: unknown papers {unknown}"
        sizes = {len(c) for c in combos}
        text = ", or ".join(combo_text(c) for c in combos)
        rows.append({
            "rule_id": rid, "university": uni,
            "papers": text[0].upper() + text[1:],
            "combinations_json": json.dumps([[slot_json(s) for s in c] for c in combos]),
            "n_combinations": len(combos),
            # the scale the printed cut-offs use: the paper total, or that
            # total rescaled (JNU: of 500 -> of 100)
            "max_score": SCALE_TO.get(rid, max(sizes) * PAPER_SCORE_MAX),
            "papers_max": max(sizes) * PAPER_SCORE_MAX,
            "prorated": len(sizes) > 1,
            "needs_language": needs_lang,
            "missing_counts_zero": rid in ZERO_IF_MISSING,
            "source_url": BULLETIN[uni].url,
            "source_ref": ref,
            "year": YEAR,
        })
    return pd.DataFrame(rows)


def build_programs(progs: pd.DataFrame, rules: pd.DataFrame) -> pd.DataFrame:
    out, missing = [], []
    for r in progs.itertuples():
        rid = RULE_OF[r.university](r.program)
        reason = None
        if rid is None:
            reason = next((why for pat, why in EXCLUDED if re.search(pat, r.program)), None)
            if reason is None:
                missing.append((r.university, r.program))
        out.append({"university": r.university, "program": r.program,
                    "rule_id": rid, "excluded_reason": reason,
                    "max_cutoff": round(float(r.max_cutoff), 2), "year": YEAR})
    if missing:
        raise SystemExit(f"{len(missing)} courses have no rule (add them to rules.py):\n"
                         + "\n".join(f"  {u}: {p}" for u, p in missing))
    df = pd.DataFrame(out)
    unused = set(rules.rule_id) - set(df.rule_id.dropna())
    assert not unused, f"rules no course uses: {unused}"
    m = df.merge(rules[["rule_id", "max_score"]], on="rule_id")
    over = m[m.max_cutoff > m.max_score]
    if len(over):
        raise SystemExit("cutoffs above their rule's maximum (wrong rule?):\n"
                         + over[["university", "program", "rule_id", "max_cutoff", "max_score"]].to_string())
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    fetch_raw()
    rules = build_rules()
    progs = build_programs(cutoff_programs(), rules)
    print(f"cuet_dim_merit_rules: {len(rules)} rules "
          f"({', '.join(f'{u} {n}' for u, n in rules.university.value_counts().items())})")
    print(f"cuet_dim_program_rules: {len(progs)} course strings, "
          f"{progs.rule_id.notna().sum()} with a rule, "
          f"{progs.excluded_reason.notna().sum()} excluded")
    print(progs.groupby("university").rule_id.agg(["count", "nunique"]).to_string())
    if args.dry_run:
        return
    CLEAN.mkdir(exist_ok=True)
    rules.to_parquet(TABLES[0].local_path, index=False)
    progs.to_parquet(TABLES[1].local_path, index=False)
    for t in TABLES:
        print(f"✓ wrote {t.local_path}")


if __name__ == "__main__":
    main()
