"""What the judgments in Levy's library say about the cases they cite.

Half of audited answers cite an authority Levy does not hold, and most of
those are leading cases the library's own judgments quote: Wilson Masauso
Zulu v Avondale Housing Project is cited by dozens of them, yet comes from the
Zambia Law Reports, which Levy deliberately does not ingest. Until now such a
citation could only be called "not in the library", the same verdict a
fabricated case gets.

`scripts/build_citator.py` reads every judgment, extracts the cases it cites
(with the audit's own conservative extractor), groups the spellings of one
case together, and writes `app/data/citator.json`. From it this module can say:

  * a case Levy does not hold is real: N judgments in the library cite it,
    and this is how they describe it;
  * a citation's year contradicts how those judgments cite the case;
  * a case was later reversed, departed from, or held per incuriam. These
    entries are reviewed by hand before they ship: keyword matching on
    "overrule" and "per incuriam" mostly finds counsel's arguments, dissents
    and quotations, and a wrong "overruled" is worse than none.

Grouping is precision first. A short form ("Zulu v The People") joins a fuller
name only when exactly one fuller name fits, and a year in the citation must
agree with the years the library's judgments give.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

CITATOR_PATH = Path(__file__).resolve().parent.parent / "data" / "citator.json"

# Words that do not identify a party.
STOP = {
    "the", "of", "and", "&", "limited", "ltd", "plc", "company", "co", "others", "other",
    "another", "anor", "ors", "zambia", "z", "a", "an", "in", "re", "inc", "corporation",
    "corp", "t/a", "ta", "mr", "mrs", "ms", "dr", "1", "2", "3", "4", "5",
}
# Parties that name nobody in particular: the case lives in the other party.
GENERIC = ({"people"}, {"attorney", "general"}, {"attorney"}, {"general"})

COURT_RANK = {"CCZ": 4, "SCZ": 4, "CAZ": 3, "HC": 2, "": 1}

# Footnote markers and OCR debris that end or begin a party name in a
# judgment's text: "The People® and Saidi Banda", "People4", "J8 Yokoniya".
_MARKS = re.compile(r"[®©™!?¹²³⁴⁵⁶⁷⁸⁹⁰’“”\"|]|(?<=[A-Za-z])\d+\b|\(\d{1,2}\)")
_PAGE_REF = re.compile(r"^(?:[JR]\d+\s+)+")
_LEADING = re.compile(r"^(?:and|in|see|the case of|case of|also)\s+", re.I)

ZR_CITE = re.compile(r"\(\s*((?:19|20)\d{2})(?:\s*[-/]\s*\d{1,4})?\s*\)\s*(?:\d\s*)?Z\.?\s*R\.?\s*(\d{1,4})")
ZR_BARE = re.compile(r"\b((?:19|20)\d{2})\s+Z\.?\s*R\.?\s*(\d{1,4})\b")
ZM_NEUTRAL = re.compile(r"\[\s*((?:19|20)\d{2})\s*\]\s*(ZM(?:SC|CA|HC|CC))\s*(\d{1,4})", re.I)
SCZ_NO = re.compile(r"\bS\.?C\.?Z\.?\s+(?:Judgment|Appeal)\s+No\.?\s*(\d{1,4})\s+of\s+((?:19|20)\d{2})", re.I)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def clean_party(raw: str, side: str) -> str:
    """Cut a party name free of footnote markers and neighbouring text."""
    text = _MARKS.sub("|", raw or "")
    parts = [p.strip(" ,.;:-") for p in text.split("|")]
    parts = [p for p in parts if p]
    if not parts:
        return ""
    party = parts[-1] if side == "a" else parts[0]
    party = _PAGE_REF.sub("", party)
    while True:
        cut = _LEADING.sub("", party)
        if cut == party:
            break
        party = cut
    return party.strip()


def tokens(party: str) -> frozenset[str]:
    return frozenset(w for w in _norm(party).split() if w not in STOP and len(w) > 1 and not w.isdigit())


def generic(toks: frozenset[str]) -> bool:
    return not toks or set(toks) in GENERIC


def report_cites(text: str) -> tuple[list[str], list[int]]:
    """Law-report and neutral citations in a short tail of text, and their years."""
    cites, years = [], []
    for m in ZR_CITE.finditer(text):
        cites.append(f"({m.group(1)}) ZR {m.group(2)}"); years.append(int(m.group(1)))
    for m in ZR_BARE.finditer(text):
        cites.append(f"({m.group(1)}) ZR {m.group(2)}"); years.append(int(m.group(1)))
    for m in ZM_NEUTRAL.finditer(text):
        cites.append(f"[{m.group(1)}] {m.group(2).upper()} {m.group(3)}"); years.append(int(m.group(1)))
    for m in SCZ_NO.finditer(text):
        cites.append(f"SCZ Judgment No. {m.group(1)} of {m.group(2)}"); years.append(int(m.group(2)))
    return list(dict.fromkeys(cites)), sorted(set(years))


def cited_years(cite: str) -> list[int]:
    """Years a citation in an answer gives: "(1982) ZR 172", "[1982]", "Appeal No. 2 of 2019"."""
    return sorted({int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", cite or "")})


def _same(t: str, u: str) -> bool:
    """Token equality tolerant of one-letter OCR drift (Yokonia / Yokoniya)."""
    if t == u:
        return True
    if min(len(t), len(u)) < 5 or abs(len(t) - len(u)) > 2:
        return False
    from difflib import SequenceMatcher
    return SequenceMatcher(None, t, u).ratio() >= 0.86


def subset(small: frozenset[str], big: frozenset[str]) -> bool:
    return all(any(_same(t, u) for u in big) for t in small)


def overlap(x: frozenset[str], y: frozenset[str]) -> int:
    return sum(1 for t in x if any(_same(t, u) for u in y))


def fits(a: frozenset[str], b: frozenset[str], case: dict) -> bool:
    """Is this name a shortening of the case's name (each party a subset)?"""
    ca, cb = frozenset(case["a"]), frozenset(case["b"])
    return bool(a and b) and subset(a, ca) and subset(b, cb)


