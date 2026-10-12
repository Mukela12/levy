"""What an amending Act does to each section of its principal Act.

The law map knows whole Acts: repealed, in force, pending. It had no idea that
section 9 of the Immigration and Deportation (Amendment) Act No. 19 of 2016
reads "The principal Act is amended by the repeal of section twenty-four", so
Levy answered a business-permit question from section 24 of the 2010 Act ten
years after it stopped being law. A general model with web search caught it
in the first benchmark run; we held the amending Act and did not.

This module reads one amending Act's text and says, per section: repealed,
repealed and replaced, amended, or inserted. It never touches the database, so
it can be tested on the clauses as they really appear. Parts and Schedules are
read too, as their own kinds, and the Constitution's Articles as its sections.

How they really appear is the hard part. Parliament's PDFs carry a margin note
beside every section ("Repeal of section 24"), and extraction splices it into
the body mid-number:

    repeal of section twenty- Repeal of 9. The principal Act is amended by the
    repeal of section twenty- section 24 four.

Each clause also appears twice per chunk, and some text lost its spaces
("Sectionfouroftheprincipal Actisamended"). So a number is read from every
occurrence of a clause, splice words are stepped over, a digit found inside a
spelled-out number is kept as the margin's evidence, and a spelled number that
ends on a dangling hyphen is discarded as cut off rather than guessed at.

The distinction that matters most: "repeal of section 77 and the substitution
therefor of the following" means section 77 still exists with new wording.
Calling that "repealed" would tell the model a live section is dead, which is
the same kind of error this exists to prevent.
"""
from __future__ import annotations

import re

_UNITS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_NUMBER_WORDS = set(_UNITS) | set(_TENS) | {"hundred"}
# Longest first, so "fourteen" is not read as "four" + "teen" in squashed text.
_VOCAB = sorted(_NUMBER_WORDS, key=len, reverse=True)

# Words the margin note splices into a clause. Stepping over these is what lets
# "section three Repeal and hundred and sixty seven" read as 367.
_SPLICE = {
    "repeal", "repealand", "repealof", "replacement", "amendment", "insertion",
    "of", "section", "sections", "and", "substitution",
}
# Everything after one of these belongs to the next sentence, not the number.
_STOP = {"the", "principal", "act", "is", "are", "amended", "by", "in", "subsection",
         "paragraph", "immediately", "following", "therefor", "new", "with", "to"}

_REF_DIGITS = re.compile(r"^(\d{1,3})([A-Z]{0,2})\.?$")
_SUFFIX = re.compile(r"^[A-H]$")

OPS = ("repealed", "replaced", "amended", "inserted")


def words_to_int(words: list[str]) -> int | None:
    """["three", "hundred", "sixty", "seven"] -> 367. None if any word is not a number."""
    total = current = 0
    seen = False
    for raw in words:
        w = raw.lower().strip("-.,;:")
        if not w or w == "and":
            continue
        if w in _UNITS:
            current += _UNITS[w]
        elif w in _TENS:
            current += _TENS[w]
        elif w == "hundred":
            current = (current or 1) * 100
        else:
            return None
        seen = True
    return total + current if seen else None


def split_squashed(blob: str) -> list[str] | None:
    """ "sixtyfour" -> ["sixty", "four"], or None if it is not all number words."""
    out, i, s = [], 0, blob.lower().replace("-", "")
    while i < len(s):
        for w in _VOCAB:
            if s.startswith(w, i):
                out.append(w)
                i += len(w)
                break
        else:
            return None
    return out or None


def _kind(word: str) -> str:
    return "hundred" if word == "hundred" else "tens" if word in _TENS else "unit"


