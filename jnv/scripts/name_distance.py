"""Indian-name distance for the JNV student outcome mapping (build_student_outcome_mapping.py).

Our own code. The idea (low costs for common Indian spelling variants, a limit that grows with
name length) comes from devdatalab/masala-merge. No code is copied from that repo (it has no license).
The length limits are the masala-merge defaults (fuzziness 1).

normalise(s)          upper case, letters only, common spelling variants made the same (EE->I, KSH->X, BH->B, ...)
name_distance(a, b)   weighted edit distance after normalise; word order does not count
name_limit(a, b)      the largest distance that counts as the same name, by name length
same_name(a, b)       name_distance <= name_limit
father_check(a, b)    'missing' | 'same' | 'spelling variant' | 'initial or dropped word' | 'different'
given_names_differ(a, b)  True when two student names with the same DOB and parents look like twins
"""
import re
from functools import lru_cache
from itertools import permutations

VOWELS = frozenset("AEIOUY")
# consonants that Indian spellings often exchange (after normalise: W->V, Z->J, Q->K)
NEAR = {frozenset(p) for p in ("BV", "DT", "GJ", "KC", "PF", "RD")}

_RULES = [
    (re.compile(r"[^A-Z ]"), ""),
    (re.compile(r"KSH|KS"), "X"),        # LAKSHMI, LAXMI
    (re.compile(r"PH"), "F"),
    (re.compile(r"EE"), "I"),            # PRADEEP, PRADIP
    (re.compile(r"OO"), "U"),
    (re.compile(r"Q"), "K"),
    (re.compile(r"W"), "V"),
    (re.compile(r"Z"), "J"),
    (re.compile(r"CK"), "K"),
    (re.compile(r"([BDGJKPT])H"), r"\1"),  # aspirated consonants: BH->B, DH->D, TH->T, ...
    (re.compile(r"([A-Z])\1+"), r"\1"),     # double letters
]


def normalise(s) -> str:
    if s is None:
        return ""
    s = re.sub(r"\s+", " ", str(s).upper().replace(".", " ")).strip()
    for pat, rep in _RULES:
        s = pat.sub(rep, s)
    return re.sub(r"\s+", " ", s).strip()


def _words(s) -> list[str]:
    return [w for w in normalise(s).split(" ") if w]


def _sub(x: str, y: str) -> float:
    if x == y:
        return 0.0
    if x in VOWELS and y in VOWELS:
        return 0.4
    if frozenset((x, y)) in NEAR:
        return 0.5
    return 1.0


def _indel(x: str) -> float:
    return 0.3 if x in VOWELS or x == "H" else 1.0


