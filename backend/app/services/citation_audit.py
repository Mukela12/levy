"""Post-answer citation verification.

The retrieval pipeline guarantees that SOURCES shown under an answer came from
the corpus, but nothing checked the authorities NAMED IN THE PROSE. That prose
is exactly where a language model hallucinates: a confident "Zulu v The People
(1990-2) ZR 65" that was never retrieved. Courts in the region are sanctioning
lawyers for filing invented citations, so Levy's promise has to be checkable
per citation, not per answer.

After the final answer is written, this module extracts every legal citation
from the text and verifies each against the document library:

    verified   -> the cited authority IS in Levy's library; we attach the
                  document id so the client opens it in one click.
    not_found  -> we do not hold it. Shown honestly as unverified, with the
                  wording pointed at what the reader should do (verify before
                  relying), never dressed up as an error.

Design constraints:
  * Precision over recall. A false "verified" defeats the whole feature, so
    matching is conservative: exact-ish citation numbers, or both party names
    for cases, or the full statute name. Unmatched mentions that were not
    confidently parsed as citations are simply not audited.
  * One corpus title index per process, refreshed every 10 minutes, so the
    audit adds no per-citation database round trips.
"""

from __future__ import annotations

import re
import time
import unicodedata

_INDEX: list[dict] | None = None
_INDEX_AT = 0.0
_INDEX_TTL = 600.0


def _with_act(r: dict, title: str) -> str:
    """ "The Immigration and Deportation 2010" -> "... Deportation Act 2010".

    The parser cut "Act" off some library titles; without it a citation of
    the 2010 Act only matched the 1965 one.
    """
    if r.get("document_type") != "act" or not title or re.search(r"\b(?:act|code|constitution)\b", title, re.I):
        return title
    return re.sub(r"^(.*?)(\s*,?\s*(?:\((?:No|Cap)[^)]*\)|(?:19|20)\d{2}\b).*)?$", r"\1 Act\2", title.strip(), count=1)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _load_index() -> list[dict]:
    global _INDEX, _INDEX_AT
    if _INDEX is not None and time.time() - _INDEX_AT < _INDEX_TTL:
        return _INDEX
    from ..db.supabase import get_db
    db = get_db()
    rows: list[dict] = []
    off, step = 0, 1000
    while True:  # PostgREST caps a single select at 1000 rows
        # Public library only: a user's private upload must never verify, or
        # show its title under, somebody else's answer.
        page = (db.table("legal_documents")
                .select("id,title,short_name,document_type,year,act_number")
                .eq("is_global", True)
                .range(off, off + step - 1).execute().data) or []
        rows += page
        if len(page) < step:
            break
        off += step
    for r in rows:
        title, short = _with_act(r, r.get("title") or ""), _with_act(r, r.get("short_name") or "")
        r["_ntitle"] = _norm(title)
        r["_nshort"] = _norm(short)
        r["_btitle"], r["_bshort"] = _base(title), _base(short)
    _INDEX, _INDEX_AT = rows, time.time()
    return rows


# ── extraction ──────────────────────────────────────────────────────────────

# Case names are extracted by walking tokens around a " v " pivot rather than
# by regex: party names are arbitrary-length runs of capitalised words with
# connectors ("The People", "Zamtel v Felix Musonda And 29 Others"), and lazy
# regex quantifiers were measured truncating them ("Loreta" for "Loreta
# Kunda") or swallowing sentence prefixes ("In Cynthia Kunda").

_PIVOT = re.compile(r"\b(vs?\.?)\s", re.I)
_WORD = re.compile(r"[^\s]+")
_CONNECTORS = {"of", "and", "&", "the"}          # allowed inside a party name
_EDGE_STOP = {"in", "see", "eg", "e.g", "compare", "following", "applying",
              "authority", "leading", "case", "matter", "cf", "also", "under",
              "including", "cite", "cited", "held", "read", "per"}