def read_refs(window: str) -> tuple[list[str], list[str]]:
    """Every section number at the start of `window`, and any margin digits seen.

    Reads lists as well as single numbers: "thirty- sections 31 and 32 one and
    thirty-two" is sections 31 and 32, not one number, and summing it gave a
    repeal of section 63 that never happened. A new number starts where the
    words say so: a tens word after a units word ("thirty-one thirty-two"), or
    a units word after a units word.

    Returns ([], margins) when the number was cut off by a line break or a
    margin note, rather than guessing from half of it. "one hundred and 7. The
    principal Act" is cut off too: it read as section 100 (Mines and Minerals
    (Amendment) Act, 1997, whose next copy says "one hundred and eight").
    "seventy-eighty" is OCR for one number, not a list of two.
    """
    tokens = re.findall(r"[A-Za-z]+-?|\d{1,3}[A-Z]{0,2}\.?|[,;:]", window.replace("—", " "))
    groups: list[list[str]] = []
    current: list[str] = []
    last = None
    margins: list[str] = []
    suffix = ""
    dangling = False
    hundred_and = False
    skip: set[int] = set()
    digits_first: list[str] = []

    def close() -> None:
        nonlocal current, last
        if current:
            groups.append(current)
        current, last = [], None

    for i, tok in enumerate(tokens):
        if i in skip:
            continue
        low = tok.lower().rstrip(".")
        d = _REF_DIGITS.match(tok)
        if d:
            nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
            nxt2 = tokens[i + 2].lower() if i + 2 < len(tokens) else ""
            # "9. The principal Act is amended" is the amending Act's own
            # section number, wherever it lands. Taken as margin evidence it
            # turned "section twenty- Repeal of 9. The principal Act" into a
            # repeal of section 9, which never happened. "2. (1) The
            # principal Act" is the same, with its first subsection.
            if tok.endswith(".") and nxt == "the":
                continue
            if tok.endswith(".") and nxt == "1" and nxt2 == "the":
                skip.add(i + 1)
                continue
            ref = d.group(1) + d.group(2)
            if not groups and not current:
                # Digits before any words are the reference itself, and a list
                # of them ("303, 304 and 306") is handled by _list_refs.
                digits_first.append(ref)
                if not tok.endswith(".") and nxt in {",", "and", "to"}:
                    continue
                break
            margins.append(ref)
            continue
        base = low.rstrip("-")
        if base in _NUMBER_WORDS:
            k = _kind(base)
            if dangling and k != "unit":
                # A hyphen joins a tens word to a unit; "seventy-eighty"
                # (Income Tax (Amendment) Act, 1997, margin "section 78") is
                # neither 70 and 80 nor anything else we can read.
                return [], margins
            if last is not None and ((k == "tens" and last in {"unit", "tens"})
                                     or (k == "unit" and last == "unit")):
                close()
            current.append(base)
            last = k
            dangling = low.endswith("-")
            hundred_and = False
            continue
        if (current or groups) and _SUFFIX.match(tok):
            suffix = tok
            break
        if tok == "," or low == "and":
            if low == "and" and current and current[-1] == "hundred":
                hundred_and = True
            continue
        if low in _SPLICE:
            continue
        # Anything else — "the", "principal", "of subsection", a margin
        # title word — ends the reference.
        break
    close()

    if digits_first:
        return digits_first, margins
    numbers = [words_to_int(g) for g in groups]
    numbers = [n for n in numbers if n is not None]
    if not numbers:
        return [], margins
    dangling = dangling or hundred_and
    if dangling and margins:
        # "twenty-" with nothing after it, but the margin said which.
        return margins, margins
    if dangling:
        numbers = numbers[:-1]
        if not numbers:
            return [], margins
    refs = [str(n) for n in numbers]
    if suffix and len(refs) == 1:
        refs = [refs[0] + suffix]
    return refs, margins


def read_ref(window: str) -> tuple[str | None, list[str]]:
    """The first section number at the start of `window`. See read_refs."""
    refs, margins = read_refs(window)
    return (refs[0] if refs else None), margins