@lru_cache(maxsize=500_000)
def _dist(a: str, b: str) -> float:
    """Weighted edit distance with adjacent transposition (cost 0.5). A different first letter costs double."""
    n, m = len(a), len(b)
    prev2, prev = None, [0.0]
    for j in range(m):
        prev.append(prev[-1] + _indel(b[j]))
    for i in range(1, n + 1):
        cur = [prev[0] + _indel(a[i - 1])]
        for j in range(1, m + 1):
            c = min(prev[j] + _indel(a[i - 1]),
                    cur[j - 1] + _indel(b[j - 1]),
                    prev[j - 1] + _sub(a[i - 1], b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1] and a[i - 1] != b[j - 1]:
                c = min(c, prev2[j - 2] + 0.5)
            cur.append(c)
        prev2, prev = prev, cur
    d = prev[m]
    if a and b and a[0] != b[0]:
        d += _sub(a[0], b[0])
    return d


def name_distance(a, b) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return float("inf")
    return min(_dist("".join(wa), "".join(wb)), _dist("".join(sorted(wa)), "".join(sorted(wb))))


def _limit_for(n: int) -> float:
    return 0.9 if n <= 4 else 1.0 if n <= 5 else 1.3 if n <= 8 else 1.4 if n <= 14 else 1.8 if n <= 17 else 2.1


def name_limit(a, b) -> float:
    la = len(re.sub(r"[^A-Z]", "", str(a).upper()))
    lb = len(re.sub(r"[^A-Z]", "", str(b).upper()))
    return _limit_for((la + lb) // 2)


def same_name(a, b) -> bool:
    return name_distance(a, b) <= name_limit(a, b)


def _word_match(x: str, y: str) -> str | None:
    """'initial' when one word is a single letter that starts the other, 'word' when the words are close."""
    if len(x) == 1 or len(y) == 1:
        return "initial" if (y.startswith(x) or x.startswith(y)) else None
    return "word" if _dist(x, y) <= _limit_for((len(x) + len(y)) // 2) else None


def _subset(small: list[str], big: list[str]) -> bool:
    """Every word of the shorter name matches a different word of the longer one, and at least one
    match is a full word (not an initial)."""
    if not small or len(big) > 6:
        return False
    for perm in permutations(big, len(small)):
        kinds = [_word_match(x, y) for x, y in zip(small, perm)]
        if all(kinds) and "word" in kinds:
            return True
    return False


def father_check(a, b) -> str:
    if not normalise(a) or not normalise(b):
        return "missing"
    if re.sub(r"[^A-Z]", "", str(a).upper()) == re.sub(r"[^A-Z]", "", str(b).upper()):
        return "same"
    if same_name(a, b):
        return "spelling variant"
    wa, wb = _words(a), _words(b)
    small, big = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if _subset(small, big):
        return "initial or dropped word"
    return "different"


# ── father check v2: father_check plus optional rules (opts) ──
HONORIFICS = {"MR", "MRS", "SHRI", "SRI", "SHREE", "SMT", "LATE", "LT", "DR", "MISS", "SH", "STHE"}
PLACEHOLDERS = {"FARMER", "TEACHER", "LABOUR", "LABOURER", "DRIVER", "BUSINESS", "SERVICE", "NA", "NIL",
                "NONE", "UNKNOWN", "FATHER", "GUARDIAN", "CULTIVATOR", "AGRICULTURE", "HOUSEWIFE", "XXX"}
# words too common to identify a father alone (after normalise)
FILLERS = {"KUMAR", "SINGH", "LAL", "PRASAD", "CHANDRA", "DEVI", "BAI", "BEN", "RAM", "DAS", "MOHAMAD",
           "MOHAMED", "MUHAMAD", "MD", "MOHD", "SK", "SAIK", "SEIK", "KAN", "BEGUM"}
OPTIONS = ("placeholders", "abbrev", "span", "prefix", "first_name")


def _raw_words(s) -> list[str]:
    return [w for w in re.sub(r"[^A-Z ]", "", re.sub(r"\s+", " ", str(s).upper().replace(".", " "))).split(" ") if w]


def _strip_honorific(words: list[str]) -> list[str]:
    """Drop honorifics at the start only (SH in the middle is SHANKAR)."""
    out = list(words)
    while out and out[0] in HONORIFICS:
        out = out[1:]
    return out


def _strip_suffix(w: str) -> str:
    for suf in ("BAI", "BEN"):                # BHAI -> BAI after normalise
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[: -len(suf)]
    return w


def _is_subseq(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def _word_match_v2(x: str, y: str, opts) -> str | None:
    base = _word_match(x, y)
    if base:
        return base
    short, long = (x, y) if len(x) <= len(y) else (y, x)
    if "abbrev" in opts and 2 <= len(short) <= 4 and len(long) >= len(short) + 2 \
            and short[0] == long[0] and _is_subseq(short, long):
        return "initial"                      # KR -> KUMAR, CH -> CHANDRA, MOHD -> MOHAMAD, AH -> AHMAD
    if "prefix" in opts:
        if len(short) >= 5 and long.startswith(short):
            return "word"                     # NEHRU -> NEHRULAL, PURAN -> PURANMAL
        sx, sy = _strip_suffix(x), _strip_suffix(y)
        if (sx, sy) != (x, y) and (sx == sy or _word_match(sx, sy) == "word"
                                   or (min(len(sx), len(sy)) >= 5 and (sx.startswith(sy) or sy.startswith(sx)))):
            return "word"                     # MAHESHBHAI -> MAHESH, PARBATBHAI -> PARBAT
    return None


def _subset_v2(small: list[str], big: list[str], opts) -> bool:
    if not small or len(big) > 6:
        return False
    for perm in permutations(big, len(small)):
        kinds = [_word_match_v2(x, y, opts) for x, y in zip(small, perm)]
        if all(kinds) and "word" in kinds:
            return True
    return False


def _span_match(ra: list[str], rb: list[str]) -> bool:
    """One whole name (raw words joined, then normalised) matches a run of consecutive words of the other
    name (joined, then normalised). The run must leave out at least one word."""
    for whole_raw, words in (("".join(ra), rb), ("".join(rb), ra)):
        whole = normalise(whole_raw)
        for i in range(len(words)):
            for j in range(i + 1, len(words) + 1):
                if j - i == len(words):
                    continue
                span_raw = "".join(words[i:j])
                if len(span_raw) >= 4 and _dist(whole, normalise(span_raw)) <= _limit_for((len(whole_raw) + len(span_raw)) // 2):
                    return True
    return False


def father_check_v2(a, b, opts=frozenset(OPTIONS)) -> str:
    """'missing' | 'same' | 'spelling variant' | 'initial or dropped word' | 'joined or split words'
    | 'first name only' | 'different'. `opts` switches the optional rules on.
    First father_check, with and without a leading honorific; the optional rules run only when
    it says 'different'."""
    ra, rb = _raw_words(a), _raw_words(b)
    if "placeholders" in opts and ((ra and all(w in PLACEHOLDERS for w in ra))
                                   or (rb and all(w in PLACEHOLDERS for w in rb))):
        return "missing"
    if not ra or not rb:
        return "missing"
    sa, sb = _strip_honorific(ra), _strip_honorific(rb)
    tries = {(" ".join(ra), " ".join(rb)), (" ".join(sa), " ".join(rb)),
             (" ".join(ra), " ".join(sb)), (" ".join(sa), " ".join(sb))}
    results = [father_check(x, y) for x, y in tries if x and y]
    for label in ("same", "spelling variant", "initial or dropped word"):
        if label in results:
            return label
    if not sa or not sb:
        return "missing"
    wa, wb = _words(" ".join(sa)), _words(" ".join(sb))
    small, big = (wa, wb) if len(wa) <= len(wb) else (wb, wa)
    if _subset_v2(small, big, opts):
        return "initial or dropped word"
    if "span" in opts and _span_match(sa, sb):
        return "joined or split words"
    if "first_name" in opts and wa and wb and wa[0] not in FILLERS and len(wa[0]) >= 4 \
            and _word_match_v2(wa[0], wb[0], opts) == "word":
        return "first name only"
    return "different"


# ── blocking keys: records are compared only inside a block ──
_SKEL = str.maketrans({"V": "B", "T": "D", "J": "G", "C": "K", "F": "P"})


def skeleton(s) -> str:
    """Blocking key for fuzzy names: normalise, no spaces, the first letter plus the consonants after it,
    near consonants made the same (V->B, T->D, J->G, C->K, F->P), doubles collapsed.
    GURJIT and GURJEET, RAMVEER and RAMBEER, PRIYANKA and PRIYNKA get the same key."""
    n = normalise(s).replace(" ", "")
    if not n:
        return ""
    key = (n[0] + re.sub(r"[AEIOUYH]", "", n[1:])).translate(_SKEL)
    return re.sub(r"(.)\1+", r"\1", key)


def skeleton_sorted(s) -> str:
    """skeleton() with the words in sorted order, so word order does not split a block."""
    return skeleton(" ".join(sorted(_raw_words(s))))


def father_first_letter(s) -> str | None:
    """First letter of the father's name after a leading honorific, after normalise. None when missing."""
    words = _strip_honorific(_raw_words(s)) if isinstance(s, str) else []
    first = normalise(words[0]) if words else ""
    return first[:1] or None


# Twin check: the largest spelling distance at which two given names still count as one name.
# Set on known twin pairs and known same-person pairs: the normal name limit lets many twins
# through; this limit refuses most twins and few same-person pairs.
TWIN_SPELLING_MAX = 0.6
_TWIN_OPTS = frozenset({"abbrev", "prefix"})


def _given_partner(x: str, y: str) -> bool:
    """True when two words can be one given name: an initial, an abbreviation (KR, MOHD), one word
    the start of the other (5+ letters), or a close spelling (distance <= TWIN_SPELLING_MAX)."""
    if len(x) == 1 or len(y) == 1:
        return y.startswith(x) or x.startswith(y)
    if _word_match_v2(x, y, _TWIN_OPTS) == "initial":
        return True
    short, long = sorted((x, y), key=len)
    if len(short) >= 5 and long.startswith(short):
        return True
    return _dist(x, y) <= min(_limit_for((len(x) + len(y)) // 2), TWIN_SPELLING_MAX)


def given_names_differ(a, b) -> bool:
    """True when two student names look like two siblings (twins): after the words that both names
    share and the common filler words (KUMAR, SINGH, ...) are removed, each name keeps a word, and
    no kept word of one name is a partner (_given_partner) of a kept word of the other.
    Joined or split words (RAMKUMAR / RAM KUMAR) are one name."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb or "".join(wa) == "".join(wb):
        return False
    la = [w for w in wa if w not in wb]
    lb = [w for w in wb if w not in wa]
    if (len(la) > 1 or len(lb) > 1) and _word_match_v2("".join(la), "".join(lb), _TWIN_OPTS):
        return False
    la = [w for w in la if w not in FILLERS]
    lb = [w for w in lb if w not in FILLERS]
    if not la or not lb:
        return False
    return not any(_given_partner(x, y) for x in la for y in lb)


if __name__ == "__main__":
    # self-test: made-up names that show each spelling pattern
    father_cases = [
        ("GURMIT SINGH", "GURMEET SINGH", "spelling variant"),
        ("DASHRATH", "DASHARATH", "spelling variant"),
        ("SANJAY MANDAL", "SANJAY MONDAL", "spelling variant"),
        ("RAMVEER YADAV", "RAMBEER YADAV", "spelling variant"),
        ("PRADEEP KUMAR RAM", "PRADIP KUMAR RAM", "spelling variant"),
        ("MOHEN PATEL", "MOHAN PATEL", "spelling variant"),
        ("LAXMI", "LAKSHMI", "spelling variant"),
        ("KUMAR NAIK KH", "KH KUMARA NAIK", "spelling variant"),
        ("S RAMA RAO", "SURESH RAMA RAO", "initial or dropped word"),
        ("K KRISHNA REDDY", "KAMAL KRISHNA REDDY", "initial or dropped word"),
        ("KALUBHAI", "KALUBHAI PATEL", "initial or dropped word"),
        ("RATHOD RAVIDNER NAIK", "RATHOD RAVINDER", "initial or dropped word"),
        ("PRADEEP KUMAR", "PRADEEP SAXENA", "different"),
        ("SUNIL KUMAR", "SANTOSH SHARMA", "different"),
        ("RAJ KUMAR", "RAJKUMAR", "same"),
    ]
    bad = 0
    for a, b, want in father_cases:
        got = father_check(a, b)
        flag = "" if got == want else "   <-- expected " + want
        bad += got != want
        print(f"{a + ' / ' + b:<46}{name_distance(a, b):6.2f}{name_limit(a, b):6.1f}  {got}{flag}")
    for a, b, want in [("SUMIT RANJAN SINGH", "MOHIT RANJAN SINGH", False), ("PRIYANKA", "PRIYNKA", True)]:
        got = same_name(a, b)
        bad += got != want
        print(f"student name {a} / {b}: same_name={got}" + ("" if got == want else f"   <-- expected {want}"))
    v2_cases = [
        ("BIJAY KR SINGH", "BIJAY KUMAR SINGH", "initial or dropped word"),
        ("NIRMAL CH DAS", "NIRMAL CHANDRA DAS", "initial or dropped word"),
        ("MOHD ASHRAF", "MOHAMMAD ASHRAF KHAN", "initial or dropped word"),
        ("NAZIR AH KHAN", "NAZIR AHMAD KHAN", "initial or dropped word"),
        ("HINDUSINGH", "HINDU SINGH RATHORE", "initial or dropped word"),   # prefix: HINDU starts HINDUSINGH
        ("REDDY SOMESWARARAO", "SOMESWARA RAO", "joined or split words"),
        ("MAHESH NEHRU PATIL", "MAHESH NEHRULAL PATIL", "initial or dropped word"),
        ("PARBATBHAI", "SOLANKI PARBAT RAMABHAI", "initial or dropped word"),
        ("FARMER", "BISWANATH ROY", "missing"),
        ("VIRENDRA KUMAR", "VIRENDRA YADAV", "first name only"),
        ("SHRI RAMESH KUMAR", "RAMESH KUMAR", "same"),
        ("SUNIL KUMAR", "SANTOSH SHARMA", "different"),
        ("KUMAR SINGH", "KUMAR YADAV", "different"),
        # father_check accepts these; v2 must too
        ("SHRIRAM YADAV", "SHREE RAM YADAV", "spelling variant"),
        ("SHRI PRAKAS", "SHRIPRAKASH", "spelling variant"),
        ("MAHAKSINGH", "MAHAK SINGH", "same"),
        ("RAGGNU", "RAGGHU", "spelling variant"),
    ]
    for a, b, want in v2_cases:
        got = father_check_v2(a, b)
        bad += got != want
        print(f"v2 {a + ' / ' + b:<46}{got}" + ("" if got == want else f"   <-- expected {want}"))
    for a, b in [("GURMIT SINGH", "GURMEET SINGH"), ("RAMVEER YADAV", "RAMBEER YADAV"), ("PRIYANKA", "PRIYNKA"),
                 ("DASHRATH", "DASHARATH"), ("PRANJALBEN PATEL", "PATEL PRANJALBEN")]:
        same_key = skeleton(a) == skeleton(b) or skeleton_sorted(a) == skeleton_sorted(b)
        bad += not same_key
        print(f"block {a} / {b}: {skeleton(a)} {skeleton(b)} {skeleton_sorted(a)} {skeleton_sorted(b)}"
              + ("" if same_key else "   <-- expected the same block"))
    twin_cases = [
        ("SUMIT RANJAN SINGH", "MOHIT RANJAN SINGH", True),      # twins: other given name
        ("SAMEER PATIL", "SAMEER ANIL PATIL", False),            # dropped middle word
        ("KALYANI VIJAY JADHAV", "JADHAV KALYANI VIJAY", False), # other word order
        ("AMIT PRIYADARSHI", "AMIT PRIYADARSHEE", False),        # spelling variant
        ("PRIYANKA SHARMA", "PRIYNKA SHARMA", False),            # dropped vowel
        ("R KUMAR", "RAHUL KUMAR", False),                       # initial
        ("MOHD ASIF", "MOHAMMAD ASIF", False),                   # abbreviation
        ("RAMKUMAR YADAV", "RAM KUMAR YADAV", False),            # joined words
        ("ANJALI YADAV", "ANJANA YADAV", True),                  # close given names, still two names
    ]
    for a, b, want in twin_cases:
        got = given_names_differ(a, b)
        bad += got != want
        print(f"twin {a + ' / ' + b:<46}{got}" + ("" if got == want else f"   <-- expected {want}"))
    for f, want in [("SHRI RAMESH KUMAR", "R"), ("N RAMA RAO", "N"), (None, None), ("PHOOL SINGH", "F")]:
        got = father_first_letter(f)
        bad += got != want
        print(f"father first letter {f}: {got}" + ("" if got == want else f"   <-- expected {want}"))
    print("ALL PASS" if not bad else f"{bad} FAILED")