# words that end a party name on the right: they begin the surrounding legal
# prose, not the litigant ("... v Loretta Kunda Court of Appeal Case No...")
_RIGHT_STOP = {"court", "appeal", "case", "no", "judgment", "held", "decided",
               "supra", "ibid", "the", "scz", "caz", "ccz", "app", "ruling",
               "selected", "supreme", "constitutional", "high", "industrial",
               "subordinate", "lord", "per", "in", "at", "on", "is", "was", "were",
               "that", "this", "what", "which", "where", "when"}

# Heading and prose words that never begin, or make up, a litigant's name.
# The second live week produced "FULL LEGAL ANALYSIS Kumwenda v Zimco", "1 Care
# International ... v", "The Critical Legal Question Preparation v Overt Act":
# a heading or a list number glued to a real citation, or an heading that
# merely contains " v ".
_HEADING_WORDS = {
    "analysis", "legal", "full", "question", "issue", "issues", "summary", "facts",
    "holding", "rule", "application", "conclusion", "step", "critical", "preparation",
    "overt", "key", "note", "answer", "irac", "model", "framework", "test", "principle",
    "principles", "position", "statutory", "procedure", "procedural", "requirement",
    "requirements", "element", "elements", "stage", "point", "doctrine", "distinction",
    "versus", "standard", "burden", "proof", "approach", "difference", "between",
    "comparison", "preliminary", "introduction", "background", "discussion",
    "assessment", "evaluation", "what", "why", "how", "when", "where", "which",
    # The third live week: "The Section 3 Value vs. the Current Operative
    # Value: An Important Distinction", a comparison heading shown to readers
    # as a judgment "not in the library". Words that name a provision or a
    # comparison never begin, or make up, a litigant's name.
    "section", "sections", "article", "order", "clause", "provision", "provisions",
    "regulation", "schedule", "definition", "meaning", "effect", "scope",
    "interpretation", "formula", "amount", "rate", "value", "current", "operative",
    "important", "actual", "practical", "practice", "written", "text", "wording",
    "reading", "literal", "purposive", "strict", "statute", "statutes", "default",
    "base", "former", "latter", "previous", "existing", "proposed", "amended",
    "original", "revised", "correct", "incorrect", "myth", "reality", "fact",
    "fiction", "theory", "option", "options", "scenario", "route", "remedy",
    "remedies", "liability", "damages", "consequence", "consequences", "outcome",
    "process", "before", "after",
}
_COURT_WORDS = {"court", "supreme", "appeal", "high", "constitutional", "subordinate",
                "industrial", "relations", "division", "of"}
# Reporters that place an authority outside Zambia. They are shown as foreign
# rather than as "not in the library": fairly flagged, differently worded.
_FOREIGN_CITE = re.compile(
    r"(?:\b(?:All\s?ER|A\.?C\.?|Q\.?B\.?D?|K\.?B\.?|W\.?L\.?R\.?|Ch\.?\s?D?|Cr\s?App\s?R|EWCA|EWHC|UKHL|UKSC|"
    r"H\.?L\.?|P\.?C\.?|Lloyd'?s\s?Rep|BCLC|FLR|TLR|App\s?Cas|SCR|SASR|CLR|NZLR|ALR)\b)")
_ZM_CITE = re.compile(r"\b(?:ZR|ZMSC|ZMCA|ZMHC|ZMIC|ZMCC|SCZ|CAZ|CCZ|HP[CFA]?|APP|Appeal|Zambia|Zambian)\b", re.I)

_NUMCITE = re.compile(
    r"\b(?:APP|SCZ|CAZ|CCZ|HP[CFA]?|SP|Appeal|ZR|ZMSC|ZMCA|ZMHC|ZMIC|ZMCC)\b"
    r"|\b(?:No\.?\s*)?\d{1,4}\s*(?:of|/)\s*\d{4}\b|\b\d{4}\b", re.I)