def _list_refs(window: str) -> list[str]:
    """ "303, 304, 305 and 306" -> all four; ranges written "53 to 58" expand."""
    m = re.match(r"\s*((?:\d{1,3}[A-Z]{0,2})(?:\s*(?:,|and|to)\s*\d{1,3}[A-Z]{0,2})+)", window)
    if not m:
        return []
    listed = m.group(1)
    # "repeal of sections 11, 6. The principal Act is amended by the repeal of
    # sections 11, 12 and 13": the "6." after a comma is the amending Act's own
    # next section, spliced in by the margin. A list that really ends there
    # ends with "and 13." instead. (ZLDC (Amendment) Act 2019, read 8 Oct 2026.)
    spliced = re.search(r",\s*\d{1,3}[A-Z]{0,2}$", listed)
    if spliced and re.match(r"\.\s+(?:The|Section)\b", window[m.end():]):
        listed = listed[:spliced.start()]
        if not re.search(r"(?:,|and|to)\s*\d", listed):
            return []
    parts = re.findall(r"\d{1,3}[A-Z]{0,2}|to", listed)
    out: list[str] = []
    for i, p in enumerate(parts):
        if p == "to" and out and i + 1 < len(parts) and parts[i + 1].isdigit() and out[-1].isdigit():
            out.extend(str(x) for x in range(int(out[-1]) + 1, int(parts[i + 1])))
        elif p != "to":
            out.append(p)
    return out


_ROMAN = r"[IVXL]+[A-Z]?"
_PART_REF = re.compile(rf"parts?\s+({_ROMAN}(?:\s*(?:,|and|to)\s*{_ROMAN})*)", re.I)
_REPEAL = re.compile(r"repeal\s*of\s*(sections?|parts?)\b", re.I)
_SUBSTITUTED = re.compile(
    r"substitution\s*therefor|substituted\s*therefor|repeal\s*and\s*replacement|"
    r"repealed\s*and\s*replaced|replacement\s*of\s*(?:section|part)", re.I)
# "Section 6(1) of the principal Act is amended", "Section 23 (2)(c) of ...":
# the subsection sits between the number and "of". Most 2021-2026 amending
# Acts are drafted this way, and 24 of them read as changing nothing.
_SUBREF = r"(?P<sub>(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*)"
_AMENDED = re.compile(
    r"\bsections?\s+(?P<ref>(?:[a-z]+[\s-]+){0,5}?[a-z]+-?|\d{1,3}[A-Z]{0,2})"
    r"(?P<suf>\s+[A-H])?" + _SUBREF + r"\s+of\s+the\s+principal\s+act\s+(?:is|are)\s+(?:hereby\s+)?amended", re.I)
# "4. Section ninety-seven is amended": bare form, only right after an
# amending section's own number, so a consequential "section 5 of the
# Companies Act is amended" inside the text is not taken for the principal.
_AMENDED_BARE = re.compile(
    r"\d+\.\s+sections?\s+(?P<ref>(?:[a-z]+[\s-]+){0,5}?[a-z]+-?|\d{1,3}[A-Z]{0,2})"
    r"(?P<suf>\s+[A-H])?" + _SUBREF + r"\s+(?:is|are)\s+(?:hereby\s+)?amended", re.I)
_REPEALED_FORM = re.compile(
    r"\bsections?\s+(?P<ref>(?:[a-z]+[\s-]+){0,5}?[a-z]+-?|\d{1,3}[A-Z]{0,2}(?:\s*(?:,|and)\s*\d{1,3}[A-Z]{0,2})*)"
    + _SUBREF + r"\s+of\s+the\s+principal\s+act\s+(?:is|are)\s+(?:hereby\s+)?repealed(?P<rep>\s+and\s+replaced)?", re.I)
