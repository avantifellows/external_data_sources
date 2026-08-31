#!/usr/bin/env python3
"""
OJEE B.Tech 2025 opening/closing ranks -> ojee/clean/ojee_fact_cutoffs.parquet

THE RANKS ARE JEE (MAIN) RANKS: Odisha admits first-year B.Tech on JEE Main
through OJEE counselling, so OR/CR run into the lakhs. Not an OJEE state
rank, never comparable to other state tables.

Parse strategy: pdfplumber's table extraction garbles ~40 rows where a long
programme name wraps across lines (characters from the wrapped line
interleave into the CATEGORY/SEAT/QUOTA cells). The wrapped-text columns
(institute, programme) come from pdfplumber, which handles multi-line cells
correctly; the five right columns come from a y-locked word parse anchored
on the numeric OR/CR tokens, which wrapped text cannot pollute. The two
parses are zipped in document order and cross-checked on OR/CR.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from sources import RAW_FILES  # noqa: E402

RAW, CLEAN = ROOT / "raw", ROOT / "clean"

# column x-starts measured from the header row (stable across pages)
CAT_CODES = {"OP": "General", "SC": "SC", "ST": "ST", "EW": "EW"}

XBOUNDS = [("category", 499), ("seat_type", 538), ("opening_rank", 595),
           ("closing_rank", 629), ("quota", 665), ("cat_code", 700),
           ("spl_cat", 716)]


def colof(x: float) -> str | None:
    name = None
    for n, x0 in XBOUNDS:
        if x >= x0:
            name = n
    return name


def anchor_rows(page) -> list[dict]:
    """One dict per data line. On ~3 BPUT rows the PDF's own text layer
    physically overlaps two lines, fusing tokens ("CommunGiceanteioranl" =
    Communication x General; "PG1)74629" = PG) x 174629). Recovery is
    deterministic without untangling the interleave:
      - ranks: digits of the rank-column tokens, concatenated in x order
        (interleaving preserves character order within each source string);
      - category: from the CAT code column, which never fuses (OP/SC/ST/EW);
      - seat type: 'Female Only' iff an 'F' appears in the seat cell -
        the only other text that can land there ("year integrated UG & PG",
        "Gender Neutral") contains no F.
    """
    lines = defaultdict(list)
    for w in page.extract_words():
        lines[round(w["top"])].append(w)
    out = []
    for y in sorted(lines):
        cells = defaultdict(list)
        for w in sorted(lines[y], key=lambda w: w["x0"]):
            c = colof(w["x0"])
            if c:
                cells[c].append(w["text"])
        o = "".join(ch for t in cells["opening_rank"] for ch in t if ch.isdigit())
        c = "".join(ch for t in cells["closing_rank"] for ch in t if ch.isdigit())
        code = " ".join(cells.get("cat_code", [])).strip()
        if o and c and code in CAT_CODES:
            out.append({
                "opening_rank": o, "closing_rank": c,
                "category": CAT_CODES[code],
                "seat_type": "Female Only" if "F" in " ".join(cells["seat_type"]) else "Gender Neutral",
                "quota": " ".join(cells.get("quota", [])).strip(),
                "spl_cat": " ".join(cells.get("spl_cat", [])).strip(),
            })
    return out


# ── de-fusing overflow institute names out of programme strings ─────────────
# Six institutes' names overflow their column and the PDF prints the tail
# ON TOP of the programme text (same y, interleaved x). The interleave
# preserves character order in both strings, so removing the known tail as a
# subsequence recovers the programme exactly. Tails were read off the fused
# strings themselves; a full-match assert guards every removal.
CONTINUATIONS = {
    # CUTM prints two campuses, each with its own overflow tail
    "CENTURION UNIVERSITY OF TECHNOLOGY AND MANAGEMENT,(CUTM": [") ODISHA, BHUBANESWAR CAMPUS", ") ODISHA, PARALAKHEMUNDI CAMPUS"],
    "GANESH INSTITUTE OF ENGINEERING & TECHNOLOGY, POLYTECHNIC,K": ["HORDHA"],
    "INTERSCIENCE INSTITUTE OF MANAGEMENT & TECHNOLOGY, BHUBAN": ["ESWAR"],
    "KALLINGA GLOBAL INSTITUTE OF TECHNOLOGY, INNOVATION & MANA": ["GEMENT,JAJPUR"],
    "Odisha University of Technology and Research (formerly College of Eng": ["ineering and Technology), Bhubaneswar"],
    "RADHAKRISHNA INSTITUTE OF TECHNOLOGY & ENGINEERING, BHUBA": ["NESWAR"],
    # these two overflow only their CITY, so the head ends at a comma and the
    # city interleaves the programme ("BCuormlaputer" = Burla x Computer)
    "Sambalpur University Institute of Information Technology, Jyoti Vihar,": ["Burla"],
    "Balaji Institute of Technology & Science, Knowledge Centre, Gunupur,": ["Rayagada"],
}

FUSE_SIG = None  # set lazily


def looks_fused(s: str) -> bool:
    import re
    for t in s.split():
        if len(re.findall(r"[a-z][A-Z]", t)) >= 2:
            return True
        # a Titlecase city interleaved into a Titlecase word leaves two
        # leading capitals and no case flips ("BCuormlaputer", "RCaiyvailg")
        if len(t) > 4 and re.match(r"^[A-Z]{2,}[a-z]", t):
            return True
    return False


def remove_subsequence(fused: str, tail: str) -> str | None:
    """Remove tail as a subsequence of fused (greedy leftmost, spaces in the
    tail may match spaces or be skipped). Returns the remainder, or None if
    the tail does not fully embed."""
    out, ti = [], 0
    for ch in fused:
        if ti < len(tail) and ch == tail[ti]:
            ti += 1
        elif ti < len(tail) and tail[ti] == " " and ch != " " and ti + 1 < len(tail) and ch == tail[ti + 1]:
            ti += 2  # tail space absorbed by the interleave
        else:
            out.append(ch)
    return "".join(out) if ti >= len(tail) - 1 else None


def defuse(df: pd.DataFrame) -> pd.DataFrame:
    """For every row under an overflow-affected institute head, try to remove
    each known tail as a subsequence of the programme string. Applied only
    when a tail fully embeds - rows the overflow did not reach are untouched.
    Both greedy directions are tried (leftmost and rightmost matching) and
    the remainder with more intact spacing wins; a canonical-spelling lookup
    against the document's own clean rows normalises the survivors.
    """
    clean = {p.replace(" ", ""): p for p in df.loc[~df.programme.map(looks_fused), "programme"].unique()
             if not p.startswith(")")}
    fixed = 0
    for idx, row in df.iterrows():
        tails = CONTINUATIONS.get(row.institute)
        if not tails:
            continue
        best, best_tail = None, None
        for cand in tails:
            for direction in ("ltr", "rtl"):
                if direction == "ltr":
                    rem = remove_subsequence(row.programme, cand)
                else:
                    r = remove_subsequence(row.programme[::-1], cand[::-1])
                    rem = r[::-1] if r is not None else None
                if rem is None:
                    continue
                rem = " ".join(rem.split())
                rem = clean.get(rem.replace(" ", ""), rem)
                # prefer the remainder with more spaces (less glue), then shorter
                if best is None or rem.count(" ") > best.count(" "):
                    best, best_tail = rem, cand
        if best is None:
            assert not looks_fused(row.programme) and not row.programme.startswith(")"), \
                f"fused but no tail embeds: {row.institute!r} / {row.programme!r}"
            continue
        assert not looks_fused(best) and not best.startswith(")"), \
            f"still fused after removal: {best!r}"
        df.at[idx, "programme"] = best
        joiner = " " if row.institute.endswith(",") else ""
        df.at[idx, "institute"] = row.institute + joiner + best_tail
        fixed += 1
    print(f"  de-fused {fixed} rows (institute tail re-joined, programme recovered)")

    # rows the overflow did not reach keep the truncated institute head —
    # complete them too (single-tail institutes only; CUTM's two campuses
    # can only be told apart by which tail embedded)
    for head, tails in CONTINUATIONS.items():
        if len(tails) == 1:
            joiner = " " if head.endswith(",") else ""
            df.loc[df.institute == head, "institute"] = head + joiner + tails[0]
    # tripwire: a head cut at a comma means an overflow tail we don't know
    dangling = sorted(df.loc[df.institute.str.rstrip().str.endswith(","), "institute"].unique())
    assert not dangling, f"institutes still truncated at a comma (unregistered overflow?): {dangling}"

    # second sweep: a recovered spelling can be the canonical form for a
    # remainder that lost its spaces (OUTR's AEROSPACEENGINEERING finds
    # CUTM's recovered "AEROSPACE ENGINEERING"). Map on the space-stripped
    # form, TFW suffix aside, preferring the spelling with more spaces.
    best_form: dict[str, str] = {}
    for p in df.programme.unique():
        base = p.replace(" - TFW", "").replace("- TFW", "").replace("-TFW", "")
        k = base.replace(" ", "")
        if k not in best_form or base.count(" ") > best_form[k].count(" "):
            best_form[k] = base
    def renorm(p: str) -> str:
        for suf in (" - TFW", "- TFW", "-TFW"):
            if p.endswith(suf):
                return best_form[p[: -len(suf)].replace(" ", "")] + " - TFW"
        return best_form[p.replace(" ", "")]
    df["programme"] = df.programme.map(renorm)

    # the source's own column edge cuts two spellings mid-word; complete the
    # word only (never guess beyond it — the tfw FLAG comes from the seat
    # column, so "- TF" rows were already correct functionally)
    df["programme"] = (df.programme
                       .str.replace(r"Machine Learni$", "Machine Learning", regex=True)
                       .str.replace(r"- TF$", "- TFW", regex=True))
    return polish_spellings(df)


def polish_spellings(df: pd.DataFrame) -> pd.DataFrame:
    """Two artifact classes the tail-removal above cannot see:

    TRANSPOSITIONS / SPACE JITTER — x-coordinate noise swaps adjacent chars
    or moves a space ("Elcetric la Engineering", "InformationTechnology").
    Both preserve the letter multiset, so variants group by sorted-letters
    key; the winner is decided by EVIDENCE, not frequency (a dirty spelling
    can outnumber the clean one): score a variant by how many of its words
    also occur in unrelated programmes ("Electronics" is everywhere,
    "Elcetronics" only at one institute).

    SINGLE-FRAGMENT INTERLEAVES — an institute tail this short drops one
    fragment into the programme ("aCivil Engineering", "wCaormputer…",
    "mCiivliigl uEdnagineering"). Removing a known-good programme as a
    subsequence leaves just the fragment; a unique longest fit recovers the
    programme. The fragment is a truncated city shard — not restorable, so
    it is dropped, never appended.
    """
    import re
    from collections import Counter

    def split_tfw(p: str) -> tuple[str, bool]:
        return (p[:-6].rstrip(), True) if p.endswith("- TFW") else (p, False)

    def letters(s: str) -> str:
        return "".join(sorted(re.sub(r"[^a-z0-9]", "", s.lower())))

    # CIPET's and EAST's overflow-hit programmes exist NOWHERE clean in the
    # document, so subsequence recovery has no target — spelled by hand
    # (fragments: CIPET drops "swar", EAST drops "war"; both verified)
    MANUAL = {
        "sPwlaasrtic Engineering": "Plastic Engineering",
        "sMwaanrufacturing Engineering & Technology": "Manufacturing Engineering & Technology",
        "sInwtaergrated M.Sc. in Material Science and Engg": "Integrated M.Sc. in Material Science and Engg",
        "wEanrvironmental Engineering": "Environmental Engineering",
        "Txetlie Engineering": "Textile Engineering",
        # OUTR spells one programme two ways, both with the space shifted
        "MechanicalE ngg.( Artificial Intelligence and Robotics)":
            "Mechanical Engineering (Artificial Intelligence and Robotics)",
        "MechanicalE ngineering (Artificial Intelligence and Robotics)":
            "Mechanical Engineering (Artificial Intelligence and Robotics)",
        # glued spaces with no clean sibling anywhere in the document
        "InformationTechnology(SSC)": "Information Technology(SSC)",
        "Integrated MSc in AppliedPhysics": "Integrated MSc in Applied Physics",
    }

    fixed_sp = fixed_il = 0
    # to a FIXPOINT: when every variant of a programme is dirty, round one's
    # multiset winner is itself dirty — recovery cleans the winner, and the
    # next round pulls the remaining variants onto the cleaned spelling
    for _ in range(4):
        bases = Counter(split_tfw(p)[0] for p in df.programme)
        word_df = Counter()
        for b in bases:
            for w in set(re.findall(r"[A-Za-z]{3,}", b)):
                word_df[w] += 1

        def evidence(b: str) -> int:
            return sum(1 for w in set(re.findall(r"[A-Za-z]{3,}", b)) if word_df[w] >= 4)

        canonical: dict[str, str] = {}
        for b in bases:
            k = letters(b)
            if k not in canonical or (evidence(b), bases[b]) > (evidence(canonical[k]), bases[canonical[k]]):
                canonical[k] = b
        good = sorted({b for b in canonical.values() if evidence(b) >= 1},
                      key=len, reverse=True)

        changed = 0
        for idx, p in df.programme.items():
            base, tfw = split_tfw(p)
            if base in MANUAL:
                df.at[idx, "programme"] = MANUAL[base] + (" - TFW" if tfw else "")
                fixed_il += 1
                changed += 1
                continue
            target = canonical[letters(base)]
            if target != base:
                fixed_sp += 1
            elif (evidence(base) == 0 or looks_fused(base)
                  # a fragment lands before the capital: "aComputer"
                  or any(re.match(r"^[a-z]{1,4}[A-Z]", t) for t in base.split())
                  # or inside a word almost no other programme uses
                  # ("Cromputer" appears in two sibling rows)
                  or any(word_df[w] <= 2 and bases[base] <= 12
                         for w in set(re.findall(r"[A-Za-z]{4,}", base)))):
                # genuinely unique programmes simply find no subsequence fit
                # and pass through the recovery unchanged
                hits = []
                for g in good:
                    rem = remove_subsequence(base, g)
                    # a genuine institute shard is a short run of LOWERCASE
                    # letters ("r", "a", "war", "miliguda") — an uppercase or
                    # parenthesised remainder ("(SSC)") is a real suffix that
                    # distinguishes a separate programme, never a shard
                    if rem is not None and re.fullmatch(r"[a-z ]{1,10}", rem.strip()):
                        hits.append(g)
                        if len(hits) > 1 and len(hits[1]) < len(hits[0]):
                            break  # longest fit already unique
                if hits:
                    target, fixed_il = hits[0], fixed_il + 1
            if target != base:
                df.at[idx, "programme"] = target + (" - TFW" if tfw else "")
                changed += 1
        if not changed:
            break

    leftover = sorted({p for p in df.programme
                       if looks_fused(split_tfw(p)[0])
                       or any(re.match(r"^[a-z]{1,4}[A-Z]", t) for t in p.split())})
    assert not leftover, f"unrecoverable fused programmes: {leftover}"
    print(f"  spelling-normalised {fixed_sp} rows, interleave-recovered {fixed_il} rows")
    return df


def canon(cat: str) -> str:
    cat = cat.strip()
    return {"General": "GEN", "SC": "SC", "ST": "ST", "EW": "EWS"}.get(cat, "OTHER")


def main() -> None:
    CLEAN.mkdir(exist_ok=True)
    fname, _, year = RAW_FILES[0]
    rows: list[dict] = []
    KNOWN_CAT = {"General", "SC", "ST", "EW"}
    KNOWN_SEAT = {"Gender Neutral", "Female Only"}
    recovered = 0
    with pdfplumber.open(RAW / fname) as pdf:
        for page in pdf.pages:
            anchors = anchor_rows(page)

            def pop_anchor(o: str, c: str) -> dict:
                for i, a in enumerate(anchors):
                    if a["opening_rank"] == o and a["closing_rank"] == c:
                        return anchors.pop(i)
                raise AssertionError(
                    f"p{page.page_number}: no anchor for garbled row {o}/{c}")

            for tbl in page.extract_tables() or []:
                for r in tbl:
                    if not r or len(r) != 9 or r[0] in (None, "INSTITUTE"):
                        continue
                    if "OPENING" in str(r[0]):
                        continue
                    cells = [(x or "").replace("\n", " ").strip() for x in r]
                    clean = (cells[4].isdigit() and cells[5].isdigit()
                             and cells[2] in KNOWN_CAT and cells[3] in KNOWN_SEAT)
                    if clean:
                        cat, seat, quota, spl = cells[2], cells[3], cells[6], cells[8]
                        o, c = cells[4], cells[5]
                    else:
                        # fused-text row: digits survive in order inside the
                        # fused tokens - use them to find the matching anchor
                        o = "".join(ch for ch in cells[4] if ch.isdigit())
                        c = "".join(ch for ch in cells[5] if ch.isdigit())
                        a = pop_anchor(o, c)
                        cat, seat, quota, spl = a["category"], a["seat_type"], a["quota"], a["spl_cat"]
                        recovered += 1
                    rows.append({
                        "exam_year": year,
                        "institute": cells[0],
                        "programme": cells[1],
                        "category_raw": cat,
                        "category": canon(cat),
                        "seat_type": seat,
                        "quota": quota,
                        "tfw": spl == "TF",
                        "opening_rank": int(o),
                        "closing_rank": int(c),
                    })

    df = pd.DataFrame(rows)
    df = defuse(df)

    # THREE rank scales share this document. B.Tech (incl. 5-year integrated)
    # admits on JEE Main; B.Arch / B.Plan on their own scale (ranks ~1e4);
    # the film institute's diploma rows on its own merit list (ranks ~1e2).
    # Tag the family so nothing downstream compares across scales.
    def family(r):
        if "FILM" in r.institute.upper():
            return "film"
        p = r.programme.upper()
        if p.startswith(("B ARCH", "B. PLAN", "B.ARCH", "B.PLAN")):
            return "barch-bplan"
        return "btech-jeemain"
    df["rank_family"] = df.apply(family, axis=1)
    key = ["institute", "programme", "category_raw", "seat_type", "quota", "tfw"]
    # The source itself prints ONE bucket twice: BPUT Rourkela's 5-year
    # integrated CSE (General/Gender Neutral/HS) appears as two rows with
    # adjacent rank windows (143763-308120 and 314865-356866) - identical
    # verbatim strings in the PDF. Kept verbatim, disambiguated by dup_seq;
    # anything beyond that one known case fails the build.
    df["dup_seq"] = df.groupby(key).cumcount()
    extra = df[df.dup_seq > 0]
    assert len(extra) == 1 and extra.iloc[0].opening_rank == 314865, \
        f"unexpected duplicate buckets:\n{extra}"

    print(f"  {len(df):,} rows ({recovered} recovered from fused text) | "
          f"{df.institute.nunique()} institutes | {df.programme.nunique()} programmes")
    print("  category_raw:", df.category_raw.value_counts().to_dict())
    print("  seat_type:", df.seat_type.value_counts().to_dict())
    print("  quota:", df.quota.value_counts().to_dict())
    print("  tfw:", df.tfw.value_counts().to_dict())
    print("  rank_family:", df.rank_family.value_counts().to_dict())

    a = df[df.institute.str.contains("Technology and Rese", case=False, na=False)
           & df.programme.str.contains("Computer Sc", na=False)
           & (df.category_raw == "General") & (df.seat_type == "Gender Neutral")
           & ~df.tfw]
    print("  anchor OUTR CSE Gen GN:", a[["quota", "opening_rank", "closing_rank"]].to_dict("records"))

    out = CLEAN / "ojee_fact_cutoffs.parquet"
    df.to_parquet(out, index=False)
    print(f"  -> {out} ({out.stat().st_size:,}B)")


if __name__ == "__main__":
    main()