def compatible(a: frozenset[str], b: frozenset[str], case: dict) -> bool:
    """Could this spelling be the same case, allowing for how judgments mangle names?

    Judgments shorten names ("Zulu v Avondale"), drift on first names
    ("William" for "Wilson Masauso Zulu"), and OCR glues neighbouring text on
    ("Attorney General> Wilson Masauso Zulu", "Housing Project Limitect").
    Against "The People" or the Attorney General the defendant's own name is
    all there is, so there only a strict shortening or extension counts.
    """
    ca, cb = frozenset(case["a"]), frozenset(case["b"])
    if not (a and b and ca and cb):
        return False
    if generic(cb) or generic(b):
        if not (subset(b, cb) or subset(cb, b)):
            return False
        return len(ca) >= 2 and len(a) >= 2 and (subset(a, ca) or subset(ca, a))
    side_a = subset(a, ca) or subset(ca, a) or overlap(a, ca) >= 2
    side_b = subset(b, cb) or subset(cb, b) or overlap(b, cb) >= 2
    return side_a and side_b


def distinctive(a: frozenset[str], b: frozenset[str]) -> bool:
    """Enough of a name to identify one case without a year."""
    return (len(a) + len(b) >= 3 and not (generic(b) and len(a) < 2)) or (not generic(a) and not generic(b))


# ── runtime ──────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _data() -> dict:
    try:
        return json.loads(CITATOR_PATH.read_text())
    except (OSError, ValueError):
        return {"cases": [], "judgments": {}}


@lru_cache(maxsize=1)
def _index() -> tuple[dict, dict]:
    by_token: dict[str, list[int]] = {}
    by_doc: dict[str, int] = {}
    for i, c in enumerate(_data().get("cases", [])):
        for t in set(c["a"]) | set(c["b"]):
            by_token.setdefault(t, []).append(i)
        if c.get("doc"):
            by_doc[c["doc"]] = i
    return by_token, by_doc


def judgment(doc_id: str) -> dict:
    return _data().get("judgments", {}).get(doc_id) or {}


def for_document(doc_id: str) -> dict | None:
    _, by_doc = _index()
    i = by_doc.get(doc_id)
    return _data()["cases"][i] if i is not None else None


def lookup(a: str, b: str, cite: str = "") -> dict | None:
    """The one case these party names and citation identify, or None.

    Returns {"case": <case>, "year_conflict": bool}. A year in the citation
    that no judgment in the library gives for the case is a conflict, not a
    match, and only a distinctive name is trusted to report one.
    """
    ta, tb = tokens(clean_party(a, "a")), tokens(clean_party(b, "b"))
    if not ta or not tb:
        return None
    cases = _data().get("cases", [])
    by_token, _ = _index()
    pool = {i for t in ta | tb for i in by_token.get(t, ())}
    hits = [cases[i] for i in pool if fits(ta, tb, cases[i]) or (distinctive(ta, tb) and compatible(ta, tb, cases[i]))]
    if not hits:
        return None
    hits.sort(key=lambda c: -c.get("n", 0))
    if len(hits) > 1 and hits[0].get("n", 0) >= 3 * max(1, hits[1].get("n", 0)) and not cited_years(cite):
        hits = hits[:1]   # one dominant case and some stray spellings of it
    years = cited_years(cite)
    if years:
        agree = [c for c in hits if set(years) & set(c.get("years") or [])]
        if len(agree) == 1:
            return {"case": agree[0], "year_conflict": False}
        if not agree and len(hits) == 1 and hits[0].get("years") and not (generic(ta) or generic(tb)) \
                and not generic(frozenset(hits[0]["b"])) and len(hits[0].get("cites") or []) >= 1:
            # Both parties named and the library's judgments agree on a report
            # citation: a different year in the answer is a wrong citation, not
            # another case. Against the State or the Attorney General a name can
            # recur, so no conflict is claimed there.
            return {"case": hits[0], "year_conflict": True}
        if not agree:
            undated = [c for c in hits if not c.get("years")]
            if len(undated) == 1 and len(hits) == 1 and distinctive(ta, tb):
                return {"case": undated[0], "year_conflict": False}
        return None
    if len(hits) == 1 and distinctive(ta, tb):
        return {"case": hits[0], "year_conflict": False}
    return None


def describe(case: dict, limit: int = 6) -> dict:
    """A case's record, with the citing judgments' names filled in."""
    js = _data().get("judgments", {})
    by = []
    for occ in (case.get("by") or [])[:limit]:
        j = js.get(occ["d"], {})
        by.append({"document_id": occ["d"], "judgment": j.get("t"), "court": j.get("c"), "year": j.get("y"),
                   "excerpt": occ["s"]})
    neg = []
    for n in case.get("neg") or []:
        j = js.get(n["d"], {})
        neg.append({"document_id": n["d"], "judgment": j.get("t") or n.get("t"), "court": j.get("c") or n.get("c"),
                    "year": j.get("y") or n.get("y"), "treatment": n["kind"], "extent": n.get("extent"),
                    "quote": n.get("quote")})
    return {"name": case["name"], "document_id": case.get("doc"), "citations": case.get("cites") or [],
            "years": case.get("years") or [], "cited_by_count": case.get("n", 0),
            "negative_treatment": neg, "cited_in": by}