# Statutes: "<Name> Act", "<Name> Code", "the Constitution (of Zambia)",
# with optional "No. 3 of 2019" / "Cap. 87" tails.
_ACT = re.compile(
    r"\b(?P<name>"
    r"(?:[A-Z][A-Za-z’'\-]+(?:\s+(?:of|and|the|[A-Z][A-Za-z’'\-]+)){0,7}\s+(?:Act|Code|Rules|Regulations))(?![A-Za-z])"
    r"|Constitution(?:\s+of\s+Zambia)?"
    r")"
    r"(?P<tail>\s*,?\s*(?:No\.?\s*\d+\s*of\s*\d{4}|\(?Cap\.?\s*\d+\)?|\d{4}))?")

_TITLECASE_STOP = {"The", "This", "That", "These", "Those", "A", "An"}

# A statute's name never starts with these. Measured in the first live week:
# answer headings ("## What Order 14 Actually Says") and prose ("a prohibited
# act", "the key rules") were being extracted as statutes and shown to users
# as "not in the library, verify before relying on it" — "What Order",
# "Only Person Who Can Order", "Some Act". A junk NOT FOUND badge is almost as
# corrosive as a false VERIFIED: it teaches the reader to ignore the panel.
_NOT_A_STATUTE_START = {
    "what", "does", "says", "say", "actually", "only", "who", "not", "an",
    "honest", "reassessment", "now", "your", "most", "important", "although",
    "letter", "demand", "three", "modes", "commencing", "action", "contracts",
    "one", "paragraph", "key", "venue", "some", "prohibited", "part", "time",
    "employee", "correct", "which", "why", "how", "when", "where", "under",
    "per", "see", "within", "through", "beyond", "in", "any", "each", "every",
    "relevant", "applicable", "governing", "same", "other", "such", "new",
    "old", "main", "principal", "judicial", "hc", "first", "second", "third",
    "yes", "no", "however", "because", "if", "and", "or", "but", "so",
}
# Suffix words carry no identity: "Rules" alone, or "Venue Rules", say nothing
# about WHICH instrument. At least one token must be a proper content word.
_WEAK_TOKENS = {"the", "of", "and", "zambia", "act", "code", "rules",
                "regulations", "court", "courts", "high"}


def _clean(text: str) -> str:
    # markdown emphasis splits names ("**Employment Code Act**"); drop it
    return re.sub(r"[*_`#]+", "", text or "")


_QUOTES = "\"'\u201c\u201d\u2018\u2019"


# Heading words that open a real, frequently cited litigant's name. Without
# this "Standard Chartered Bank Zambia Plc" was shown as "Chartered Bank".
_LITIGANT_OPENERS = {("standard", "chartered"), ("standard", "bank"), ("key", "stone")}


def _litigant_opener(tokens: list[str]) -> bool:
    return len(tokens) > 1 and (tokens[0].lower(), tokens[1].lower().strip(".,")) in _LITIGANT_OPENERS


def _all_heading(tokens: list[str]) -> bool:
    return bool(tokens) and all(
        t.lower() in _HEADING_WORDS or t.lower() in _CONNECTORS or t.lower() in _COURT_WORDS
        for t in tokens)


def _party_left(text: str, end: int) -> str:
    """Walk left from the pivot collecting the capitalised run."""
    tokens = []
    for m in reversed(list(_WORD.finditer(text[:end]))):
        raw = m.group(0)
        w = raw.strip(".,;:()[]" + _QUOTES)
        if not w:
            break
        if w[0].isupper() or w.isdigit() or w.lower() in _CONNECTORS:
            tokens.append(w)
            # an opening quote starts the name; nothing before it belongs.
            # (Brackets are kept: "Zambia Sugar (Z) Ltd" is one party.)
            if raw[:1] in _QUOTES or len(tokens) >= 8:
                break
        else:
            break
    tokens.reverse()
    # trim sentence-lead words off the left edge, then stray connectors
    while tokens and tokens[0].lower().strip(".") in _EDGE_STOP:
        tokens.pop(0)
    # list numbers ("1.", "2)") and heading words glued to the name
    changed = True
    while tokens and changed:
        changed = False
        if re.fullmatch(r"\d+[.)]?", tokens[0]):
            tokens.pop(0); changed = True; continue
        if tokens[0].lower() in _HEADING_WORDS and not _litigant_opener(tokens):
            tokens.pop(0); changed = True; continue
        if tokens[0] == "The" and len(tokens) > 1 and tokens[1].lower() in _HEADING_WORDS \
                and not _litigant_opener(tokens[1:]):
            tokens.pop(0); tokens.pop(0); changed = True; continue
    # "Supreme Court and <Party>": court prose ahead of the litigant
    for i in range(1, min(5, len(tokens))):
        if tokens[i].lower() in ("and", "in") and all(t.lower() in _COURT_WORDS for t in tokens[:i]):
            tokens = tokens[i + 1:]
            break
    while tokens and tokens[0].lower() in _CONNECTORS and not (
            len(tokens) > 1 and tokens[0] == "The" and tokens[1][0].isupper()):
        tokens.pop(0)
    if _all_heading(tokens):
        return ""
    return " ".join(tokens)


