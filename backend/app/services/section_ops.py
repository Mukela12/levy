"""What an amending Act does to each section of its principal Act.

The law map knows whole Acts: repealed, in force, pending. It had no idea that
section 9 of the Immigration and Deportation (Amendment) Act No. 19 of 2016
reads "The principal Act is amended by the repeal of section twenty-four", so
Levy answered a business-permit question from section 24 of the 2010 Act ten
years after it stopped being law. A general model with web search caught it
in the first benchmark run; we held the amending Act and did not.

This module reads one amending Act's text and says, per section: repealed,
repealed and replaced, amended, or inserted. It never touches the database, so
it can be tested on the clauses as they really appear.

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
    margin note, rather than guessing from half of it.
    """
    tokens = re.findall(r"[A-Za-z]+-?|\d{1,3}[A-Z]{0,2}\.?|[,;:]", window.replace("—", " "))
    groups: list[list[str]] = []
    current: list[str] = []
    last = None
    margins: list[str] = []
    suffix = ""
    dangling = False
    digits_first: list[str] = []

    def close() -> None:
        nonlocal current, last
        if current:
            groups.append(current)
        current, last = [], None

    for i, tok in enumerate(tokens):
        low = tok.lower().rstrip(".")
        d = _REF_DIGITS.match(tok)
        if d:
            nxt = tokens[i + 1].lower() if i + 1 < len(tokens) else ""
            # "9. The principal Act is amended" is the amending Act's own
            # section number, wherever it lands. Taken as margin evidence it
            # turned "section twenty- Repeal of 9. The principal Act" into a
            # repeal of section 9, which never happened.
            if tok.endswith(".") and nxt == "the":
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
            if last is not None and ((k == "tens" and last in {"unit", "tens"})
                                     or (k == "unit" and last == "unit")):
                close()
            current.append(base)
            last = k
            dangling = low.endswith("-")
            continue
        if (current or groups) and _SUFFIX.match(tok):
            suffix = tok
            break
        if tok == "," or low == "and":
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


def extract_ops(text: str) -> list[dict]:
    """Operations one chunk of an amending Act performs on its principal Act.

    Each op: {"op", "kind": "section"|"part", "target", "confidence", "evidence"}.
    Confidence is "high" when the body and the margin note agree, "medium" when
    only one of them could be read.
    """
    t = re.sub(r"\s+", " ", text or "")
    out: list[dict] = []

    def add(op: str, kind: str, target: str, conf: str, ev: str) -> None:
        target = target.upper() if kind == "part" else target.upper().lstrip("0") or "0"
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
