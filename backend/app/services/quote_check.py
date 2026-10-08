"""Does the text an answer puts in quotation marks say what the source says?

The citation audit proves an authority exists. It cannot see a proposition
that is wrong while the citation is real, the error class professionals still
catch (Order 14, September). The most checkable form of a proposition is a
quotation: when an answer writes `Section 75(4) provides: "..."` or quotes a
judgment, the words can be compared with the stored text.

For each quotation of 8 words or more this finds the authority it is
attributed to (the nearest citation before it, or right after it in Levy's
bracket style) and the section named with it, then compares the words:

    verbatim   every fragment appears in the section
    close      the wording matches allowing for OCR and margin notes
    elsewhere  the words are in a neighbouring section, not the one cited
    amended    the words are in an Act that amended the cited one
    not_found  the cited section does not contain these words

Comparison is on letters and digits only, so the "anemployeewhoworks" text of a
squashed OCR scan still matches "an employee who works". Fuzzy matching uses
the share of the quotation's 8-letter runs found in the source: OCR noise and
margin notes keep that high, a paraphrase dressed as a quotation does not.
Never raises; anything it cannot check is left unchecked.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

MIN_WORDS = 8
MAX_QUOTES = 5
CLOSE = 0.6          # share of 8-letter runs present for "close"
GRAM = 8

# An opening quote follows a space, bracket, colon or line start and touches
# the first word; a closing one touches the last word. Pairing any two straight
# quotes read the text BETWEEN two quotations as one (measured on real answers).
_QUOTE = re.compile(r"(?:(?<=^)|(?<=[\s(\[:>—-]))[“\"](?=\S)([^“”\"\n]{30,1500}?)(?<=\S)[”\"](?=[\s.,;:)\]!?—-]|$)", re.M)
# Words that introduce a quotation of the authority just named.
_CUE = re.compile(r"\b(?:provides?|provided|states?|stated|reads?|says?|said|held|holds|holding|defines?|defined|means?|"
                  r"as follows|in these terms|in the following terms|put it|observed|noted|declares?|declared|"
                  r"enacts?|prescribes?|requires?|stipulates?)\b|:\s*(?:>\s*)?$", re.I)
_BLOCK = re.compile(r"(?:^|\n)((?:[ \t]*>[^\n]*(?:\n|$))+)")
_SECREF = re.compile(r"\b(?:sections?|ss?\.|articles?|art\.)\s*(\d{1,3}[A-Z]{0,2})(?:\s*\(\s*[0-9a-z]{1,4}\s*\))*", re.I)
_ELLIPSIS = re.compile(r"\.\s?\.\s?\.|…|\[[^\]]{0,80}\]")


def squash(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _grams(s: str) -> set[str]:
    return {s[i:i + GRAM] for i in range(max(0, len(s) - GRAM + 1))}


def match_score(quote: str, source: str) -> float:
    """1.0 for every fragment verbatim; otherwise the share of 8-letter runs found."""
    hay = squash(source)
    frags = [squash(f) for f in _ELLIPSIS.split(quote)]
    frags = [f for f in frags if len(f) >= 20]
    if not frags or not hay:
        return 0.0
    if all(f in hay for f in frags):
        return 1.0
    have = _grams(hay)
    want = set().union(*(_grams(f) for f in frags))
    return len(want & have) / len(want) if want else 0.0


def find_quotes(text: str) -> list[tuple[int, int, str]]:
    """(start, end, words) for every quotation of MIN_WORDS words or more."""
    out = []
    for m in _QUOTE.finditer(text):
        if len(m.group(1).split()) >= MIN_WORDS:
            out.append((m.start(), m.end(), m.group(1)))
    for m in _BLOCK.finditer(text):
        body = re.sub(r"(?m)^[ \t]*>[ \t]?", "", m.group(1)).strip()
        body = body.strip("“”\"")
        if len(body.split()) < MIN_WORDS:
            continue
        # A blockquote that holds a quoted string is one quotation, not two.
        out = [(s, e, w) for s, e, w in out if not (m.start(1) <= s < m.end(1))]
        if not any(s <= m.start(1) < e for s, e, _ in out):
            out.append((m.start(1), m.end(1), body))
    return sorted(out)[:MAX_QUOTES]


def _mentions(text: str, cite: dict) -> list[tuple[int, int]]:
    if cite["kind"] == "case" and "pos" in cite:
        start = max(0, cite["pos"] - len(cite.get("a") or ""))
        return [(start, cite.get("end", cite["pos"]))]
    name = cite.get("name") or cite.get("text") or ""
    return [(m.start(), m.end()) for m in re.finditer(re.escape(name), text)] if name else []


def _attribute(text: str, qs: int, qe: int, cites: list[dict], usable: list[bool]) -> tuple[int, str | None] | None:
    """The citation a quotation belongs to, and the section named with it.

    The quotation must be tied to the citation in the prose: right after it in
    Levy's bracket style ('..." [Employment Code Act, Section 77]'), or after
    it in the same paragraph, close by, with words that introduce a quotation
    ("Section 85(4) of the Act provides:", "the Supreme Court held:"). The
    nearest citation decides; when that is one Levy cannot check (an English
    case, an Act not in the library) the quotation is left alone rather than
    pinned on the next authority along. Measured on 600 production answers:
    without these rules most "not found" flags were draft wording, list items
    or Levy's own sentences near a citation, not quotations of it.
    """
    before, after = None, None
    for i, c in enumerate(cites):
        for ms, me in _mentions(text, c):
            if me <= qs and qs - me <= 200 and (before is None or qs - me < before[0]):
                before = (qs - me, i, ms, me)
            elif ms >= qe and ms - qe <= 15 and re.fullmatch(r"[\s.,;:]*[\[(]?", text[qe:ms]):
                if after is None or ms - qe < after[0]:
                    after = (ms - qe, i, ms, me)
    if after:
        _, i, ms, me = after
        lo, hi = qe, min(len(text), me + 40)
    elif before:
        _, i, ms, me = before
        between = text[me:qs]
        if re.search(r"\n\s*\n|^\s*-{3,}", between, re.M) or not _CUE.search(between):
            return None
        lo, hi = max(0, ms - 60), qs
    else:
        return None
    if not usable[i]:
        return None
    if cites[i]["kind"] != "statute":
        return i, None
    refs = list(_SECREF.finditer(text, lo, hi))
    if not refs:
        return i, None
    near = refs[-1] if hi == qs else refs[0]
    return i, near.group(1).upper()


# ── source text ──────────────────────────────────────────────────────────────

def _neighbours(section: str) -> list[str]:
    m = re.match(r"(\d+)", section)
    if not m:
        return [section]
    n = int(m.group(1))
    return [section] + [str(k) for k in range(max(1, n - 3), n + 4) if str(k) != section]


@lru_cache(maxsize=64)
def _fetch_sections(doc_id: str, sections: tuple[str, ...]) -> tuple[tuple[str, str, str], ...]:
    """(section, part, text) for the sections asked for."""
    from ..db.supabase import get_db
    rows = (get_db().table("legal_chunks").select("content,metadata").eq("document_id", doc_id)
            .in_("metadata->>section_number", list(sections)).execute().data) or []
    return tuple((str((r.get("metadata") or {}).get("section_number") or ""),
                  str((r.get("metadata") or {}).get("part_number") or ""), r.get("content") or "") for r in rows)


@lru_cache(maxsize=32)
def _fetch_document(doc_id: str) -> str:
    from ..db.supabase import get_db
    rows = (get_db().table("legal_chunks").select("content,chunk_index").eq("document_id", doc_id)
            .order("chunk_index").limit(400).execute().data) or []
    return "\n".join(r.get("content") or "" for r in rows)


def _amending(doc_id: str) -> list[dict]:
    from . import law_map
    return [a for a in (law_map.entry(doc_id).get("amended_by") or []) if a.get("id")][:4]


def check_statute_quote(quote: str, doc_id: str, section: str, fetch_sections=None, fetch_document=None,
                        amending=None) -> dict:
    fetch_sections = fetch_sections or _fetch_sections
    fetch_document = fetch_document or _fetch_document
    amending = amending if amending is not None else _amending
    rows = [r if len(r) == 3 else (r[0], "", r[1]) for r in fetch_sections(doc_id, tuple(_neighbours(section)))]
    # Every chunk carrying this number counts: the arrangement of sections,
    # the section itself, and in Acts that bundle their court rules, rule N of
    # an Order. Words in none of them are not in "section N" of this document.
    cited = "\n".join(t for s, _, t in rows if s == section)
    if len(squash(cited)) >= 120:
        score = match_score(quote, cited)
        if score == 1.0:
            return {"status": "verbatim"}
        if score >= CLOSE:
            return {"status": "close"}
    for other in {s for s, _, _ in rows if s != section}:
        text = "\n".join(t for s, _, t in rows if s == other)
        if match_score(quote, text) >= CLOSE:
            return {"status": "elsewhere", "found_in": other}
    for a in amending(doc_id):
        if match_score(quote, fetch_document(a["id"])) >= CLOSE:
            return {"status": "amended", "amending_act": a.get("title")}
    if len(squash(cited)) < 120:
        return {"status": "unchecked"}   # the section's text is not in the library to compare
    return {"status": "not_found"}


def check_case_quote(quote: str, doc_id: str, fetch_document=None) -> dict:
    text = (fetch_document or _fetch_document)(doc_id)
    if len(squash(text)) < 500:
        return {"status": "unchecked"}
    score = match_score(quote, text)
    return {"status": "verbatim" if score == 1.0 else "close" if score >= CLOSE else "not_found"}


def check_quotes(text: str, cites: list[dict], rows: list[dict | None], **fetchers) -> dict[int, list[dict]]:
    """Quotation verdicts keyed by the index of the citation each is attributed to."""
    out: dict[int, list[dict]] = {}
    try:
        quotes = find_quotes(text)
        if not quotes:
            return out
        usable = [bool(r) for r in rows]
        for qs, qe, words in quotes:
            hit = _attribute(text, qs, qe, cites, usable)
            if not hit:
                continue
            i, section = hit
            doc_id = rows[i]["id"]
            if cites[i]["kind"] == "statute":
                if not section:
                    continue
                verdict = check_statute_quote(words, doc_id, section, **{k: v for k, v in fetchers.items()
                                                                        if k in ("fetch_sections", "fetch_document", "amending")})
                verdict["section"] = section
            else:
                verdict = check_case_quote(words, doc_id, fetchers.get("fetch_document"))
            if verdict["status"] == "unchecked":
                continue
            verdict["quote"] = " ".join(words.split())[:160]
            out.setdefault(i, []).append(verdict)
    except Exception:  # noqa: BLE001 - a check that fails says nothing
        return out
    return out