def _party_right(text: str, start: int) -> tuple[str, int]:
    """Walk right from the pivot; returns (party, index after it)."""
    tokens = []
    pos = start
    for m in _WORD.finditer(text, start):
        raw = m.group(0)
        w = raw.strip(".,;:()[]" + _QUOTES)
        low = w.lower()
        if low in _RIGHT_STOP and tokens:
            break
        # a bracket opens the citation tail, which is parsed separately
        if raw[:1] in "([" and tokens:
            break
        if w and (w[0].isupper() or w.isdigit() or low in _CONNECTORS or low in ("others",)):
            tokens.append(w)
            pos = m.end()
            if len(tokens) >= 8 or raw.endswith((",", ".", ";", ":", ")") + tuple(_QUOTES)):
                break
        else:
            break
    # drop a trailing connector, a stray single letter, or heading words
    while tokens and (tokens[-1].lower() in _CONNECTORS
                      or (len(tokens[-1]) == 1 and len(tokens) > 1)
                      or tokens[-1].lower() in _HEADING_WORDS):
        tokens.pop()
    if _all_heading(tokens):
        return "", pos
    return " ".join(tokens), pos


def _stray_number(party: str) -> bool:
    toks = party.split()
    for i, t in enumerate(toks):
        if t.isdigit() and not (i + 1 < len(toks) and toks[i + 1].lower() in ("others", "other", "another", "ors")):
            return True
    return False


