"""
Shared institute-name cleaning for the NEET cutoff parsers.

Some counselling PDFs (notably the MCC All India Quota file, and partly
Karnataka) pack the full postal address into the institute cell:

    "AIIMS, New Delhi,AIIMS ANSARI NAGAR EAST AUROBINDO MARG NEW DELHI 110029,
     Delhi (NCT), 110029"

That is an extraction artifact, so we resolve it here at the parser layer (not
downstream): split into a clean display NAME (+ city) and a preserved ADDRESS.
The address is never discarded — it moves to its own column.

Parsers whose PDFs already give clean names (Gujarat, WB, MP, Punjab, Andhra)
can call split_institute too; it is a no-op for a plain name.
"""
from __future__ import annotations
import re


# A trailing address segment that is a pincode, optionally followed by a
# parenthetical seat annotation, e.g. "110095", "110095 (Female Seat only )".
# Group 2 captures the annotation text (without the parens) when present.
_PIN_TAIL_RE = re.compile(r"^\d{5,6}\s*(?:\(([^)]*)\))?\s*$")
_WS_RE = re.compile(r"\s+")


def _norm_ws(s: str) -> str:
    """Collapse internal whitespace runs to one space. PDFs line-wrap inside
    tokens (``CIV IL``→``CIVIL`` is a *different* problem, handled by the caller
    normalizing names), but at least fold the multi-space artifacts so keys and
    display text are stable."""
    return _WS_RE.sub(" ", (s or "")).strip()


def split_institute(raw: str):
    """Return (name, address, state, note) from a raw institute string.

    Format seen in MCC/AIQ: 'Name, City,ADDRESS BLOB, State, pincode[(note)]'.
    - name    = college name (+ city when the 2nd segment is clearly a city)
    - address = everything else, joined back with ", " (preserved, not dropped)
    - state   = best-effort from the trailing ', State, pincode'
    - note    = a seat annotation that rode along on the pincode segment, e.g.
                'Female Seat only' (kept as its own field, never dumped in State)

    The trailing segment is often ``<pincode>`` OR ``<pincode> (Female Seat
    only)``. The old logic only recognised a *bare* pincode, so the annotated
    form fell through and the whole ``110095 (Female Seat only)`` string became
    the State. We now strip a pincode-with-optional-note tail robustly and take
    the segment before it as the State.
    """
    raw = _norm_ws(raw or "").strip()
    # 'Name,,ADDRESS' — empty city slot means the address starts immediately.
    had_empty_city = ",," in raw.replace(", ,", ",,")
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    if len(parts) <= 1:
        return raw, "", "", ""

    name = parts[0]
    city = parts[1] if len(parts) >= 2 else ""
    looks_like_city = (
        city
        and not had_empty_city
        and len(city) <= 18
        and not re.search(r"\d{3,}", city)
        and len(city.split()) <= 2  # a city, not an ALL-CAPS street phrase
    )
    if looks_like_city:
        name = f"{parts[0]}, {city}"
        rest = parts[2:]
    else:
        rest = parts[1:]

    note = ""
    state = ""
    if rest:
        tail = rest[-1]
        m = _PIN_TAIL_RE.match(tail)
        if m:  # tail is a pincode (bare or with a (note)) -> state is the prior seg
            if m.group(1):
                note = _norm_ws(m.group(1))
            if len(rest) >= 2:
                state = rest[-2]
        else:
            state = tail
    address = ", ".join(rest)
    return name, address, state, note


# --- program (MBBS vs BDS) from the college name -------------------------------
# Several state files don't label the degree per row, but the college name does
# (Amogh's heuristic): a Medical college -> MBBS, a Dental college -> BDS. Indian
# college names fuse the M/D into acronyms (GMC/GSMC/BJMC/GDC = medical/dental),
# so match those acronym suffixes plus the spelled-out words. A name matching
# both (or neither) returns "REVIEW" for manual check rather than a guess.
_MED_RE = re.compile(r"MEDICAL|\bMED\b|[A-Z]MC\b|\bMC\b|IMS|\bMH\b")
_DEN_RE = re.compile(r"DENTAL|[A-Z]DC\b|\bDC\b")


def program_from_name(name: str) -> str:
    u = (name or "").upper()
    med = bool(_MED_RE.search(u))
    den = bool(_DEN_RE.search(u))
    if med and den:
        return "REVIEW"
    if med:
        return "MBBS"
    if den:
        return "BDS"
    return "REVIEW"