_AMENDED_SQUASHED = re.compile(r"section([a-z-]+?|\d{1,3}[a-z]?)(?:\([0-9a-z]{1,4}\))*oftheprincipalact(?:is|are)amended")
# "The principal Act is amended by the deletion of section 7": a repeal in
# other words, or a replacement when new wording is substituted.
# Only when the clause ends at the number or goes on to substitute: the OCR
# splices the margin note into the sentence, so "is amended by the deletion
# of subsection (2)" arrives as "... deletion of section 14 of subsection (2)",
# and four live sections were read as repealed that way.
_DELETION = re.compile(
    r"principal\s+act\s+is\s+(?:hereby\s+)?amended\s+by\s+the\s+deletion\s+of\s+sections?\s+"
    r"(?P<ref>\d{1,3}[A-Z]{0,2})(?=\s*(?:[.;:]|and\s+the\s+substitution|and\s+substituting))", re.I)
_INSERTED = re.compile(
    r"insertion[^.]{0,120}?(?:new\s+)?sections?\s*(\d{1,3}[A-Z]{1,2})\b|"
    r"insertion\s+of\s+sections?\s*(\d{1,3}[A-Z]{1,2})\b", re.I)
_MARGIN = re.compile(
    r"(?:repeal|amendment|insertion|replacement)\w*\s+(?:and\s+replacement\s+)?of\s+"
    r"sections?\s*(\d{1,3}[A-Z]{0,2})\b", re.I)

# "2. The principal Act is amended in section ten, by—" and "amended in
# subsection (2) of section Amendment thirty-four": the section is named after
# the verb. Older Acts (High Court, Supreme Court, English Law 2002, VAT 2010,
# Criminal Procedure Code 1997) are drafted this way and read as changing
# nothing. Only the reference right after "in section" is read: "in section
# forty by the deletion of section 40 of subsection (1)" amends section 40.
_AMENDED_IN = re.compile(
    r"\bthe\s+principal\s+act\s+is\s+(?:hereby\s+)?amended\s*,?\s*(?:[—–-]+\s*)?(?:\(\s*a\s*\)\s*)?in\s+"
    r"(?:sub-?section\s*\(\s*[0-9a-z]{1,4}\s*\)(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*\s+of\s+)?sections?\s+", re.I)
# "the deletion of section replacement eight and the substitution therefor":
# the number spelled out, or with the margin note ("Repeal and replacement",
# "Amendment of section 13") spliced around it. Only number words, digits and
# margin words may stand between "section" and "substitution therefor", so
# "deletion of section 14 of subsection (2) and the substitution" (a margin
# spliced into a subsection amendment) can never match.
_DEL_WORDS = "|".join(sorted(_NUMBER_WORDS | {"repeal", "replacement", "amendment", "and", "of",
                                              "section", "sections"}, key=len, reverse=True))
_DELETION_SPLICED = re.compile(
    r"principal\s+act\s+is\s+(?:hereby\s+)?amended\s+by\s+the\s+deletion\s+of\s+sections?\s+"
    rf"(?P<ref>(?:(?:(?:{_DEL_WORDS})\b|\d{{1,3}}[A-Z]{{0,2}}\b)[\s,-]*){{1,10}}?)"
    r"(?:(?P<sub>(?:and\s+)?(?:the\s+)?substitution\s+therefor|and\s+substituting)|(?P<end>[.;](?=\s|$)))", re.I)
# "insertion, immediately after section eight, of the following new section:
# 9. The Minister may" (Fees and Fines (Amendment) Act, 2013). The new number
# is taken from the text only when it follows the one named: 11A after eleven,
# or 9 after eight with the section's own words after it.
_INSERT_AFTER = re.compile(
    r"\b(?:insertion|addition)\b[^.;]{0,80}?\bafter\s+section\s+(?P<after>[^,;:.()]{1,40}?)\s*,?\s+"
    r"of\s+the\s+following\s+new\s+sections?\b", re.I)
_NEW_NUMBER = re.compile(r"\b(\d{1,3})\s?([A-Z]{1,2})?\b(\.)?")