def extract_citations(text: str) -> list[dict]:
    """Pull the auditable legal citations out of an answer."""
    text = _clean(text)
    out: list[dict] = []
    seen: set[str] = set()

    for pm in _PIVOT.finditer(text):
        a = _party_left(text, pm.start())
        b, after = _party_right(text, pm.end())
        if not a or not b:
            continue
        # A bare number inside a party ("Section 3 Value", "Rule 14 Test") is
        # a provision reference, not a litigant; "and 29 Others" is the one
        # numeric form real case names take.
        if _stray_number(a) or _stray_number(b):
            continue
        # "R" (the Crown) is a real party in the English cases Zambian courts cite
        if _norm(a).split()[:1] == ["v"] or (len(_norm(a)) < 3 and a != "R") or len(_norm(b)) < 3:
            continue
        # optional "(APP No. 142 of 2019)" style tail
        tail = text[after:after + 60]
        cm = re.match(r"\s*[\(\[]\s*([^)\]]{3,58})\s*[\)\]]", tail)
        cite = (cm.group(1).strip() if cm else "")
        if not cite:
            # unbracketed tail: "... v Loretta Kunda Court of Appeal Case No.
            # 142 of 2019" still carries the number that verifies the match
            nm = re.search(r"(?:No\.?\s*)?(\d{1,4})\s*(?:of|/)\s*(\d{4})", tail)
            if nm:
                cite = f"{nm.group(1)} of {nm.group(2)}"
        # only audit things that look like real case references: either a
        # citation-ish tail exists nearby, or both parties are multiword/known
        numeric = bool(_NUMCITE.search(cite)) or bool(_NUMCITE.search(tail[:40]))
        if not numeric and (len(a.split()) + len(b.split())) < 3:
            continue
        display = f"{a} v {b}" + (f" ({cite})" if cite else "")
        key = _norm(display)
        if key in seen:
            continue
        seen.add(key)
        # English and other foreign reports: a reporter abbreviation in the
        # tail, or a pre-independence year with no Zambian marker anywhere.
        near = (cite + " " + tail[:60])
        ym = re.search(r"\b(1[89]\d\d)\b", near)
        foreign = bool(_FOREIGN_CITE.search(near)) or (
            bool(ym) and int(ym.group(1)) < 1964 and not _ZM_CITE.search(near + " " + a + " " + b))
        out.append({"kind": "case", "text": display, "a": a, "b": b, "cite": cite,
                    "foreign": foreign})

    candidates = []
    for m in _ACT.finditer(text):
        nm = m.group("name").strip()
        # Two instruments conjoined ("the Wills Act and the ILRA") split only
        # where the left side already ends with an instrument word. Splitting
        # at every "and" cut the Fees and Fines Act down to "Fines Act".
        pieces = re.sub(r"\b(Act|Code|Rules|Regulations)\s+and\s+(?:the\s+)?", r"\1|", nm).split("|")
        if len(pieces) > 1:
            for pc in pieces:
                candidates.append((pc.strip(), ""))
        else:
            candidates.append((nm, m.group("tail") or ""))
    for name, tail in candidates:
        name = name.strip()
        # "Under the Employment Code Act" -> "Employment Code Act"
        parts = name.split()
        while parts and parts[0].lower() in ("under", "per", "see", "within",
                                             "through", "beyond", "the", "in"):
            parts.pop(0)
        # A heading glued to a real name: "Discipline Under the Employment Code
        # Act", "Objection The High Court Act". The instrument is the tail after
        # the last "Under the" or mid-name capital "The", so keep only that.
        joined = " ".join(parts)
        for sep in (" Under the ", " under the ", " Under ", " The "):
            if sep in joined:
                joined = joined.rsplit(sep, 1)[-1]
        parts = joined.split()
        # peel any heading/prose words off the front
        while parts and parts[0].lower().strip(".,") in (_NOT_A_STATUTE_START | {"of", "the"}):
            parts.pop(0)
        name = " ".join(parts)
        if not parts or len(parts) < 2:
            continue
        content = [w for w in parts[:-1] if w.lower() not in _WEAK_TOKENS]
        if not content and not name.lower().startswith(("high court", "subordinate court",
                                                        "supreme court", "court of appeal",
                                                        "constitutional court")):
            continue
        if name.split()[0] in _TITLECASE_STOP and len(name.split()) < 3:
            continue
        display = (name + tail).strip(" ,")
        key = _norm(name)
        if key in seen or len(key) < 8:
            continue
        seen.add(key)
        foreign = name.startswith(("English ", "UK ", "United Kingdom ", "British ")) or "(UK)" in display
        out.append({"kind": "statute", "text": display, "name": name, "foreign": foreign})

    return out[:20]


# ── verification ────────────────────────────────────────────────────────────

def _num_tokens(s: str) -> list[str]:
    return re.findall(r"\d+", s or "")


def _tok_in(tok: str, hay: str) -> bool:
    """Token membership tolerant of one-letter spelling drift.

    The measured miss: the model cites "Loretta" while the stored title says
    "Loreta" (the judgment's own OCR). Exact membership called a case we hold
    unverified. A ratio floor of 0.86 tolerates that drift without letting
    different surnames through ("banda" vs "bandra" fails, "zulu" vs "zule"
    fails on length-4 words).
    """
    if tok in hay:
        return True
    if len(tok) < 5:
        return False
    from difflib import SequenceMatcher
    return any(SequenceMatcher(None, tok, w).ratio() >= 0.86
               for w in hay.split() if abs(len(w) - len(tok)) <= 2)


def _match_case(c: dict, index: list[dict]) -> dict | None:
    """Match a cited case to a held judgment, biased hard toward precision.

    The measured failure this guards: "Zulu v The People (1990-2) ZR 65" —
    which Levy deliberately does not hold — party-matched "Violet Zulu v The
    People (2025)", a different case, and would have worn a VERIFIED badge.
    A wrong VERIFIED is strictly worse than a wrong NOT FOUND, so:

      * if the citation names a year, the candidate must carry that year;
      * if several candidates match the parties and no number disambiguates,
        we return nothing rather than guess.
    """
    na, nb = _norm(c["a"]), _norm(c["b"])
    cite_years = [n for n in _num_tokens(c.get("cite") or "") if len(n) == 4]
    cite_nums = [n for n in _num_tokens(c.get("cite") or "") if len(n) < 4]
    hits = []
    for r in index:
        if r.get("document_type") != "judgment":
            continue
        hay = r["_ntitle"] + " " + r["_nshort"]
        a_hit = all(_tok_in(w, hay) for w in na.split()[:2])
        b_hit = all(_tok_in(w, hay) for w in nb.split()[:2])
        if not (a_hit and b_hit):
            continue
        hay_years = [n for n in _num_tokens(hay) if len(n) == 4]
        if cite_years and not any(y in hay_years for y in cite_years):
            continue  # cited year absent from the candidate: different case
        score = 0
        if cite_years and any(y in hay_years for y in cite_years):
            score += 2
        if cite_nums and any(n in _num_tokens(hay) for n in cite_nums):
            score += 2
        hits.append((score, r))
    if not hits:
        return None
    hits.sort(key=lambda x: -x[0])
    top = [r for sc, r in hits if sc == hits[0][0]]
    # several equally-plausible candidates and nothing numeric to pick one:
    # refuse to guess.
    if len(top) > 1 and hits[0][0] == 0:
        return None
    return top[0]


_STATUTE_TYPES = ("act", "bill", "court_rule", "statutory_instrument")


def _statute_candidates(c: dict, index: list[dict]) -> list[dict]:
    name = _norm(c["name"])
    if name in ("constitution", "constitution of zambia"):
        name = "constitution of zambia"
    cands = [r for r in index
             if r.get("document_type") in _STATUTE_TYPES
             and ((name and name in r["_ntitle"]) or (r["_nshort"] and name == r["_nshort"]))]
    if cands:
        return cands
    # tolerate the common "Employment Code Act" vs "THE EMPLOYMENT CODE ACT, 2019"
    toks = [t for t in name.split() if t not in ("the", "of", "zambia")]
    if len(toks) >= 2:
        return [r for r in index
                if r.get("document_type") in _STATUTE_TYPES and all(t in r["_ntitle"] for t in toks)]
    return []


def _doc_year(r: dict) -> int | None:
    if r.get("year"):
        return int(r["year"])
    title = re.sub(r"\[[^\]]*\]", " ", r.get("title") or "")   # not "[repealed by ..., 2002]"
    m = re.search(r"\b((?:19|20)\d{2})\b", f"{r.get('act_number') or ''} {title}")
    return int(m.group(1)) if m else None


def _cited_year(c: dict) -> int | None:
    m = re.search(r"\b((?:19|20)\d{2})\b", c.get("text", "")[len(c.get("name", "")):])
    return int(m.group(1)) if m else None