# Schedules. "The Second Schedule to the principal Act is amended", "the repeal
# of the Second Repeal and Schedule and the substitution therefor": eight of
# the 25 amending Acts read as changing nothing changed only a Schedule (Road
# Traffic licence taxes 2010 and 2021, emoluments, customs tariffs). Recorded
# as kind "schedule", target "SECOND SCHEDULE" or "SCHEDULE" for an Act's only
# one, so they never touch a section's status.
_ORDINALS = {
    "first": "FIRST", "second": "SECOND", "third": "THIRD", "fourth": "FOURTH", "fifth": "FIFTH",
    "sixth": "SIXTH", "seventh": "SEVENTH", "eighth": "EIGHTH", "ninth": "NINTH", "nineth": "NINTH",
    "tenth": "TENTH", "eleventh": "ELEVENTH", "twelfth": "TWELFTH", "thirteenth": "THIRTEENTH",
    "fourteenth": "FOURTEENTH", "fifteenth": "FIFTEENTH", "sixteenth": "SIXTEENTH",
    "seventeenth": "SEVENTEENTH", "eighteenth": "EIGHTEENTH", "nineteenth": "NINETEENTH",
    "twentieth": "TWENTIETH", "charging": "CHARGING",
}
_ORD = "|".join(sorted(_ORDINALS, key=len, reverse=True))
_SCHEDULE_AMENDED = re.compile(
    rf"\b(?:(?P<ords>(?:{_ORD})(?:\s*(?:,|and)\s*(?:{_ORD}))*)\s+|the\s+)schedules?\s+(?:to|of)\s+the\s+"
    r"principal\s+act\s+(?:is|are)\s+(?:hereby\s+)?amended", re.I)
_SCHEDULE_REPEAL = re.compile(
    r"principal\s+act\s+is\s+(?:hereby\s+)?amended\s+by\s+the\s+"
    r"(?P<how>repeal\s+and\s+replacement|repeal|deletion|replacement)\s+(?:(?:repeal|replacement|amendment|and)\s+){0,3}"
    r"of\s+the\s+"
    rf"(?P<body>(?:(?:(?:{_ORD}|repeal|replacement|amendment|of|and)\b|,)\s*){{0,8}}?)schedules?\b"
    rf"(?P<more>(?:\s*(?:,|and)\s*(?:the\s+)?(?:{_ORD})\s+schedules?\b)*)", re.I)

# The Constitution numbers Articles, not sections, and is amended in its own
# words: "Article 47 of the Constitution is amended", "The Constitution is
# amended by the repeal of Article 68 ... and the substitution therefor"
# (Constitution of Zambia (Amendment) Act, 2025). Single Articles only: the
# 2016 amending Acts repeal "Articles 62 to 78 inclusive" of a text the
# library holds already amended by them, and reading those would mark the
# Constitution in force as dead.
_ARTICLE_AMENDED = re.compile(
    r"\barticle\s+(?P<ref>\d{1,3}[A-Z]?)" + _SUBREF + r"\s+of\s+the\s+constitution\s+is\s+(?:hereby\s+)?amended", re.I)
_ARTICLE_REPEAL = re.compile(
    r"\bconstitution\s+is\s+(?:hereby\s+)?amended\s+by\s+the\s+repeal\s+of\s+article\s+(?P<ref>\d{1,3}[A-Z]?)\b"
    r"(?!\s*(?:,|and|to)\s*\d)", re.I)

# Parts named before the verb ("3. Part IV of the principal Act is repealed.",
# Zambia National Broadcasting Corporation (Amendment) Act, 2017) and new
# Parts ("insertion of the following new part: new part VIA"). The numeral is
# matched case-sensitively, or "new part in" would read as Part IN.
_ROMAN_CS = r"(?-i:[IVXL]+[A-Z]?)"
_PART_NAMED = re.compile(
    rf"\bparts?\s+(?P<ref>{_ROMAN_CS}(?:\s*(?:,|and)\s*{_ROMAN_CS})*)\s+of\s+the\s+principal\s+act\s+"
    r"(?:is|are)\s+(?:hereby\s+)?(?P<verb>repealed(?:\s+and\s+replaced)?|amended)", re.I)