def _base(title: str) -> str:
    """ "REPUBLIC OF ZAMBIA THE COMPANIES ACT, 2017 (No. 10 of 2017)" -> "companies act"."""
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", title or "")
    t = _norm(t)
    t = re.sub(r"^(?:republic of zambia )?(?:the )?", "", t)
    t = re.sub(r"\b(?:19|20)\d{2}\b|\bno \d+ of\b|\bcap(?:ter)? \d+\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _kind_fits(name: str, r: dict) -> bool:
    last = _norm(name).split()[-1:] or [""]
    if last[0] in ("act", "code", "constitution"):
        return r.get("document_type") in ("act", "bill")
    return r.get("document_type") in ("court_rule", "statutory_instrument")


def _match_statute(c: dict, index: list[dict]) -> dict | None:
    cands = _statute_candidates(c, index)
    if not cands:
        return None
    name = c["name"]
    year = _cited_year(c)
    capped = bool(re.search(r"\bCap(?:ter)?\.?\s*\d+", c.get("text", ""), re.I))

    def rank(r: dict) -> tuple:
        # An exact name beats a longer title that merely contains it ("Test
        # Certificates Regulations (Roads and Road Traffic Act)"); the kind of
        # instrument must fit; a cited year must agree, and a Cap. number
        # without a year points at the old consolidated edition (undated or
        # before 1997), so "Companies Act, Cap. 388" is not the 2017 Act.
        dy = _doc_year(r)
        return (
            0 if _base(name) in (r["_bshort"], r["_btitle"]) else 1,
            0 if _kind_fits(name, r) else 1,
            0 if not year or dy == year else 1,
            0 if not capped or year or not dy or dy <= 1996 else 1,
            len(r["_ntitle"]),
        )
    return min(cands, key=rank)


def _law_status(c: dict, row: dict, index: list[dict]) -> dict:
    """Repealed or pending, when that is certain for the Act the answer means.

    A wrong "repealed" on live law is worse than no flag, so the flag needs
    the matched Act to be repealed AND either the citation to pin it down (a
    year, or a Cap. number, which only the old consolidated edition carries)
    or every Act of that name in the library to be repealed. "Companies Act"
    alone is left unflagged: the Companies Act, 2017 is in force.
    """
    from . import law_map
    e = law_map.entry(row["id"])
    status = e.get("status")
    if status not in ("repealed", "repeal pending"):
        return {}
    key = "repealed_by" if status == "repealed" else "repeal_pending_by"
    refs = e.get(key) or []
    text = c.get("text", "")
    year = _cited_year(c)
    if year:
        # "Arbitration Act, 2000" when only the 1933 Act is in the library:
        # the match is by name, but the answer means the newer Act.
        dy = _doc_year(row)
        newest = max((y for y in (law_map.ref_year(x) for x in refs) if y), default=None)
        if (dy and dy != year) or (newest and year >= newest):
            return {}
    pinned = bool(year) or bool(re.search(r"\bCap(?:ter)?\.?\s*\d+", text, re.I))
    if not pinned:
        # Only an Act of exactly this name can make the citation ambiguous;
        # "Employment Act" is not the Minimum Wages and Conditions of
        # Employment Act.
        live = [r for r in _statute_candidates(c, index)
                if r.get("document_type") == "act" and r["id"] != row["id"]
                and r["_btitle"] == _base(c["name"])
                and law_map.entry(r["id"]).get("status") not in ("repealed",)]
        if live and status == "repealed":
            return {}
    by = [law_map.ref_name(x) for x in refs if x.get("title")]
    return {"law_status": status, "replaced_by": list(dict.fromkeys(b for b in by if b))[:3]}


def audit_answer(text: str) -> list[dict]:
    """Return per-citation verdicts for an answer. Never raises."""
    try:
        cites = extract_citations(text or "")
        if not cites:
            return []
        index = _load_index()
        out = []
        for c in cites:
            foreign = bool(c.get("foreign"))
            row = None
            if not foreign:
                row = _match_case(c, index) if c["kind"] == "case" else _match_statute(c, index)
            if row:
                verdict = {"text": c["text"], "kind": c["kind"], "status": "verified",
                           "document_id": row["id"], "title": row.get("title")}
                if c["kind"] == "statute":
                    # The badge says the Act is in the library; this says
                    # whether it is still law.
                    verdict.update(_law_status(c, row, index))
                out.append(verdict)
            else:
                verdict = {"text": c["text"], "kind": c["kind"], "status": "not_found"}
                if foreign:
                    verdict["foreign"] = True
                out.append(verdict)
        return out
    except Exception:  # noqa: BLE001 — the audit must never break an answer
        return []