_PART_INSERTED = re.compile(
    rf"\binsertion\b[^.;]{{0,80}}?\bnew\s+part\b[\s:]*(?:new\s+part\s+)?(?P<ref>{_ROMAN_CS})\b", re.I)
_NEXT_CLAUSE = r"\s\d+\.\s+(?:The|Section)\b"


def _schedules(text: str) -> list[str]:
    """ "First and Repeal and Second" -> ["FIRST SCHEDULE", "SECOND SCHEDULE"]; no ordinal -> ["SCHEDULE"]."""
    out: list[str] = []
    for w in re.findall(rf"\b(?:{_ORD})\b", text or "", re.I):
        name = f"{_ORDINALS[w.lower()]} SCHEDULE"
        if name not in out:
            out.append(name)
    return out or ["SCHEDULE"]


def extract_ops(text: str) -> list[dict]:
    """Operations one chunk of an amending Act performs on its principal Act.

    Each op: {"op", "kind": "section"|"part"|"schedule", "target", "confidence",
    "evidence"}. Confidence is "high" when the body and the margin note agree,
    "medium" when only one of them could be read.
    """
    t = re.sub(r"\s+", " ", text or "")
    out: list[dict] = []

    def add(op: str, kind: str, target: str, conf: str, ev: str) -> None:
        target = target.upper() if kind in ("part", "schedule") else target.upper().lstrip("0") or "0"
        out.append({"op": op, "kind": kind, "target": target, "confidence": conf, "evidence": ev[:180]})

    margins_all = {m.group(1).upper() for m in _MARGIN.finditer(t)}

    for m in _REPEAL.finditer(t):
        kind = "part" if m.group(1).lower().startswith("part") else "section"
        after = t[m.end():m.end() + 200]
        # A replacement's wording follows within the same clause; the next
        # clause starts with its own number and "The principal Act".
        clause = re.split(r"\s\d+\.\s+(?:The|Section)\b", t[m.end():m.end() + 500])[0]
        op = "replaced" if _SUBSTITUTED.search(clause) else "repealed"
        if kind == "part":
            pm = _PART_REF.match("part " + after.lstrip())
            if pm:
                for ref in re.findall(_ROMAN, pm.group(1)):
                    add(op, "part", ref, "medium", t[m.start():m.start() + 160])
            continue
        listed = _list_refs(after)
        if listed:
            for ref in listed:
                add(op, "section", ref, "high", t[m.start():m.start() + 160])
            continue
        refs, margins = read_refs(after)
        # The margin often carries the whole list the body splits up:
        # "repeal of sections 11 Repeal of and 12. sections 11 and 12".
        for lm in re.finditer(r"sections\s+(\d{1,3}[A-Z]{0,2}(?:\s*(?:,|and|to)\s*\d{1,3}[A-Z]{0,2})+)", clause):
            for ref in _list_refs(lm.group(1)):
                if ref not in refs:
                    refs.append(ref)
                    margins.append(ref)
        seen_margin = margins_all | {x.upper() for x in margins}
        for ref in refs:
            agree = ref.upper() in seen_margin
            add(op, "section", ref, "high" if agree else "medium", t[m.start():m.start() + 160])

    # "15. Section 38 of the principal Act is repealed." — the other way the
    # same thing is drafted, with the section named before the verb.
    for m in _REPEALED_FORM.finditer(t):
        clause = re.split(r"\s\d+\.\s+(?:The|Section)\b", t[m.end():m.end() + 400])[0]
        op = "replaced" if (m.group("rep") or _SUBSTITUTED.search(clause)) else "repealed"
        if m.group("sub").strip():
            # "Section 7(1) ... is repealed" kills a subsection: the section
            # lives on, amended.
            op = "amended"
        refs, _ = read_refs(m.group("ref"))
        for ref in refs:
            conf = "high" if ref.upper() in margins_all else "medium"
            add(op, "section", ref, conf, t[m.start():m.start() + 160])

    for rx in (_AMENDED, _AMENDED_BARE):
        for m in rx.finditer(t):
            ref, _ = read_ref(m.group("ref"))
            if not ref:
                continue
            if m.group("suf") and not ref[-1].isalpha():
                ref += m.group("suf").strip()
            conf = "high" if ref.upper() in margins_all else "medium"
            add("amended", "section", ref, conf, t[m.start():m.start() + 160])

    squashed = re.sub(r"\s+", "", t).lower()
    for m in _AMENDED_SQUASHED.finditer(squashed):
        raw = m.group(1)
        if raw[0].isdigit():
            ref = raw.upper()
        else:
            words = split_squashed(raw)
            n = words_to_int(words) if words else None
            if n is None:
                continue
            ref = str(n)
        add("amended", "section", ref, "medium", m.group(0)[:160])

    for m in _DELETION.finditer(t):
        clause = re.split(r"\s\d+\.\s+(?:The|Section)\b", t[m.end():m.end() + 400])[0]
        op = "replaced" if _SUBSTITUTED.search(clause) else "repealed"
        ref = m.group("ref").upper()
        add(op, "section", ref, "high" if ref in margins_all else "medium", t[m.start():m.start() + 160])

    for m in _INSERTED.finditer(t):
        ref = (m.group(1) or m.group(2) or "").upper()
        if ref:
            add("inserted", "section", ref, "high", t[m.start():m.start() + 160])

    for m in _AMENDED_IN.finditer(t):
        refs, margins = read_refs(t[m.end():m.end() + 120])
        seen = margins_all | {x.upper() for x in margins}
        for ref in refs:
            add("amended", "section", ref, "high" if ref.upper() in seen else "medium",
                t[m.start():m.start() + 160])

    for m in _DELETION_SPLICED.finditer(t):
        raw = m.group("ref")
        refs, _ = read_refs(raw)
        words = [w for w in re.findall(r"[a-z]+", raw.lower()) if w in _NUMBER_WORDS]
        digits = [x.upper() for x in re.findall(r"\d{1,3}[A-Z]{0,2}", raw, re.I)]
        spelled = words_to_int(words) if words else None
        if not refs or (spelled is not None and digits and any(x != str(spelled) for x in digits)):
            continue    # the words and the margin's digits disagree: read neither
        if m.group("sub"):
            op = "replaced"
        else:
            # Deleted outright, which is a repeal. Only when the clause ends on
            # a number word that its own margin digits confirm ("deletion of
            # section section 40 forty."): "deletion of section two Repeal and
            # 2. The principal Act" ends on the amending Act's own number.
            last_word = raw.strip(" ,-").split()[-1].lower().split("-")[-1]
            if not (len(refs) == 1 and spelled is not None and digits and last_word in _NUMBER_WORDS):
                continue
            op = "repealed"
        for ref in refs:
            agree = ref.upper() in margins_all or (spelled is not None and digits and ref == str(spelled))
            add(op, "section", ref, "high" if agree else "medium", t[m.start():m.start() + 160])

    for m in _INSERT_AFTER.finditer(t):
        after, _ = read_refs(m.group("after"))
        am = re.match(r"(\d{1,3})([A-Z]{0,2})$", after[0]) if len(after) == 1 else None
        if not am:
            continue
        base, suf = int(am.group(1)), am.group(2)
        tail = t[m.end():m.end() + 100]
        for nm in _NEW_NUMBER.finditer(tail):
            n, s = int(nm.group(1)), nm.group(2) or ""
            if n == base and s and s > suf:
                ref = f"{n}{s}"
            elif (n == base + 1 and not s and not suf and nm.group(3)
                  and re.match(r"\s+(?!The\s+principal\b|Section\b)(?:\(1\)|[A-Z])", tail[nm.end():])):
                ref = str(n)
            else:
                continue
            add("inserted", "section", ref, "high" if ref in margins_all else "medium", t[m.start():m.start() + 160])
            break

    for m in _SCHEDULE_AMENDED.finditer(t):
        for name in _schedules(m.group("ords") or ""):
            add("amended", "schedule", name, "medium", t[m.start():m.start() + 160])

    for m in _SCHEDULE_REPEAL.finditer(t):
        clause = re.split(_NEXT_CLAUSE, t[m.end():m.end() + 400])[0]
        replaced = "replacement" in m.group("how").lower() or _SUBSTITUTED.search(m.group(0) + clause)
        op = "replaced" if replaced else "repealed"
        for name in _schedules(m.group("body") + " " + (m.group("more") or "")):
            add(op, "schedule", name, "medium", t[m.start():m.start() + 160])

    for m in _ARTICLE_AMENDED.finditer(t):
        add("amended", "section", m.group("ref"), "medium", t[m.start():m.start() + 160])
    for m in _ARTICLE_REPEAL.finditer(t):
        clause = re.split(_NEXT_CLAUSE, t[m.end():m.end() + 400])[0]
        add("replaced" if _SUBSTITUTED.search(clause) else "repealed", "section", m.group("ref"), "medium",
            t[m.start():m.start() + 160])

    for m in _PART_NAMED.finditer(t):
        clause = re.split(_NEXT_CLAUSE, t[m.end():m.end() + 400])[0]
        verb = m.group("verb").lower()
        op = ("amended" if verb == "amended" else
              "replaced" if "replaced" in verb or _SUBSTITUTED.search(clause) else "repealed")
        for ref in re.findall(r"[IVXL]+[A-Z]?", m.group("ref")):
            add(op, "part", ref, "medium", t[m.start():m.start() + 160])
    for m in _PART_INSERTED.finditer(t):
        add("inserted", "part", m.group("ref"), "medium", t[m.start():m.start() + 160])

    # One clause appears twice per chunk: keep the best-supported reading of each.
    rank = {"high": 2, "medium": 1}
    best: dict[tuple[str, str, str], dict] = {}
    for op in out:
        key = (op["op"], op["kind"], op["target"])
        if key not in best or rank[op["confidence"]] > rank[best[key]["confidence"]]:
            best[key] = op
    ops = list(best.values())
    # A section that is repealed-and-replaced reads "repeal of section 8" in
    # one copy of the clause and "substitution therefor" in the other: the
    # replacement wins, because the section still exists.
    replaced = {(o["kind"], o["target"]) for o in ops if o["op"] == "replaced"}
    ops = [o for o in ops if not (o["op"] == "repealed" and (o["kind"], o["target"]) in replaced)]
    # A section amended in its own clause is not also repealed by it.
    return ops


def normalise_section(ref: str | int | None) -> str | None:
    """ "s. 24", "section twenty-four", "24" and "24(1)(a)" -> "24"; "64 A" -> "64A"."""
    if ref is None:
        return None
    s = str(ref).strip()
    # Longest first: "s\.?" first stripped the "s" off "section" and left "ection 24".
    s = re.sub(r"^(?:sections|section|sec\.?|s\.?)\s*", "", s, flags=re.I)
    s = re.sub(r"\(.*$", "", s).strip()
    m = re.match(r"^(\d{1,3})\s*([A-Za-z]{0,2})\b", s)
    if m:
        return (m.group(1).lstrip("0") or "0") + m.group(2).upper()
    ref_, _ = read_ref(s)
    return ref_
